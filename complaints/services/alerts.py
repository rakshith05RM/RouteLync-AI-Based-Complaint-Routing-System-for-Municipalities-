"""
Who is told what, and when. Messages sent to citizens use plain wording only: no priority, no AI
details, no internal staff names.
"""
from django.urls import reverse

from notifications.services import administrators, department_officers, notify, notify_many  # noqa: F401


def _citizen_link(c):
    return reverse("complaints:detail", args=[c.pk])


def _officer_link(c):
    return reverse("officer:detail", args=[c.pk])


def _admin_link(c):
    return reverse("adminpanel:complaint", args=[c.pk])


def to_citizen(c, kind, message):
    notify(c.citizen, message, link=_citizen_link(c), kind=kind, complaint_id=c.pk)


def to_department_officers(c, kind, message, heads_only=False):
    if c.department_id:
        notify_many(department_officers(c.department, heads_only), message, link=_officer_link(c), kind=kind, complaint_id=c.pk)


def to_worker(c, worker, kind, message):
    notify(worker, message, link=reverse("worker:detail", args=[c.pk]), kind=kind, complaint_id=c.pk)


def to_administrators(c, kind, message):
    notify_many(administrators(), message, link=_admin_link(c), kind=kind, complaint_id=c.pk)
