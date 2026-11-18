import re

from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CitizenProfile, Role, User

from .helpers import PASSWORD, make_user


def code_from(message) -> str:
    return re.search(r"\b(\d{6})\b", message.body).group(1)


class RegistrationTests(TestCase):
    url = reverse("accounts:register")

    def payload(self, **over):
        data = {"full_name": "Asha Rao", "email": "Asha@Example.com", "phone": "9876543210",
                "address": "12, 4th Main Road", "password1": PASSWORD, "password2": PASSWORD}
        data.update(over)
        return data

    def test_registration_page_explains_email_verification(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Create your account")
        self.assertContains(response, "verification code to finish setting up your account")
        self.assertContains(response, "Start with a report. Stay for the resolution.")
        self.assertContains(response, "YOUR FIRST REPORT, STEP BY STEP")

    def test_registration_creates_a_pending_account_and_emails_a_code(self):
        response = self.client.post(self.url, self.payload())
        self.assertRedirects(response, reverse("accounts:verify_email"))
        user = User.objects.get(email="asha@example.com")
        self.assertEqual((user.role, user.email_verified), (Role.CITIZEN, False))
        self.assertTrue(CitizenProfile.objects.filter(user=user, address="12, 4th Main Road").exists())
        self.assertNotEqual(user.password, PASSWORD)
        self.assertNotIn("_auth_user_id", self.client.session)                    # NOT signed in until verified
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["asha@example.com"])
        self.assertRegex(mail.outbox[0].body, r"\b\d{6}\b")
        self.assertNotIn(PASSWORD, mail.outbox[0].body)

    def test_role_cannot_be_injected_through_post(self):
        self.client.post(self.url, self.payload(role="ADMIN", is_staff="on", is_superuser="on"))
        user = User.objects.get(email="asha@example.com")
        self.assertEqual(user.role, Role.CITIZEN)
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_registering_a_verified_address_looks_identical_and_changes_nothing(self):
        make_user("asha@example.com", full_name="Original Name")
        fresh = Client()
        response = fresh.post(self.url, self.payload(full_name="Someone Else"))
        self.assertRedirects(response, reverse("accounts:verify_email"), fetch_redirect_response=False)   # same page as a brand-new address
        page = fresh.get(reverse("accounts:verify_email"))
        self.assertContains(page, "If this address can be used")
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().full_name, "Original Name")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("already have one", mail.outbox[0].body)                          # the real owner is told
        self.assertNotRegex(mail.outbox[0].body, r"\b\d{6}\b")                          # ...and no code is sent
        self.assertEqual(User.objects.get().check_password(PASSWORD), True)             # password not replaced

    def test_registering_a_pending_address_again_replaces_the_details_and_sends_a_new_code(self):
        self.client.post(self.url, self.payload(full_name="First Try"))
        Client().post(self.url, self.payload(full_name="Second Try", password1="Another-Str0ng#Pass", password2="Another-Str0ng#Pass"))
        user = User.objects.get()
        self.assertEqual(user.full_name, "Second Try")
        self.assertTrue(user.check_password("Another-Str0ng#Pass"))
        self.assertEqual(len(mail.outbox), 2)

    def test_password_mismatch_and_weak_passwords(self):
        self.assertContains(self.client.post(self.url, self.payload(password2="Different-1!x")), "do not match")
        for weak in ("short1", "12345678", "password123"):
            self.assertEqual(self.client.post(self.url, self.payload(password1=weak, password2=weak)).status_code, 200, weak)
        self.assertFalse(User.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_phone_email_and_name(self):
        for bad in ({"phone": "12345"}, {"phone": "5876543210"}, {"phone": "98765abcde"}, {"email": "not-an-email"},
                    {"full_name": "A"}, {"full_name": "R2D2 <script>"}, {"full_name": ""}):
            self.assertEqual(self.client.post(self.url, self.payload(**bad)).status_code, 200, bad)
        self.assertFalse(User.objects.exists())

    def test_registration_without_csrf_token_is_rejected(self):
        self.assertEqual(Client(enforce_csrf_checks=True).post(self.url, self.payload()).status_code, 403)

    def test_logged_in_user_is_redirected_away(self):
        self.client.force_login(make_user())
        self.assertRedirects(self.client.get(self.url), reverse("complaints:my_complaints"))
