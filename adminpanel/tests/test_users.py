from django.contrib.auth import authenticate
from django.urls import reverse

from accounts.models import Role, User
from accounts.tests.helpers import PASSWORD, make_user
from adminpanel import services
from audit.models import AuditLog
from complaints.services import WorkflowError
from departments.models import FieldWorkerProfile, OfficerProfile

from .helpers import AdminTestCase

NEW_PW = "Fresh-Staff#2026"


class StaffCreationTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.as_admin()
        self.url = reverse("adminpanel:user_new")

    def data(self, **over):
        d = {"full_name": "Meera Nair", "email": "Meera@Example.com", "phone": "9876543210", "role": Role.OFFICER,
             "department": self.water.pk, "designation": "Assistant Engineer", "employee_code": "", "password": NEW_PW}
        d.update(over)
        return d

    def test_officer_gets_a_profile_in_the_chosen_department(self):
        self.assertRedirects(self.client.post(self.url, self.data()), reverse("adminpanel:users"))
        user = User.objects.get(email="meera@example.com")
        self.assertEqual((user.role, user.officer_profile.department, user.officer_profile.designation), (Role.OFFICER, self.water, "Assistant Engineer"))
        self.assertFalse(user.is_staff)
        self.assertTrue(authenticate(email="meera@example.com", password=NEW_PW))
        self.assertTrue(AuditLog.objects.filter(action="USER_CREATED", target_id=user.pk).exists())

    def test_field_worker_gets_an_employee_code(self):
        self.client.post(self.url, self.data(role=Role.FIELD_WORKER, email="w@example.com"))
        profile = FieldWorkerProfile.objects.get(user__email="w@example.com")
        self.assertEqual((profile.department, profile.is_available), (self.water, True))
        self.assertRegex(profile.employee_code, r"^WAT-\d{4}$")
        self.client.post(self.url, self.data(role=Role.FIELD_WORKER, email="w2@example.com", employee_code="EL-777"))
        self.assertTrue(FieldWorkerProfile.objects.filter(employee_code="EL-777").exists())

    def test_duplicate_worker_code_is_refused_and_nothing_is_left_behind(self):
        self.client.post(self.url, self.data(role=Role.FIELD_WORKER, email="a@example.com", employee_code="X-1"))
        response = self.client.post(self.url, self.data(role=Role.FIELD_WORKER, email="b@example.com", employee_code="X-1"))
        self.assertContains(response, "already used")
        self.assertFalse(User.objects.filter(email="b@example.com").exists())

    def test_administrator_account_has_django_admin_access(self):
        self.client.post(self.url, self.data(role=Role.ADMIN, department="", email="boss@example.com"))
        user = User.objects.get(email="boss@example.com")
        self.assertEqual((user.role, user.is_staff, user.is_superuser), (Role.ADMIN, True, False))

    def test_validation(self):
        for bad in ({"email": self.officer.email}, {"email": "not-an-email"}, {"phone": "12345"}, {"full_name": "R2D2 <b>"},
                    {"password": "12345678"}, {"password": "short"}, {"department": ""}, {"role": "SUPERUSER"}):
            before = User.objects.count()
            self.assertEqual(self.client.post(self.url, self.data(**bad)).status_code, 200, bad)
            self.assertEqual(User.objects.count(), before, bad)

    def test_inactive_department_cannot_be_chosen(self):
        self.water.is_active = False
        self.water.save()
        self.client.post(self.url, self.data())
        self.assertFalse(User.objects.filter(email="meera@example.com").exists())


class UserManagementTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.as_admin()

    def act(self, user, action):
        return self.client.post(reverse("adminpanel:user_action", args=[user.pk, action]), follow=True)

    def test_deactivated_user_cannot_log_in_and_can_be_restored(self):
        self.act(self.worker, "deactivate")
        self.worker.refresh_from_db()
        self.assertFalse(self.worker.is_active)
        self.assertIsNone(authenticate(email="worker1@example.com", password=PASSWORD))
        self.act(self.worker, "activate")
        self.assertTrue(authenticate(email="worker1@example.com", password=PASSWORD))
        self.assertEqual(AuditLog.objects.filter(action__in=["USER_DEACTIVATED", "USER_ACTIVATED"]).count(), 2)

    def test_cannot_deactivate_yourself_or_the_last_administrator(self):
        self.assertContains(self.act(self.admin, "deactivate"), "cannot change your own account")
        other = make_user("admin2@example.com", Role.ADMIN)
        services.set_user_active(self.admin, other, False)
        with self.assertRaisesMessage(WorkflowError, "at least one active administrator"):
            services.set_user_active(other, self.admin, False) if False else services.set_user_active(make_user("x@example.com", Role.CITIZEN), self.admin, False)

    def test_worker_availability_controls_assignment(self):
        self.act(self.worker, "unavailable")
        self.assertFalse(FieldWorkerProfile.objects.get(user=self.worker).is_available)
        page = self.client.get(reverse("officer:detail", args=[self.complaint.pk])) if False else None
        self.client.force_login(self.officer)
        picker = self.client.get(reverse("officer:detail", args=[self.complaint.pk])).content.decode()
        self.assertNotIn("Ravi Kumar", picker)
        self.client.force_login(self.admin)
        self.act(self.worker, "available")
        self.client.force_login(self.officer)
        self.assertIn("Ravi Kumar", self.client.get(reverse("officer:detail", args=[self.complaint.pk])).content.decode())

    def test_availability_only_for_field_workers(self):
        self.assertContains(self.act(self.citizen, "available"), "not a field worker")

    def test_making_a_head_replaces_the_previous_one(self):
        second = make_user("o2@example.com", Role.OFFICER, department=self.elec)
        self.act(self.officer, "make_head")
        self.act(second, "make_head")
        heads = OfficerProfile.objects.filter(department=self.elec, is_department_head=True)
        self.assertEqual([h.user for h in heads], [second])
        self.assertContains(self.act(self.citizen, "make_head"), "not a department officer")

    def test_unknown_action_and_unknown_user(self):
        self.assertContains(self.act(self.worker, "delete_everything"), "Unknown action")
        self.assertEqual(self.client.post(reverse("adminpanel:user_action", args=[99999, "activate"])).status_code, 404)

    def test_list_filters_and_search(self):
        page = lambda **p: [u.email for u in self.client.get(reverse("adminpanel:users"), p).context["users"]]
        self.assertEqual(set(page(role="FIELD_WORKER")), {"worker1@example.com", "worker2@example.com", "water.worker@example.com"})
        self.assertEqual(page(q="manoj"), ["worker2@example.com"])
        self.worker.is_active = False
        self.worker.save()
        self.assertEqual(page(role="FIELD_WORKER", active="no"), ["worker1@example.com"])
        self.assertEqual(page(q="' OR 1=1 --"), [])
