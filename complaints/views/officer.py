"""
Officer (department) dashboard. Every query starts from complaints_visible_to(user) and is narrowed
again by DepartmentScopedMixin, so an officer can only ever see their own department's complaints.
"""
from django.contrib import messages
from django.db.models import Exists, OuterRef, Prefetch
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView, View

from accounts.models import Role
from departments.mixins import DepartmentScopedMixin
from departments.models import Area, OfficerProfile, Ward

from ..filters import OfficerFilterForm
from ..models import ACTIVE_STATUSES, ComplaintAssignment, DuplicateFlag, DuplicateStatus, ComplaintStatus as S, RemarkVisibility, Resolution, ResolutionOutcome
from ..presenters import duplicate_panel
from ..selectors import complaints_visible_to, location_breakdown, officer_summary
from ..services import (WorkflowError, add_remark, assign_worker, change_priority, escalate_complaint, reject_complaint,
                        review_duplicate, review_resolution, unassign_worker)
from ..services.workflow import ASSIGNABLE
from ..workflow_forms import AssignWorkerForm, EscalateForm, PriorityForm, RejectForm, RemarkForm, ReviewForm

MAP_MARKER_LIMIT = 500


class OfficerMixin(DepartmentScopedMixin):
    allowed_roles = (Role.OFFICER,)
    active_tab = ""

    @property
    def is_head(self) -> bool:
        profile = OfficerProfile.objects.filter(user=self.request.user).first()
        return bool(profile and profile.is_department_head)

    def scoped(self):
        return self.scope_queryset(complaints_visible_to(self.request.user))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_tab"] = self.active_tab
        return ctx


def with_assignment_info(queryset):
    """Adds the current worker and the 'awaiting verification' flag to every row without extra queries."""
    active = Prefetch("assignments", queryset=ComplaintAssignment.objects.filter(ended_at__isnull=True).select_related("assigned_to"),
                      to_attr="active_assignment_list")
    awaiting = Exists(Resolution.objects.filter(complaint=OuterRef("pk"), outcome=ResolutionOutcome.PENDING_VERIFICATION))
    duplicate = Exists(DuplicateFlag.objects.filter(complaint=OuterRef("pk"), status=DuplicateStatus.PENDING))
    return queryset.prefetch_related(active).annotate(awaiting_verification=awaiting, possible_duplicate=duplicate)


class DashboardView(OfficerMixin, ListView):
    template_name = "officer/dashboard.html"
    context_object_name = "complaints"
    paginate_by = 15
    active_tab = "complaints"

    def get_queryset(self):
        self.form = OfficerFilterForm(self.request.GET, department=self.department)
        base = with_assignment_info(self.scoped().select_related("location__area", "location__ward", "citizen"))
        return self.form.apply(base)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        now = timezone.now()
        scoped = self.scoped()
        streets = {}
        for name in scoped.values_list("location__street", flat=True).distinct()[:300]:
            streets.setdefault(name.lower(), name)
        ctx.update(form=self.form, summary=officer_summary(scoped, now), streets=sorted(streets.values()),
                   is_filtered=self.form.is_filtered, filter_errors=self.form.errors, now=now)
        return ctx


class LocationBrowseView(OfficerMixin, TemplateView):
    """Department -> Area -> Ward -> Street -> complaints."""

    template_name = "officer/locations.html"
    active_tab = "locations"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        scoped = self.scoped()
        area = ward = None
        street = (self.request.GET.get("street") or "").strip()[:150]
        try:
            area = Area.objects.filter(pk=int(self.request.GET.get("area", ""))).first()
            if area:
                ward = Ward.objects.filter(pk=int(self.request.GET.get("ward", "")), area=area).first()
        except ValueError:
            pass                                     # a garbage id just shows the top level
        if ward is None:
            street = ""

        level, rows = location_breakdown(scoped, area=area, ward=ward)
        complaints = []
        if ward and street:
            complaints = (scoped.filter(status__in=ACTIVE_STATUSES, location__ward=ward, location__street__iexact=street)
                          .select_related("location__area", "location__ward").order_by("sla_deadline", "-created_at"))
        ctx.update(level=level, rows=rows, area=area, ward=ward, street=street, complaints=complaints)
        return ctx


class MapView(OfficerMixin, TemplateView):
    template_name = "officer/map.html"
    active_tab = "map"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        form = OfficerFilterForm(self.request.GET, department=self.department)
        qs = form.apply(self.scoped().select_related("location__area", "location__ward"))
        total = qs.count()
        located = qs.filter(location__latitude__isnull=False, location__longitude__isnull=False)
        located_total = located.count()
        markers = [
            {"id": c.pk, "ref": c.reference, "title": c.title, "address": c.location.address_text,
             "area": c.location.area.name if c.location.area_id else "",
             "ward": c.location.ward.number if c.location.ward_id else None, "priority": c.priority, "priority_label": c.get_priority_display(),
             "status": c.get_status_display(), "lat": float(c.location.latitude), "lng": float(c.location.longitude),
             "url": f"/officer/complaints/{c.pk}/"}               # no citizen details on the map
            for c in located[:MAP_MARKER_LIMIT]
        ]
        ctx.update(form=form, markers=markers, total=total, located_total=located_total,
                   missing_gps=total - located_total, truncated=located_total > MAP_MARKER_LIMIT,
                   limit=MAP_MARKER_LIMIT, is_filtered=form.is_filtered, filter_errors=form.errors)
        return ctx


class ComplaintDetailView(OfficerMixin, DetailView):
    template_name = "officer/detail.html"
    context_object_name = "complaint"

    def get_queryset(self):
        # Another department's complaint is "not found", not "forbidden": no ID enumeration.
        return with_assignment_info(
            self.scoped()
            .select_related("citizen", "department", "predicted_department", "ai_model", "location__area", "location__ward")
            .prefetch_related("images", "status_history__changed_by", "remarks__author",
                              "resolutions__resolved_by", "resolutions__reviewed_by", "resolutions__images",
                              "escalations__escalated_to", "escalations__triggered_by"))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        c = self.object
        probabilities = sorted(c.ai_probabilities.items(), key=lambda kv: -kv[1])
        ctx["probabilities"] = [{"code": code, "label": code.replace("_", " ").title(), "percent": round(p * 100, 1)}
                                for code, p in probabilities]
        ctx["sla"] = c.sla_state() if c.sla_active else None
        loc = c.location
        ctx["map_point"] = {"lat": float(loc.latitude), "lng": float(loc.longitude)} if loc.has_gps else None

        assignment = c.active_assignment_list[0] if c.active_assignment_list else None
        pending = next((r for r in c.resolutions.all() if r.outcome == ResolutionOutcome.PENDING_VERIFICATION), None)
        ctx.update(
            assignment=assignment, pending_resolution=pending, resolutions=list(c.resolutions.all()), remarks=list(c.remarks.all()),
            can_assign=c.status in ASSIGNABLE and pending is None, can_unassign=c.status == S.ASSIGNED_TO_WORKER,
            can_prioritise=c.status in (S.DEPARTMENT_ASSIGNED, S.PENDING, S.ASSIGNED_TO_WORKER, S.IN_PROGRESS, S.REOPENED),
            can_reject=c.status in (S.DEPARTMENT_ASSIGNED, S.PENDING),
            escalations=list(c.escalations.all()), can_escalate=c.status in ACTIVE_STATUSES and c.escalation_level < (2 if self.is_head else 1),
            escalate_label="Escalate to Administrator" if self.is_head else "Escalate to Department Head",
            feedback=getattr(c, "feedback", None), duplicates=duplicate_panel(c, self.scoped()),
            assign_form=AssignWorkerForm(department=self.department), remark_form=RemarkForm(),
            priority_form=PriorityForm(initial={"priority": c.priority}), review_form=ReviewForm(), reject_form=RejectForm())
        return ctx


# ---------------------------------------------------------------------------------------- actions (POST only)
class OfficerActionView(OfficerMixin, View):
    """Template for the small POST endpoints on the detail page. Anything not POST gets 405."""

    form_class = None
    success_message = ""

    def get_form(self, complaint):
        return self.form_class(self.request.POST)

    def perform(self, complaint, data):
        raise NotImplementedError

    def post(self, request, pk):
        complaint = get_object_or_404(self.scoped(), pk=pk)           # another department's complaint -> 404
        form = self.get_form(complaint)
        if not form.is_valid():
            first = next(iter(form.errors.values()))[0]
            messages.error(request, first)
        else:
            try:
                self.perform(complaint, form.cleaned_data)
                messages.success(request, self.success_message)
            except WorkflowError as exc:
                messages.error(request, str(exc))
        return redirect("officer:detail", pk=pk)


class AssignView(OfficerActionView):
    success_message = "Field worker assigned."

    def get_form(self, complaint):
        return AssignWorkerForm(self.request.POST, department=self.department)

    def perform(self, complaint, data):
        assign_worker(complaint, data["worker"], actor=self.request.user, note=data["note"])


class UnassignView(OfficerActionView):
    success_message = "Complaint returned to the queue."

    def get_form(self, complaint):
        from django import forms
        return forms.Form(self.request.POST)

    def perform(self, complaint, data):
        unassign_worker(complaint, actor=self.request.user)


class RemarkView(OfficerActionView):
    form_class = RemarkForm
    success_message = "Remark added."

    def perform(self, complaint, data):
        add_remark(complaint, author=self.request.user, text=data["text"], visibility=data["visibility"])


class PriorityView(OfficerActionView):
    form_class = PriorityForm
    success_message = "Priority updated."

    def perform(self, complaint, data):
        change_priority(complaint, data["priority"], actor=self.request.user, reason=data["reason"])


class EscalateView(OfficerActionView):
    form_class = EscalateForm
    success_message = "Complaint escalated."

    def perform(self, complaint, data):
        escalate_complaint(complaint, actor=self.request.user, reason=data["reason"])


class RejectView(OfficerActionView):
    form_class = RejectForm
    success_message = "Complaint rejected."

    def perform(self, complaint, data):
        reject_complaint(complaint, actor=self.request.user, reason=data["reason"])


class ReviewView(OfficerActionView):
    form_class = ReviewForm

    def perform(self, complaint, data):
        approve = data["decision"] == "approve"
        review_resolution(complaint, actor=self.request.user, approve=approve, note=data["note"])
        self.success_message = "Resolution verified. The citizen can now confirm it." if approve else "Work sent back to the field worker."

    def post(self, request, pk):
        response = super().post(request, pk)
        return response


class DuplicateReviewView(OfficerMixin, View):
    """POST: decision=duplicate | not_duplicate. The complaint must belong to the officer's department."""

    def post(self, request, pk, flag_id):
        complaint = get_object_or_404(self.scoped(), pk=pk)
        flag = get_object_or_404(DuplicateFlag, pk=flag_id, complaint=complaint)
        decision = request.POST.get("decision")
        if decision not in ("duplicate", "not_duplicate"):
            messages.error(request, "Choose whether this is a duplicate.")
        else:
            try:
                messages.success(request, review_duplicate(flag, actor=request.user, is_duplicate=decision == "duplicate"))
            except WorkflowError as exc:
                messages.error(request, str(exc))
        return redirect("officer:detail", pk=pk)
