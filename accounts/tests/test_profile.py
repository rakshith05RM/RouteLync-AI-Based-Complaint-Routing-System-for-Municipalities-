from django.test import TestCase
from django.urls import reverse

from accounts.models import CitizenProfile, Role

from .helpers import PASSWORD, make_user


class ProfileTests(TestCase):
    url = reverse("accounts:profile")

    def test_login_required(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_citizen_updates_name_phone_address(self):
        user = make_user("p@example.com")
        self.client.force_login(user)
        r = self.client.post(self.url, {"full_name": "  New   Name ", "phone": "9123456789", "address": "Jayanagar"})
        self.assertRedirects(r, self.url)
        user.refresh_from_db()
        self.assertEqual((user.full_name, user.phone), ("New Name", "9123456789"))
        self.assertEqual(CitizenProfile.objects.get(user=user).address, "Jayanagar")

    def test_email_and_role_cannot_be_changed_here(self):
        user = make_user("safe@example.com")
        self.client.force_login(user)
        self.client.post(self.url, {"full_name": "Safe User", "phone": "9123456789",
                                    "email": "hacker@example.com", "role": "ADMIN"})
        user.refresh_from_db()
        self.assertEqual((user.email, user.role), ("safe@example.com", Role.CITIZEN))

    def test_officer_profile_has_no_address_field(self):
        self.client.force_login(make_user("off@example.com", role=Role.OFFICER))
        self.assertNotContains(self.client.get(self.url), 'name="address"')

    def test_change_password(self):
        user = make_user("cp@example.com")
        self.client.force_login(user)
        new = "Another-Str0ng#Pass"
        r = self.client.post(reverse("accounts:password_change"),
                             {"old_password": PASSWORD, "new_password1": new, "new_password2": new})
        self.assertRedirects(r, self.url)
        user.refresh_from_db()
        self.assertTrue(user.check_password(new))
