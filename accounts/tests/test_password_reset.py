import re

from django.conf import settings
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .helpers import PASSWORD, make_user


@override_settings(SITE_URL="http://testserver")
class PasswordResetTests(TestCase):
    def test_full_reset_flow(self):
        make_user("reset@example.com")
        r = self.client.post(reverse("accounts:password_reset"), {"email": "reset@example.com"})
        self.assertRedirects(r, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].reply_to, [settings.DEFAULT_REPLY_TO_EMAIL])

        link = re.search(r"https?://testserver(/accounts/reset/\S+)", mail.outbox[0].body).group(1)
        r = self.client.get(link, follow=True)           # token is swapped into the session
        self.assertContains(r, "Set a new password")
        set_url = r.redirect_chain[-1][0]

        new_pw = "Brand-New-Pass#42"
        r = self.client.post(set_url, {"new_password1": new_pw, "new_password2": new_pw})
        self.assertRedirects(r, reverse("accounts:password_reset_complete"))

        self.assertFalse(self.client.login(email="reset@example.com", password=PASSWORD))
        self.assertTrue(self.client.login(email="reset@example.com", password=new_pw))

    @override_settings(SITE_URL="https://mobile.example.test:8443")
    def test_reset_email_uses_configured_site_url_instead_of_request_host(self):
        make_user("mobile@example.com")
        self.client.post(reverse("accounts:password_reset"), {"email": "mobile@example.com"})
        self.assertIn("https://mobile.example.test:8443/accounts/reset/", mail.outbox[0].body)

    def test_unknown_email_gives_same_response_and_sends_nothing(self):
        r = self.client.post(reverse("accounts:password_reset"), {"email": "ghost@example.com"})
        self.assertRedirects(r, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_token_is_rejected(self):
        r = self.client.get(reverse("accounts:password_reset_confirm", args=["bad", "token"]))
        self.assertContains(r, "expired or invalid")

    def test_weak_new_password_rejected(self):
        make_user("w@example.com")
        self.client.post(reverse("accounts:password_reset"), {"email": "w@example.com"})
        link = re.search(r"(/accounts/reset/\S+)", mail.outbox[0].body).group(1)
        set_url = self.client.get(link, follow=True).redirect_chain[-1][0]
        r = self.client.post(set_url, {"new_password1": "12345678", "new_password2": "12345678"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.client.login(email="w@example.com", password=PASSWORD))  # unchanged
