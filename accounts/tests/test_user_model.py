from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase, override_settings

from accounts.models import Role

User = get_user_model()


class UserModelTests(TestCase):
    @override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.PBKDF2PasswordHasher"])
    def test_create_user_defaults_to_citizen_with_hashed_password(self):
        user = User.objects.create_user("Asha@Example.com", "S3cure-pass!", full_name="Asha Rao")
        self.assertEqual(user.role, Role.CITIZEN)
        self.assertEqual(user.email, "asha@example.com")  # normalised to lower case
        self.assertNotEqual(user.password, "S3cure-pass!")  # not plain text
        self.assertTrue(user.password.startswith(("pbkdf2_", "argon2", "bcrypt")))
        self.assertTrue(user.check_password("S3cure-pass!"))
        self.assertFalse(user.is_staff)

    def test_create_superuser_is_admin_role(self):
        admin = User.objects.create_superuser("root@example.com", "S3cure-pass!", full_name="Root")
        self.assertEqual(admin.role, Role.ADMIN)
        self.assertTrue(admin.is_staff and admin.is_superuser)

    def test_email_is_required(self):
        with self.assertRaises(ValueError):
            User.objects.create_user("", "x", full_name="No Email")

    def test_duplicate_email_rejected_case_insensitively(self):
        User.objects.create_user("dup@example.com", "S3cure-pass!", full_name="One")
        with self.assertRaises(IntegrityError):
            User.objects.create_user("DUP@example.com", "S3cure-pass!", full_name="Two")

    def test_phone_validation(self):
        user = User(email="p@example.com", full_name="P", phone="12345")
        with self.assertRaises(ValidationError):
            user.full_clean(exclude=["password"])
        user.phone = "9876543210"
        user.full_clean(exclude=["password"])  # valid -> no exception

    def test_login_with_email_and_inactive_user_blocked(self):
        user = User.objects.create_user("l@example.com", "S3cure-pass!", full_name="L")
        self.assertEqual(authenticate(email="l@example.com", password="S3cure-pass!"), user)
        self.assertIsNone(authenticate(email="l@example.com", password="wrong"))
        user.is_active = False
        user.save()
        self.assertIsNone(authenticate(email="l@example.com", password="S3cure-pass!"))

    def test_role_helpers(self):
        officer = User.objects.create_user("o@example.com", "S3cure-pass!", full_name="O", role=Role.OFFICER)
        self.assertTrue(officer.is_officer)
        self.assertFalse(officer.is_citizen)

    def test_lookup_by_email_is_case_insensitive(self):
        user = User.objects.create_user("look@example.com", "S3cure-pass!", full_name="Look")
        self.assertEqual(User.objects.get_by_natural_key("LOOK@Example.COM"), user)
