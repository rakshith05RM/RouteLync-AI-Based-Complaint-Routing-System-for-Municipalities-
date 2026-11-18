from django.urls import reverse

from accounts.models import Role
from accounts.tests.helpers import make_user

from .helpers import AdminTestCase


class AdminAccessTests(AdminTestCase):
    def pages(self):
        c = self.complaint
        return [reverse(n) for n in ("adminpanel:dashboard", "adminpanel:complaints", "adminpanel:queue", "adminpanel:users",
                                     "adminpanel:user_new", "adminpanel:departments", "adminpanel:sla", "adminpanel:ai",
                                     "adminpanel:dataset", "adminpanel:dataset_export", "adminpanel:audit")] + [reverse("adminpanel:complaint", args=[c.pk])]

    def posts(self):
        c = self.complaint
        return [reverse("adminpanel:route", args=[c.pk]), reverse("adminpanel:reject", args=[c.pk]), reverse("adminpanel:train"),
                reverse("adminpanel:user_action", args=[self.officer.pk, "deactivate"]), reverse("adminpanel:department_new"),
                reverse("adminpanel:department_toggle", args=[self.elec.pk, "off"]), reverse("adminpanel:dataset_upload"),
                reverse("adminpanel:dataset_add")]

    def test_anonymous_is_sent_to_login(self):
        for url in self.pages():
            self.assertRedirects(self.client.get(url), f"{reverse('accounts:login')}?next={url}")

    def test_every_other_role_gets_403_on_pages_and_actions(self):
        for user in (self.citizen, self.officer, self.worker):
            self.client.force_login(user)
            for url in self.pages():
                self.assertEqual(self.client.get(url).status_code, 403, f"{user.role} GET {url}")
            for url in self.posts():
                self.assertEqual(self.client.post(url, {}).status_code, 403, f"{user.role} POST {url}")

    def test_administrator_can_open_every_page(self):
        self.as_admin()
        for url in self.pages():
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_action_endpoints_are_post_only(self):
        self.as_admin()
        for url in self.posts():
            self.assertEqual(self.client.get(url).status_code, 405, url)

    def test_administrators_land_on_the_dashboard_after_login(self):
        response = self.client.post(reverse("accounts:login"), {"username": "admin@example.com", "password": "Str0ng-Pass!word"})
        self.assertRedirects(response, reverse("adminpanel:dashboard"))

    def test_admin_can_see_every_departments_complaints(self):
        other = self.make(dept=self.water, title="Water pipe leaking badly")
        self.as_admin()
        page = self.client.get(reverse("adminpanel:complaints"))
        self.assertContains(page, other.reference)
        self.assertContains(page, self.complaint.reference)
        self.assertEqual(self.client.get(reverse("adminpanel:complaint", args=[other.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("adminpanel:complaint", args=[999999])).status_code, 404)
