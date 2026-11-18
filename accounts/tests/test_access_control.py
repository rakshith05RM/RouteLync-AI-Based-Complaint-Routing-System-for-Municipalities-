from django.test import TestCase
from django.urls import reverse

from accounts.mixins import role_required
from accounts.models import Role

from .helpers import make_user


class RoleAccessTests(TestCase):
    PAGES = {
        Role.CITIZEN: "complaints:my_complaints",
        Role.OFFICER: "officer:dashboard",
        Role.FIELD_WORKER: "worker:dashboard",
        Role.ADMIN: "adminpanel:dashboard",
    }

    def test_anonymous_users_are_sent_to_login(self):
        for name in self.PAGES.values():
            url = reverse(name)
            response = self.client.get(url)
            self.assertRedirects(response, f"{reverse('accounts:login')}?next={url}", msg_prefix=name)

    def test_every_role_can_open_only_its_own_dashboard(self):
        for role in self.PAGES:
            self.client.logout()
            self.client.force_login(make_user(f"{role.lower()}@example.com", role=role))
            for page_role, name in self.PAGES.items():
                expected = 200 if page_role == role else 403
                self.assertEqual(self.client.get(reverse(name)).status_code, expected, f"{role} -> {name}")

    def test_named_scenarios_from_the_spec(self):
        self.client.force_login(make_user("c@example.com", role=Role.CITIZEN))
        self.assertEqual(self.client.get(reverse("officer:dashboard")).status_code, 403)
        self.client.force_login(make_user("w@example.com", role=Role.FIELD_WORKER))
        self.assertEqual(self.client.get(reverse("adminpanel:dashboard")).status_code, 403)

    def test_forbidden_page_is_friendly(self):
        self.client.force_login(make_user())
        response = self.client.get(reverse("adminpanel:dashboard"))
        self.assertContains(response, "Access denied", status_code=403)

    def test_dashboard_router_redirects_by_role(self):
        self.client.force_login(make_user("o@example.com", role=Role.OFFICER))
        self.assertRedirects(self.client.get(reverse("accounts:dashboard")), reverse("officer:dashboard"))

    def test_role_required_decorator(self):
        from django.core.exceptions import PermissionDenied
        from django.http import HttpResponse
        from django.test import RequestFactory

        @role_required(Role.ADMIN)
        def view(request):
            return HttpResponse("ok")

        rf = RequestFactory()
        request = rf.get("/x/")
        request.user = make_user("d@example.com", role=Role.CITIZEN)
        with self.assertRaises(PermissionDenied):
            view(request)
        request.user = make_user("e@example.com", role=Role.ADMIN)
        self.assertEqual(view(request).status_code, 200)
