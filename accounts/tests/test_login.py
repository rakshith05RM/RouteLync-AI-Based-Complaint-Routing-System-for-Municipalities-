from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role

from .helpers import PASSWORD, make_user


class LoginTests(TestCase):
    url = reverse("accounts:login")

    def setUp(self):
        cache.clear()

    def test_login_page_has_a_clear_welcome_and_shared_access_note(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Welcome back")
        self.assertContains(response, "One account for citizens and city teams.")
        self.assertContains(response, "Stay in the loop with every report.")
        self.assertContains(response, "PICK UP WHERE YOU LEFT OFF")

    def test_each_role_lands_on_its_own_dashboard(self):
        expected = {Role.CITIZEN: "complaints:my_complaints", Role.OFFICER: "officer:dashboard",
                    Role.FIELD_WORKER: "worker:dashboard", Role.ADMIN: "adminpanel:dashboard"}
        for role, name in expected.items():
            self.client.logout()
            make_user(f"{role.lower()}@example.com", role=role)
            response = self.client.post(self.url, {"username": f"{role.lower()}@example.com", "password": PASSWORD})
            self.assertRedirects(response, reverse(name), msg_prefix=role)

    def test_login_email_is_case_insensitive(self):
        make_user("case@example.com")
        response = self.client.post(self.url, {"username": "CASE@Example.com", "password": PASSWORD})
        self.assertEqual(response.status_code, 302)

    def test_invalid_login_shows_generic_error(self):
        make_user("a@example.com")
        for creds in (("a@example.com", "wrong"), ("nobody@example.com", PASSWORD)):
            response = self.client.post(self.url, {"username": creds[0], "password": creds[1]})
            self.assertContains(response, "Incorrect email or password")
            self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_user_cannot_login(self):
        make_user("off@example.com", is_active=False)
        response = self.client.post(self.url, {"username": "off@example.com", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_safe_next_is_honoured_and_external_next_ignored(self):
        make_user("n@example.com")
        profile = reverse("accounts:profile")
        r = self.client.post(self.url + f"?next={profile}", {"username": "n@example.com", "password": PASSWORD})
        self.assertRedirects(r, profile)
        self.client.logout()
        r = self.client.post(self.url + "?next=https://evil.example/", {"username": "n@example.com", "password": PASSWORD})
        self.assertRedirects(r, reverse("complaints:my_complaints"))

    def test_lockout_after_repeated_failures_even_with_correct_password(self):
        make_user("lock@example.com")
        for _ in range(5):
            self.client.post(self.url, {"username": "lock@example.com", "password": "bad"})
        response = self.client.post(self.url, {"username": "lock@example.com", "password": PASSWORD})
        self.assertContains(response, "Too many failed attempts")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_post(self):
        self.client.force_login(make_user())
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("core:home"))
        self.assertNotIn("_auth_user_id", self.client.session)
