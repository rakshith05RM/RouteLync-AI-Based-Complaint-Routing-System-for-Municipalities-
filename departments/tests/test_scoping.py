from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.views.generic import TemplateView

from accounts.models import Role
from accounts.tests.helpers import make_department, make_user
from departments.mixins import DepartmentScopedMixin, ensure_same_department
from departments.models import OfficerProfile


class ProbeView(DepartmentScopedMixin, TemplateView):
    template_name = "dashboards/placeholder.html"


class DepartmentScopingTests(TestCase):
    def setUp(self):
        self.elec, self.water = make_department("ELECTRICITY"), make_department("WATER_SUPPLY")
        self.elec_officer = make_user("e@example.com", Role.OFFICER, department=self.elec)
        self.water_officer = make_user("w@example.com", Role.OFFICER, department=self.water)

    def call(self, user):
        request = RequestFactory().get("/probe/")
        request.user = user
        return ProbeView.as_view()(request)

    def test_officer_dashboard_shows_only_own_department(self):
        self.client.force_login(self.elec_officer)
        response = self.client.get(reverse("officer:dashboard"))
        self.assertContains(response, "Electricity")
        self.assertNotContains(response, "Water Supply")

    def test_scope_queryset_returns_only_own_department_rows(self):
        request = RequestFactory().get("/")
        request.user = self.elec_officer
        view = ProbeView()
        view.setup(request)
        rows = view.scope_queryset(OfficerProfile.objects.all())
        self.assertEqual(list(rows.values_list("user__email", flat=True)), ["e@example.com"])

    def test_ensure_same_department_blocks_other_department(self):
        ensure_same_department(self.elec_officer, self.elec)  # allowed
        with self.assertRaises(PermissionDenied):
            ensure_same_department(self.elec_officer, self.water)

    def test_officer_without_profile_is_denied(self):
        from django.contrib.auth import get_user_model
        orphan = get_user_model().objects.create_user("orphan@example.com", "x", full_name="Orphan", role=Role.OFFICER)
        self.client.force_login(orphan)
        self.assertEqual(self.client.get(reverse("officer:dashboard")).status_code, 403)

    def test_officer_of_inactive_department_is_denied(self):
        self.elec.is_active = False
        self.elec.save()
        self.client.force_login(self.elec_officer)
        self.assertEqual(self.client.get(reverse("officer:dashboard")).status_code, 403)

    def test_field_worker_cannot_use_officer_view_and_vice_versa(self):
        worker = make_user("fw@example.com", Role.FIELD_WORKER, department=self.elec)
        self.client.force_login(worker)
        self.assertEqual(self.client.get(reverse("officer:dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("worker:dashboard")).status_code, 200)
        self.client.force_login(self.elec_officer)
        self.assertEqual(self.client.get(reverse("worker:dashboard")).status_code, 403)
