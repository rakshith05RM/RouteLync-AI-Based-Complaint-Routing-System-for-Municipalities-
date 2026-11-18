from .models import AuditLog


def log_action(user, action, *, target=None, summary="", details=None):
    """Record an important action. Called inside the same transaction as the change it describes."""
    return AuditLog.objects.create(
        user=user if getattr(user, "pk", None) else None, action=action,
        target_type=target.__class__.__name__ if target is not None else "",
        target_id=getattr(target, "pk", None), summary=summary[:255], details=details or {})
