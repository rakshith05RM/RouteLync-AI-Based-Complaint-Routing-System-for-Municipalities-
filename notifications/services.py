"""Creating notifications. This module knows nothing about complaints beyond an optional id."""
from django.contrib.auth import get_user_model

from accounts.models import Role
from departments.models import OfficerProfile


def notify(user, message, *, link="", kind="", complaint_id=None):
    if user is None or not user.is_active:
        return None
    from . import delivery
    from .models import Notification
    notification = Notification.objects.create(recipient=user, message=message[:255], link=link[:200], kind=kind[:40], complaint_id=complaint_id)
    delivery.schedule(user, notification.message, notification.link)     # email / WhatsApp, after the transaction commits
    return notification


def notify_many(users, message, **kwargs):
    seen = set()
    for user in users:
        if user.pk not in seen:
            seen.add(user.pk)
            notify(user, message, **kwargs)


def department_officers(department, heads_only=False):
    qs = get_user_model().objects.filter(officer_profile__department=department, is_active=True)
    return qs.filter(officer_profile__is_department_head=True) if heads_only else qs


def administrators():
    return get_user_model().objects.filter(role=Role.ADMIN, is_active=True)
