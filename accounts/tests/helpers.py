from django.contrib.auth import get_user_model

from accounts.models import Role
from departments.models import Department, FieldWorkerProfile, OfficerProfile

User = get_user_model()
PASSWORD = "Str0ng-Pass!word"


def make_department(code="ELECTRICITY", name=None):
    name = name or code.replace("_", " ").title()
    return Department.objects.get_or_create(code=code, defaults={"name": name})[0]


def make_user(email="user@example.com", role=Role.CITIZEN, department=None, **extra):
    """Create a user; officers and field workers automatically get a profile in `department`
    (default: Electricity)."""
    extra.setdefault("full_name", "Test User")
    if role == Role.ADMIN:
        extra.setdefault("is_staff", True)
    user = User.objects.create_user(email, PASSWORD, role=role, **extra)
    if role in (Role.OFFICER, Role.FIELD_WORKER):
        department = department or make_department()
        if role == Role.OFFICER:
            OfficerProfile.objects.create(user=user, department=department)
        else:
            FieldWorkerProfile.objects.create(user=user, department=department, employee_code=f"E{user.pk:05d}")
    return user
