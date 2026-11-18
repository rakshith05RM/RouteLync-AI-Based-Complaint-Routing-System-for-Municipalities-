"""Administrator actions on users, departments, SLA settings, models and datasets. Each one is audited."""
from django.db import transaction

from accounts.models import CitizenProfile, Role, User
from audit.services import log_action
from complaints.models import ACTIVE_STATUSES, Complaint
from complaints.services import WorkflowError
from departments.models import Department, FieldWorkerProfile, OfficerProfile, SLAConfiguration
from departments.services import sla_hours_for
from ml_engine.dataset import import_rows
from ml_engine.exceptions import MLEngineError
from ml_engine.models import MLModel
from ml_engine.train import train_and_evaluate


@transaction.atomic
def create_staff(actor, data) -> User:
    role = data["role"]
    user = User.objects.create_user(data["email"], data["password"], full_name=data["full_name"], phone=data["phone"], role=role,
                                    is_staff=(role == Role.ADMIN))
    dept = data.get("department")
    if role == Role.OFFICER:
        OfficerProfile.objects.create(user=user, department=dept, designation=data.get("designation", ""))
    elif role == Role.FIELD_WORKER:
        code = data.get("employee_code") or f"{dept.code[:3]}-{user.pk:04d}"
        if FieldWorkerProfile.objects.filter(employee_code=code).exists():
            raise WorkflowError("That employee code is already used.")
        FieldWorkerProfile.objects.create(user=user, department=dept, employee_code=code)
    log_action(actor, "USER_CREATED", target=user, summary=f"{user.get_role_display()} account created for {user.full_name}",
               details={"role": role, "department": dept.code if dept else ""})
    return user


@transaction.atomic
def set_user_active(actor, user, active: bool):
    if user.pk == actor.pk:
        raise WorkflowError("You cannot change your own account here.")
    if not active and user.role == Role.ADMIN and User.objects.filter(role=Role.ADMIN, is_active=True).exclude(pk=user.pk).count() == 0:
        raise WorkflowError("There must be at least one active administrator.")
    user.is_active = active
    user.save(update_fields=["is_active", "updated_at"])
    log_action(actor, "USER_ACTIVATED" if active else "USER_DEACTIVATED", target=user, summary=f"{user.full_name} {'activated' if active else 'deactivated'}")


@transaction.atomic
def set_worker_available(actor, user, available: bool):
    profile = FieldWorkerProfile.objects.filter(user=user).first()
    if profile is None:
        raise WorkflowError("That person is not a field worker.")
    profile.is_available = available
    profile.save()
    log_action(actor, "WORKER_AVAILABILITY", target=user, summary=f"{user.full_name} marked {'available' if available else 'unavailable'}")


@transaction.atomic
def set_department_head(actor, user):
    profile = OfficerProfile.objects.select_related("department").filter(user=user).first()
    if profile is None:
        raise WorkflowError("That person is not a department officer.")
    OfficerProfile.objects.filter(department=profile.department, is_department_head=True).exclude(pk=profile.pk).update(is_department_head=False)
    profile.is_department_head = True
    profile.save()
    log_action(actor, "DEPARTMENT_HEAD_SET", target=user, summary=f"{user.full_name} is now head of {profile.department.name}")


@transaction.atomic
def create_department(actor, data) -> Department:
    dept = Department.objects.create(name=data["name"], code=data["code"], description=data.get("description", ""))
    log_action(actor, "DEPARTMENT_CREATED", target=dept, summary=f"Department {dept.name} created")
    return dept


@transaction.atomic
def set_department_active(actor, dept, active: bool):
    if not active and Complaint.objects.filter(department=dept, status__in=ACTIVE_STATUSES).exists():
        raise WorkflowError("This department still has active complaints. Move them to another department first.")
    dept.is_active = active
    dept.save(update_fields=["is_active"])
    log_action(actor, "DEPARTMENT_ACTIVATED" if active else "DEPARTMENT_DEACTIVATED", target=dept, summary=f"{dept.name} {'activated' if active else 'deactivated'}")


@transaction.atomic
def update_sla(actor, hours_by_priority: dict):
    changed = {}
    for priority, hours in hours_by_priority.items():
        current = sla_hours_for(priority)                      # the value in force now (configured, or the built-in default)
        row, _ = SLAConfiguration.objects.get_or_create(priority=priority, defaults={"hours": hours})
        if current != hours:
            changed[priority] = [current, hours]
            row.hours = hours
            row.save()
    if changed:
        log_action(actor, "SLA_CHANGED", summary="SLA hours changed (applies to new complaints)", details=changed)
    return changed


def train_new_model(actor, notes="") -> MLModel:
    try:
        return train_and_evaluate(user=actor, notes=notes or "Trained from the administrator panel").ml_model
    except MLEngineError as exc:
        raise WorkflowError(str(exc))


@transaction.atomic
def set_threshold(actor, model: MLModel, value: float):
    old = model.conf_threshold
    model.conf_threshold = round(value, 2)
    model.save(update_fields=["conf_threshold"])
    log_action(actor, "THRESHOLD_CHANGED", target=model, summary=f"Model v{model.version} threshold {old} -> {model.conf_threshold}")


@transaction.atomic
def import_dataset(actor, rows, *, version="", dry_run=True):
    report = import_rows(rows, version=version, dry_run=dry_run)
    if not dry_run and report.imported:
        log_action(actor, "DATASET_IMPORTED", summary=f"{report.imported} training examples imported", details={"version": version, "rows": report.rows_read})
    return report
