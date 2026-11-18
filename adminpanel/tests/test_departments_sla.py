from django.urls import reverse

from audit.models import AuditLog
from complaints.models import ComplaintStatus as S
from departments.models import Department, Priority, SLAConfiguration
from departments.services import sla_hours_for

from .helpers import AdminTestCase


class DepartmentTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.as_admin()

    def test_new_department_needs_no_code_change(self):
        response = self.client.post(reverse("adminpanel:department_new"), {"name": "Parks", "code": "PARKS", "description": "Gardens"}, follow=True)
        self.assertContains(response, "Parks was added")
        dept = Department.objects.get(code="PARKS")
        self.assertTrue(dept.is_active)
        self.assertContains(response, "Not trained yet")
        self.assertTrue(AuditLog.objects.filter(action="DEPARTMENT_CREATED", target_id=dept.pk).exists())

    def test_invalid_and_duplicate_departments(self):
        before = Department.objects.count()
        for bad in ({"name": "Roads 2", "code": "roads"}, {"name": "x", "code": "A"}, {"name": "Electricity", "code": "NEWCODE"},
                    {"name": "Other", "code": "ELECTRICITY"}, {"name": "", "code": "OK_CODE"}):
            self.client.post(reverse("adminpanel:department_new"), bad)
        self.assertEqual(Department.objects.count(), before)

    def test_cannot_deactivate_a_department_that_still_has_active_work(self):
        response = self.client.post(reverse("adminpanel:department_toggle", args=[self.elec.pk, "off"]), follow=True)
        self.assertContains(response, "still has active complaints")
        self.elec.refresh_from_db()
        self.assertTrue(self.elec.is_active)

    def test_deactivate_and_reactivate_an_idle_department(self):
        self.client.post(reverse("adminpanel:department_toggle", args=[self.water.pk, "off"]))
        self.water.refresh_from_db()
        self.assertFalse(self.water.is_active)
        self.client.post(reverse("adminpanel:department_toggle", args=[self.water.pk, "on"]))
        self.water.refresh_from_db()
        self.assertTrue(self.water.is_active)
        self.assertEqual(AuditLog.objects.filter(action__in=["DEPARTMENT_DEACTIVATED", "DEPARTMENT_ACTIVATED"]).count(), 2)

    def test_listing_shows_counts(self):
        page = self.client.get(reverse("adminpanel:departments"))
        electricity = next(d for d in page.context["departments"] if d.code == "ELECTRICITY")
        self.assertEqual((electricity.officers_n, electricity.workers_n, electricity.active_n), (1, 2, 1))


class SlaSettingsTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.as_admin()
        self.url = reverse("adminpanel:sla")

    def test_form_starts_with_the_current_values(self):
        form = self.client.get(self.url).context["form"]
        self.assertEqual([form.initial[p] for p in ("CRITICAL", "HIGH", "MEDIUM", "LOW")], [4, 12, 24, 72])

    def test_saving_changes_the_hours_and_is_audited(self):
        response = self.client.post(self.url, {"CRITICAL": 2, "HIGH": 12, "MEDIUM": 36, "LOW": 72}, follow=True)
        self.assertContains(response, "SLA settings saved")
        self.assertEqual((sla_hours_for(Priority.CRITICAL), sla_hours_for(Priority.MEDIUM), sla_hours_for(Priority.HIGH)), (2, 36, 12))
        entry = AuditLog.objects.get(action="SLA_CHANGED")
        self.assertEqual(entry.details, {"CRITICAL": [4, 2], "MEDIUM": [24, 36]})
        self.assertEqual(SLAConfiguration.objects.count(), 4)

    def test_unchanged_values_are_not_audited(self):
        self.client.post(self.url, {"CRITICAL": 4, "HIGH": 12, "MEDIUM": 24, "LOW": 72})
        self.assertFalse(AuditLog.objects.filter(action="SLA_CHANGED").exists())

    def test_invalid_values_are_rejected(self):
        for bad in (0, -5, 721, "abc", ""):
            self.client.post(self.url, {"CRITICAL": bad, "HIGH": 12, "MEDIUM": 24, "LOW": 72})
        self.assertEqual(sla_hours_for(Priority.CRITICAL), 4)
        self.assertFalse(AuditLog.objects.filter(action="SLA_CHANGED").exists())

    def test_new_complaints_use_the_new_hours(self):
        self.client.post(self.url, {"CRITICAL": 1, "HIGH": 12, "MEDIUM": 24, "LOW": 72})
        from datetime import timedelta
        from complaints.services import route_complaint
        c = self.make(status=S.SUBMITTED, dept=None, title="Live wire hanging low", description="A live electric wire is hanging low near the lane")
        route_complaint(c)
        c.refresh_from_db()
        self.assertEqual(c.sla_deadline - c.created_at, timedelta(hours=1))
