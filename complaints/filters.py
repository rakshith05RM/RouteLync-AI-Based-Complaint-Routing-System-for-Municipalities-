"""
Officer dashboard filtering, searching and sorting.

All input arrives as GET parameters and is validated by a Django form, so a bad value (ward=abc,
a nonsense date) is reported to the officer instead of crashing the page. Every database
condition is built with the ORM, never with string-built SQL.
"""
import re
from datetime import datetime, time, timedelta

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Case, Exists, F, IntegerField, OuterRef, Q, Value, When
from django.utils import timezone

from departments.models import Area, Priority, Ward

from .forms import WardChoiceField, WardSelect
from .models import (ACTIVE_STATUSES, CLOSED_STATUSES, STATUS_ORDER, ComplaintAssignment, ComplaintStatus as S,
                     Resolution, ResolutionOutcome, DuplicateFlag, DuplicateStatus)

# Officers never see complaints before routing, so those statuses are not offered.
OFFICER_STATUS_CHOICES = [(s.value, s.label) for s in STATUS_ORDER if s not in (S.SUBMITTED, S.AI_PROCESSING, S.NEEDS_VERIFICATION)]
SORT_CHOICES = [("priority", "Priority, most urgent first"), ("newest", "Newest first"), ("oldest", "Oldest first"),
                ("sla", "SLA deadline"), ("status", "Status"), ("area", "Area"), ("ward", "Ward")]
PRIORITY_RANK = {Priority.CRITICAL: 4, Priority.HIGH: 3, Priority.MEDIUM: 2, Priority.LOW: 1}
_ID_SEARCH = re.compile(r"(?i)^(?:rl-?)?0*(\d{1,9})$")


class OfficerFilterForm(forms.Form):
    q = forms.CharField(required=False, max_length=100, label="Search",
                        widget=forms.TextInput(attrs={"placeholder": "Complaint ID, citizen name, street, area or keyword"}))
    area = forms.ModelChoiceField(queryset=Area.objects.all(), required=False, empty_label="All areas")
    ward = WardChoiceField(queryset=Ward.objects.select_related("area"), required=False, empty_label="All wards",
                           widget=WardSelect)
    street = forms.CharField(required=False, max_length=150, widget=forms.TextInput(attrs={"list": "street-list"}))
    status = forms.ChoiceField(required=False,
                               choices=[("", "Open complaints"), ("ALL", "All statuses")] + OFFICER_STATUS_CHOICES)
    priority = forms.ChoiceField(required=False, choices=[("", "Any priority")] + list(Priority.choices))
    date_from = forms.DateField(required=False, label="From", widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(required=False, label="To", widget=forms.DateInput(attrs={"type": "date"}))
    min_confidence = forms.IntegerField(required=False, min_value=0, max_value=100, label="AI confidence at least (%)")
    overdue = forms.BooleanField(required=False, label="Overdue only")
    escalation = forms.ChoiceField(required=False, label="Escalation",
                                   choices=[("", "Any"), ("any", "Escalated"), ("1", "Department Head"), ("2", "Administrator")])
    assigned_to = forms.ChoiceField(required=False, label="Assigned to")
    awaiting_verification = forms.BooleanField(required=False, label="Awaiting my verification")
    duplicates = forms.BooleanField(required=False, label="Possible duplicates")
    sort = forms.ChoiceField(required=False, choices=SORT_CHOICES)

    def __init__(self, *args, department=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [("", "Anyone"), ("none", "Unassigned")]
        if department is not None:
            workers = get_user_model().objects.filter(worker_profile__department=department).order_by("full_name")
            choices += [(str(u.pk), u.full_name) for u in workers]
        self.fields["assigned_to"].choices = choices

    def clean(self):
        cleaned = super().clean()
        area, ward = cleaned.get("area"), cleaned.get("ward")
        if area and ward and ward.area_id != area.id:
            self.add_error("ward", f"Ward {ward.number} is not in {area.name}.")
        start, end = cleaned.get("date_from"), cleaned.get("date_to")
        if start and end and start > end:
            self.add_error("date_to", "The end date is before the start date.")
        return cleaned

    @property
    def is_filtered(self) -> bool:
        data = getattr(self, "cleaned_data", {})
        return any(data.get(k) for k in ("q", "area", "ward", "street", "status", "priority", "date_from",
                                         "date_to", "min_confidence", "overdue", "assigned_to", "escalation",
                                         "awaiting_verification", "duplicates"))

    # ------------------------------------------------------------------ applying
    def apply(self, queryset, now=None):
        self.is_valid()                       # runs validation; invalid fields are simply left out of cleaned_data
        d = self.cleaned_data
        now = now or timezone.now()
        qs = queryset

        status = d.get("status")
        if not status:
            qs = qs.exclude(status__in=CLOSED_STATUSES)       # default view: work that is still open
        elif status != "ALL":
            qs = qs.filter(status=status)
        if d.get("area"):
            qs = qs.filter(location__area=d["area"])
        if d.get("ward"):
            qs = qs.filter(location__ward=d["ward"])
        if d.get("street"):
            qs = qs.filter(location__street__iexact=d["street"].strip())
        if d.get("priority"):
            qs = qs.filter(priority=d["priority"])
        if d.get("date_from"):
            qs = qs.filter(created_at__gte=self._day_start(d["date_from"]))
        if d.get("date_to"):                                   # inclusive of the whole end day
            qs = qs.filter(created_at__lt=self._day_start(d["date_to"] + timedelta(days=1)))
        if d.get("min_confidence") is not None:
            qs = qs.filter(ai_confidence__gte=d["min_confidence"] / 100)
        if d.get("overdue"):
            qs = qs.filter(status__in=ACTIVE_STATUSES, sla_deadline__lt=now)
        if d.get("escalation") == "any":
            qs = qs.filter(escalation_level__gt=0)
        elif d.get("escalation"):
            qs = qs.filter(escalation_level=int(d["escalation"]))
        if d.get("assigned_to") == "none":
            qs = qs.exclude(Exists(ComplaintAssignment.objects.filter(complaint=OuterRef("pk"), ended_at__isnull=True)))
        elif d.get("assigned_to"):
            qs = qs.filter(assignments__assigned_to_id=int(d["assigned_to"]), assignments__ended_at__isnull=True)
        if d.get("awaiting_verification"):
            qs = qs.filter(status=S.IN_PROGRESS, resolutions__outcome=ResolutionOutcome.PENDING_VERIFICATION).distinct()
        if d.get("duplicates"):
            qs = qs.filter(Exists(DuplicateFlag.objects.filter(complaint=OuterRef("pk"), status=DuplicateStatus.PENDING)))
        if d.get("q"):
            qs = self._search(qs, d["q"])
        return self._sort(qs, d.get("sort") or "priority")

    @staticmethod
    def _day_start(day):
        # Plain datetime bounds instead of created_at__date: the __date lookup needs MySQL time-zone
        # tables to be loaded and silently misbehaves without them.
        return timezone.make_aware(datetime.combine(day, time.min))

    @staticmethod
    def _search(qs, text):
        match = _ID_SEARCH.match(text.strip())
        if match:                                              # "RL-000123" or "123"
            return qs.filter(pk=int(match.group(1)))
        for term in text.split()[:6]:                          # every word must match somewhere
            qs = qs.filter(
                Q(title__icontains=term) | Q(description__icontains=term)
                | Q(citizen__full_name__icontains=term) | Q(location__street__icontains=term)
                | Q(location__landmark__icontains=term) | Q(location__area__name__icontains=term))
        return qs

    @staticmethod
    def _sort(qs, key):
        priority_rank = Case(*[When(priority=p, then=Value(r)) for p, r in PRIORITY_RANK.items()],
                             default=Value(0), output_field=IntegerField())
        status_rank = Case(*[When(status=s, then=Value(i)) for i, s in enumerate(STATUS_ORDER)],
                           default=Value(99), output_field=IntegerField())
        if key == "newest":
            return qs.order_by("-created_at", "-id")
        if key == "oldest":
            return qs.order_by("created_at", "id")
        if key == "sla":
            return qs.order_by(F("sla_deadline").asc(nulls_last=True), "-created_at")
        if key == "status":
            return qs.annotate(_status_rank=status_rank).order_by("_status_rank", "-created_at")
        if key == "area":
            return qs.order_by("location__area__name", "location__ward__number", "-created_at")
        if key == "ward":
            return qs.order_by("location__ward__number", "location__area__name", "-created_at")
        return qs.annotate(_priority_rank=priority_rank).order_by(           # "priority" (default)
            "-_priority_rank", F("sla_deadline").asc(nulls_last=True), "-created_at")


def sort_complaints(queryset, key):
    return OfficerFilterForm._sort(queryset, key)
