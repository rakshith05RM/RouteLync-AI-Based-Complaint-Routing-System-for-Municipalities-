import csv
import os
import stat
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import Role, User
from departments.models import Department, FieldWorkerProfile, OfficerProfile

TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD = "chief@example.org", "Chief-Pass#2468"       # a throw-away pair used only by these tests


def run(*args, **options):
    out = StringIO()
    call_command("setup_staff_accounts", *args, stdout=out, **options)
    return out.getvalue()


@override_settings(DEBUG=True)            # the test runner switches DEBUG off; the command asks for confirmation when it is off
class StaffAccountFormatTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_master_data", stdout=StringIO())

    def setUp(self):
        cache.clear()

    def test_every_department_gets_an_officer_a_head_and_two_workers_in_the_standard_format(self):
        output = run()
        self.assertEqual(Department.objects.count(), 17)
        for dept in Department.objects.all():
            slug = dept.code.lower().replace("_", "")
            self.assertEqual(OfficerProfile.objects.filter(department=dept, is_department_head=False).count(), 1, dept.code)
            self.assertEqual(OfficerProfile.objects.filter(department=dept, is_department_head=True).count(), 1, dept.code)
            self.assertEqual(FieldWorkerProfile.objects.filter(department=dept).count(), 2, dept.code)
            for local, role in ((f"{slug}officer1", Role.OFFICER), (f"{slug}head1", Role.OFFICER),
                                (f"{slug}worker1", Role.FIELD_WORKER), (f"{slug}worker2", Role.FIELD_WORKER)):
                user = User.objects.get(email=f"{local}@company.com")
                self.assertEqual(user.role, role)
                self.assertTrue(user.check_password(f"{local}@company"), local)              # password = login name + @company
                self.assertTrue(user.is_active and user.email_verified)
                self.assertNotEqual(user.password, f"{local}@company")                       # stored hashed, never as text
        self.assertIn("68 accounts at @company.com", output)

    def test_examples_of_the_format(self):
        run()
        for email, password in (("electricityofficer1@company.com", "electricityofficer1@company"),
                                ("watersupplyworker2@company.com", "watersupplyworker2@company"),
                                ("civilregistrationhead1@company.com", "civilregistrationhead1@company"),
                                ("advertisementsworker1@company.com", "advertisementsworker1@company")):
            self.assertTrue(User.objects.get(email=email).check_password(password), email)

    def test_each_login_works_and_lands_on_the_right_page(self):
        run()
        landing = {"officer1": "/officer/", "head1": "/officer/", "worker1": "/worker/", "worker2": "/worker/"}
        for dept_code in ("ELECTRICITY", "PARKS_GARDENS", "SOCIAL_WELFARE"):
            slug = dept_code.lower().replace("_", "")
            for kind, page in landing.items():
                response = Client().post("/accounts/login/", {"username": f"{slug}{kind}@company.com", "password": f"{slug}{kind}@company.com".split(".com")[0]})
                self.assertEqual(response.status_code, 302, f"{slug}{kind}")
                self.assertIn(page, response["Location"])

    def test_the_domain_can_be_changed(self):
        run("--domain", "corp.example.in")
        self.assertTrue(User.objects.filter(email="roadsofficer1@corp.example.in").exists())
        self.assertTrue(User.objects.get(email="roadsworker2@corp.example.in").check_password("roadsworker2@corp"))
        with self.assertRaises(CommandError):
            run("--domain", "not a domain")

    def test_more_officers_and_workers_can_be_requested_but_not_fewer_than_one_and_two(self):
        run("--officers", "2", "--workers", "3")
        self.assertEqual(OfficerProfile.objects.filter(department__code="FIRE").count(), 3)        # 2 officers + the head
        self.assertEqual(FieldWorkerProfile.objects.filter(department__code="FIRE").count(), 3)
        with self.assertRaises(CommandError):
            run("--workers", "1")
        with self.assertRaises(CommandError):
            run("--officers", "0")

    def test_running_again_changes_nothing_and_keeps_changed_passwords(self):
        run()
        before = User.objects.count()
        user = User.objects.get(email="roadsofficer1@company.com")
        user.set_password("MyOwnNewPass#99")
        user.save()
        output = run()
        self.assertEqual(User.objects.count(), before)
        self.assertIn("68 already set up", output)
        user.refresh_from_db()
        self.assertTrue(user.check_password("MyOwnNewPass#99"))                          # not overwritten
        run("--reset-passwords")
        user.refresh_from_db()
        self.assertTrue(user.check_password("roadsofficer1@company"))

    def test_a_department_added_later_in_admin_gets_its_accounts_on_the_next_run(self):
        run()
        Department.objects.create(name="Burial Grounds", code="BURIAL_GROUNDS", description="added in Admin")
        run()
        for local in ("burialgroundsofficer1", "burialgroundshead1", "burialgroundsworker1", "burialgroundsworker2"):
            self.assertTrue(User.objects.filter(email=f"{local}@company.com").exists(), local)
        self.assertTrue(FieldWorkerProfile.objects.filter(department__code="BURIAL_GROUNDS").count() == 2)

    def test_worker_employee_codes_stay_unique(self):
        run("--workers", "4")
        codes = list(FieldWorkerProfile.objects.values_list("employee_code", flat=True))
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(len(codes), 17 * 4)

    def test_dry_run_saves_nothing(self):
        output = run("--dry-run")
        self.assertIn("DRY RUN", output)
        self.assertFalse(User.objects.filter(email__endswith="@company.com").exists())

    @override_settings(DEBUG=False)
    def test_outside_development_it_must_be_confirmed(self):
        with self.assertRaisesMessage(CommandError, "guessable pattern"):
            run()
        run("--allow-predictable-passwords")
        self.assertTrue(User.objects.filter(email="roadsofficer1@company.com").exists())

    def test_it_needs_departments(self):
        Department.objects.all().delete()
        with self.assertRaisesMessage(CommandError, "no departments"):
            run()


@override_settings(DEBUG=True)
class AdministratorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_master_data", stdout=StringIO())

    def setUp(self):
        cache.clear()

    def test_the_administrator_is_created_with_the_given_login(self):
        output = run("--admin-email", TEST_ADMIN_EMAIL, "--admin-password", TEST_ADMIN_PASSWORD)
        admin = User.objects.get(email=TEST_ADMIN_EMAIL)
        self.assertEqual((admin.role, admin.is_staff, admin.is_superuser, admin.is_active, admin.email_verified), (Role.ADMIN, True, True, True, True))
        self.assertTrue(admin.check_password(TEST_ADMIN_PASSWORD))
        self.assertNotIn(TEST_ADMIN_PASSWORD, output)                                       # the password is never echoed
        client = Client()
        self.assertEqual(client.post("/accounts/login/", {"username": TEST_ADMIN_EMAIL, "password": TEST_ADMIN_PASSWORD}).status_code, 302)
        self.assertEqual(client.get(reverse("adminpanel:dashboard")).status_code, 200)
        self.assertEqual(client.get("/admin/").status_code, 200)                            # the Django admin site as well

    def test_both_admin_options_are_needed_together(self):
        with self.assertRaises(CommandError):
            run("--admin-email", TEST_ADMIN_EMAIL)
        with self.assertRaises(CommandError):
            run("--admin-password", TEST_ADMIN_PASSWORD)

    @override_settings(DEBUG=True)
    def test_the_demo_administrator_is_renamed_not_left_behind(self):
        call_command("seed_master_data", "--demo-users", "--password", "Demo-Pass#12345", stdout=StringIO())
        demo = User.objects.get(email="admin@routelync.test")
        run("--admin-email", TEST_ADMIN_EMAIL, "--admin-password", TEST_ADMIN_PASSWORD)
        demo.refresh_from_db()
        self.assertEqual((demo.email, demo.role), (TEST_ADMIN_EMAIL, Role.ADMIN))             # the same account (same id and history)
        self.assertFalse(User.objects.filter(email="admin@routelync.test").exists())
        self.assertFalse(demo.check_password("Demo-Pass#12345"))

    def test_an_existing_account_with_that_email_becomes_the_administrator(self):
        User.objects.create_user(TEST_ADMIN_EMAIL, "Old-Pass#1234", full_name="Original Name", role=Role.CITIZEN)
        run("--admin-email", TEST_ADMIN_EMAIL, "--admin-password", TEST_ADMIN_PASSWORD)
        user = User.objects.get(email=TEST_ADMIN_EMAIL)
        self.assertEqual((user.role, user.full_name), (Role.ADMIN, "Original Name"))
        self.assertTrue(user.check_password(TEST_ADMIN_PASSWORD))


@override_settings(DEBUG=True)
class RenamingOldDemoAccountsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_master_data", "--demo-users", "--password", "Demo-Pass#12345", stdout=StringIO())

    def setUp(self):
        cache.clear()

    def test_old_demo_accounts_are_renamed_in_place_and_keep_their_history(self):
        old_officer = User.objects.get(email="officer.electricity@routelync.test")
        old_head = User.objects.get(email="head.roads@routelync.test")
        old_worker = User.objects.get(email="worker.ravi.kumar@routelync.test")
        profile_id = old_worker.worker_profile.pk
        output = run()
        for user, new_email in ((old_officer, "electricityofficer1@company.com"), (old_head, "roadshead1@company.com"),
                                (old_worker, "electricityworker1@company.com")):
            user.refresh_from_db()
            self.assertEqual(user.email, new_email)
            self.assertTrue(user.check_password(new_email.split(".com")[0]))
            self.assertFalse(user.check_password("Demo-Pass#12345"))                       # the known demo password is gone
        self.assertEqual(old_worker.worker_profile.pk, profile_id)                         # same profile, so assignments and complaints stay linked
        self.assertEqual(old_worker.full_name, "Ravi Kumar")
        self.assertFalse(User.objects.filter(email__startswith="officer.").exists())
        self.assertIn("renamed", output)
        self.assertEqual(Department.objects.count(), 17)

    def test_complaints_assigned_to_an_old_worker_follow_the_rename(self):
        from complaints.models import Complaint, ComplaintAssignment
        from complaints.tests.helpers import make_upload  # noqa: F401
        worker = User.objects.get(email="worker.ravi.kumar@routelync.test")
        citizen = User.objects.get(email="citizen@routelync.test")
        complaint = Complaint.objects.create(citizen=citizen, title="Old complaint", description="Streetlight not working near the junction",
                                             department=worker.worker_profile.department, status="ASSIGNED_TO_WORKER")
        ComplaintAssignment.objects.create(complaint=complaint, assigned_to=worker, assigned_by=User.objects.get(email="officer.electricity@routelync.test"))
        run()
        assignment = ComplaintAssignment.objects.get(complaint=complaint)
        self.assertEqual(assignment.assigned_to.email, "electricityworker1@company.com")

    def test_leftover_demo_accounts_are_reported_and_can_be_switched_off(self):
        User.objects.filter(email="worker.ravi.kumar@routelync.test").update(role=Role.CITIZEN)   # not renamable: wrong role
        output = run()
        self.assertIn("Old demo accounts not renamed", output)
        run("--deactivate-legacy")
        self.assertFalse(User.objects.get(email="worker.ravi.kumar@routelync.test").is_active)


@override_settings(DEBUG=True)
class CredentialsFileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_master_data", stdout=StringIO())

    def test_the_csv_lists_every_login(self):
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "credentials.csv")
        run("--admin-email", TEST_ADMIN_EMAIL, "--admin-password", TEST_ADMIN_PASSWORD, "--csv", path)
        with open(path, encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 69)
        self.assertEqual(rows[0]["Role"], "Administrator")
        by_email = {r["Email (login)"]: r for r in rows}
        self.assertEqual(by_email["electricityofficer1@company.com"]["Password"], "electricityofficer1@company")
        self.assertEqual(by_email["trafficparkingworker2@company.com"]["Role"], "Worker")
        self.assertEqual(by_email["trafficparkingworker2@company.com"]["Department"], "Traffic & Parking")
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)                    # readable only by its owner

    def test_unchanged_passwords_are_not_written_down(self):
        import tempfile
        run()
        path = os.path.join(tempfile.mkdtemp(), "again.csv")
        run("--csv", path)
        with open(path, encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual({r["Password"] for r in rows}, {"(unchanged)"})
