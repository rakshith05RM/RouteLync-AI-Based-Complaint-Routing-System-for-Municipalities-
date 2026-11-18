from .models import OfficerProfile, FieldWorkerProfile, Priority, SLAConfiguration
from accounts.models import Role

# Example defaults only: NOT real municipal regulations. Administrators can change them.
DEFAULT_SLA_HOURS = {Priority.CRITICAL: 4, Priority.HIGH: 12, Priority.MEDIUM: 24, Priority.LOW: 72}


def department_for(user):
    """The Department an officer or field worker belongs to, or None (also None for other roles)."""
    if not user.is_authenticated:
        return None
    if user.role == Role.OFFICER:
        profile = OfficerProfile.objects.select_related("department").filter(user=user).first()
    elif user.role == Role.FIELD_WORKER:
        profile = FieldWorkerProfile.objects.select_related("department").filter(user=user).first()
    else:
        return None
    return profile.department if profile else None


def sla_hours_for(priority: str) -> int:
    """Configured SLA hours for a priority; falls back to the example default if no row exists."""
    row = SLAConfiguration.objects.filter(priority=priority).first()
    return row.hours if row else DEFAULT_SLA_HOURS[Priority(priority)]
