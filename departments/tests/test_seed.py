from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from accounts.models import Role, User
from departments.models import Area, Department, FieldWorkerProfile, OfficerProfile, SLAConfiguration, Ward


class SeedCommandTests(TestCase):
    def test_seed_is_idempotent(self):
        area_count = Area.objects.count()
        call_command("seed_master_data", verbosity=0)
        counts = (Department.objects.count(), Area.objects.count(), Ward.objects.count(), SLAConfiguration.objects.count())
        call_command("seed_master_data", verbosity=0)
        self.assertEqual(counts, (17, area_count + 4, 12, 4))
        self.assertEqual(counts, (Department.objects.count(), Area.objects.count(), Ward.objects.count(),
                                  SLAConfiguration.objects.count()))
        self.assertTrue(Ward.objects.filter(number=154, area__name="Jayanagar").exists())

    def test_demo_users_need_password_and_debug(self):
        with override_settings(DEBUG=True), self.assertRaises(CommandError):
            call_command("seed_master_data", "--demo-users", verbosity=0)
        with override_settings(DEBUG=False), self.assertRaises(CommandError):
            call_command("seed_master_data", "--demo-users", "--password", "x", verbosity=0)

    @override_settings(DEBUG=True)
    def test_demo_users_created_correctly_and_idempotently(self):
        for _ in range(2):
            call_command("seed_master_data", "--demo-users", "--password", "Demo-Pass#12345", verbosity=0)
        self.assertEqual(OfficerProfile.objects.count(), 34)            # officer + head x 17 departments
        self.assertEqual(OfficerProfile.objects.filter(is_department_head=True).count(), 17)
        self.assertEqual(FieldWorkerProfile.objects.count(), 34)
        self.assertEqual(User.objects.filter(role=Role.ADMIN).count(), 1)
        officer = User.objects.get(email="officer.electricity@routelync.test")
        self.assertTrue(officer.check_password("Demo-Pass#12345"))
        self.assertEqual(officer.officer_profile.department.code, "ELECTRICITY")
        self.assertTrue(FieldWorkerProfile.objects.filter(user__full_name="Ravi Kumar", department__code="ELECTRICITY").exists())


class DemoAccountsCanSignInTests(TestCase):
    """Demo accounts are made by a script, so they must not be stuck behind the email-verification step."""

    @override_settings(DEBUG=True)
    def test_every_demo_role_can_sign_in(self):
        from django.core.cache import cache
        cache.clear()
        call_command("seed_master_data", "--demo-users", "--password", "Demo-Pass#12345", stdout=__import__("io").StringIO())
        for email in ("citizen@routelync.test", "officer.electricity@routelync.test", "worker.ravi.kumar@routelync.test", "admin@routelync.test"):
            user = User.objects.get(email=email)
            self.assertTrue(user.email_verified, email)
            client = self.client_class()
            response = client.post("/accounts/login/", {"username": email, "password": "Demo-Pass#12345"})
            self.assertEqual(response.status_code, 302, email)
            self.assertNotIn("verify-email", response["Location"], email)
