from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from accounts.models import Role
from accounts.tests.helpers import make_department, make_user
from departments.models import Area, Department, FieldWorkerProfile, OfficerProfile, Priority, SLAConfiguration, Ward
from departments.services import DEFAULT_SLA_HOURS, department_for, sla_hours_for


class DepartmentTests(TestCase):
    def test_code_must_be_upper_snake_case_and_unique(self):
        bad = Department(name="X", code="water supply")
        with self.assertRaises(ValidationError):
            bad.full_clean()
        make_department("ROADS")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Department.objects.create(name="Roads 2", code="ROADS")

    def test_cannot_delete_department_that_has_officers(self):
        dept = make_department()
        make_user("o@example.com", Role.OFFICER, department=dept)
        with self.assertRaises(ProtectedError):
            dept.delete()


class GeographyTests(TestCase):
    def test_ward_number_unique_within_area_but_reusable_across_areas(self):
        a, b = Area.objects.create(name="A"), Area.objects.create(name="B")
        Ward.objects.create(area=a, number=5)
        Ward.objects.create(area=b, number=5)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ward.objects.create(area=a, number=5)

    def test_ward_number_must_be_positive(self):
        area = Area.objects.create(name="A")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ward.objects.create(area=area, number=0)

    def test_area_with_wards_cannot_be_deleted(self):
        area = Area.objects.create(name="A")
        Ward.objects.create(area=area, number=1)
        with self.assertRaises(ProtectedError):
            area.delete()


class ProfileTests(TestCase):
    def setUp(self):
        self.dept = make_department()

    def test_officer_profile_requires_officer_role(self):
        citizen = make_user("c@example.com", Role.CITIZEN)
        with self.assertRaises(ValidationError):
            OfficerProfile.objects.create(user=citizen, department=self.dept)

    def test_worker_profile_requires_worker_role(self):
        officer = make_user("o@example.com", Role.OFFICER)
        with self.assertRaises(ValidationError):
            FieldWorkerProfile.objects.create(user=officer, department=self.dept, employee_code="X1")

    def test_only_one_head_per_department(self):
        first = make_user("h1@example.com", Role.OFFICER, department=self.dept)
        first_profile = first.officer_profile
        first_profile.is_department_head = True
        first_profile.save()
        second = make_user("h2@example.com", Role.OFFICER, department=self.dept).officer_profile
        second.is_department_head = True
        with self.assertRaises(ValidationError):
            second.save()
        # another department may have its own head
        other = make_user("h3@example.com", Role.OFFICER, department=make_department("ROADS")).officer_profile
        other.is_department_head = True
        other.save()

    def test_employee_code_unique(self):
        u1 = make_user("w1@example.com", Role.FIELD_WORKER, department=self.dept)
        u2 = make_user("w2@example.com", Role.FIELD_WORKER, department=self.dept)
        p2 = u2.worker_profile
        p2.employee_code = u1.worker_profile.employee_code
        with self.assertRaises(ValidationError):
            p2.save()

    def test_department_for_user(self):
        o = make_user("o@example.com", Role.OFFICER, department=self.dept)
        w = make_user("w@example.com", Role.FIELD_WORKER, department=self.dept)
        c = make_user("c@example.com", Role.CITIZEN)
        self.assertEqual(department_for(o), self.dept)
        self.assertEqual(department_for(w), self.dept)
        self.assertIsNone(department_for(c))


class SLATests(TestCase):
    def test_priority_unique_and_hours_positive(self):
        SLAConfiguration.objects.create(priority=Priority.HIGH, hours=10)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SLAConfiguration.objects.create(priority=Priority.HIGH, hours=5)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SLAConfiguration.objects.create(priority=Priority.LOW, hours=0)

    def test_configured_value_wins_and_default_is_fallback(self):
        self.assertEqual(sla_hours_for(Priority.CRITICAL), DEFAULT_SLA_HOURS[Priority.CRITICAL])
        SLAConfiguration.objects.create(priority=Priority.CRITICAL, hours=2)
        self.assertEqual(sla_hours_for(Priority.CRITICAL), 2)
