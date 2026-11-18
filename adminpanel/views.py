"""Administrator panel. Every view requires the ADMIN role; every state change is a POST handled by a service."""
import csv

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import DetailView, FormView, ListView, TemplateView, View

from accounts.mixins import RoleRequiredMixin
from accounts.models import Role
from audit.models import AuditLog
from complaints.models import ACTIVE_STATUSES, Complaint, ComplaintStatus as S, DuplicateFlag, RoutingCorrection
from complaints.presenters import duplicate_panel
from complaints.services import WorkflowError, reject_complaint, review_duplicate, route_by_admin
from complaints.views.officer import with_assignment_info
from complaints.workflow_forms import RejectForm
from departments.models import Department, OfficerProfile, Priority, SLAConfiguration
from ml_engine.dataset import add_verified_sample, read_csv_upload, statistics
from ml_engine.exceptions import DatasetError, MLEngineError
from ml_engine.explain import pipeline_trace
from ml_engine.models import MLModel, TrainingSample

from . import analytics, services
from .forms import (AddSampleForm, AdminComplaintFilterForm, DatasetUploadForm, DepartmentForm, RouteForm, SLAForm,
                    StaffCreateForm, ThresholdForm)

User = get_user_model()


class AdminMixin(RoleRequiredMixin):
    allowed_roles = (Role.ADMIN,)
    active_tab = ""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(active_tab=self.active_tab, queue_count=Complaint.objects.filter(status=S.NEEDS_VERIFICATION).count())
        return ctx


class AdminActionView(AdminMixin, View):
    """POST-only endpoint: run `perform`, show a message, go back. Anything else gets 405."""

    success_message = ""
    redirect_to = "adminpanel:dashboard"

    def perform(self, request, **kwargs):
        raise NotImplementedError

    def get_redirect(self, **kwargs):
        return redirect(self.redirect_to)

    def post(self, request, **kwargs):
        try:
            result = self.perform(request, **kwargs)
            msg = result if isinstance(result, str) and result else self.success_message
            if msg:
                messages.success(request, msg)
        except WorkflowError as exc:
            messages.error(request, str(exc))
        return self.get_redirect(**kwargs)


def first_error(form):
    return next(iter(form.errors.values()))[0]


# ------------------------------------------------------------------------------------------ dashboard
class DashboardView(AdminMixin, TemplateView):
    template_name = "adminpanel/dashboard.html"
    active_tab = "dashboard"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(summary=analytics.summary_counts(), by_department=analytics.by_department(), by_area=analytics.by_area(),
                   by_ward=analytics.by_ward(), over_time=analytics.over_time(), statuses=analytics.status_distribution(),
                   priorities=analytics.priority_distribution(), resolution=analytics.resolution_time_by_department(),
                   feedback=analytics.feedback_summary(), ai=analytics.ai_overview())
        model = ctx["ai"]["model"]
        if model:
            ctx["matrix"] = [{"label": lab, "cells": row} for lab, row in zip(model.labels, model.confusion_matrix)]
        return ctx


# ------------------------------------------------------------------------------------------ complaints
class ComplaintsView(AdminMixin, ListView):
    template_name = "adminpanel/complaints.html"
    context_object_name = "complaints"
    paginate_by = 20
    active_tab = "complaints"

    def get_queryset(self):
        self.form = AdminComplaintFilterForm(self.request.GET)
        base = with_assignment_info(Complaint.objects.select_related("location__area", "location__ward__area", "citizen", "department"))
        return self.form.apply(base)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(form=self.form, filter_errors=self.form.errors, is_filtered=self.form.is_filtered)
        return ctx


class ComplaintDetailView(AdminMixin, DetailView):
    template_name = "adminpanel/complaint_detail.html"
    context_object_name = "complaint"
    active_tab = "complaints"

    def get_queryset(self):
        return with_assignment_info(
            Complaint.objects.select_related("citizen", "department", "predicted_department", "ai_model",
                                             "location__area", "location__ward__area")
            .prefetch_related("images", "status_history__changed_by", "remarks__author", "resolutions__resolved_by",
                              "escalations__escalated_to", "routing_corrections__corrected_by"))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        c = self.object
        probs = sorted(c.ai_probabilities.items(), key=lambda kv: -kv[1])
        route_form = RouteForm(initial={"department": c.predicted_department_id if c.status == S.NEEDS_VERIFICATION else None})
        ctx.update(
            probabilities=[{"label": k.replace("_", " ").title(), "percent": round(v * 100, 1)} for k, v in probs],
            assignment=c.active_assignment_list[0] if c.active_assignment_list else None,
            remarks=list(c.remarks.all()), escalations=list(c.escalations.all()), corrections=list(c.routing_corrections.all()),
            resolutions=list(c.resolutions.all()), feedback=getattr(c, "feedback", None),
            duplicates=duplicate_panel(c, Complaint.objects.all()),
            sla=c.sla_state() if c.sla_active else None, route_form=route_form,
            can_route=c.status in (S.NEEDS_VERIFICATION, S.DEPARTMENT_ASSIGNED, S.PENDING, S.ASSIGNED_TO_WORKER),
            can_reject=c.status in (S.NEEDS_VERIFICATION, S.DEPARTMENT_ASSIGNED, S.PENDING),
            departments=Department.objects.filter(is_active=True),
            map_point={"lat": float(c.location.latitude), "lng": float(c.location.longitude)} if c.location.has_gps else None)
        return ctx


class RouteView(AdminActionView):
    def perform(self, request, pk):
        complaint = get_object_or_404(Complaint, pk=pk)
        form = RouteForm(request.POST)
        if not form.is_valid():
            raise WorkflowError(first_error(form))
        _, training_note = route_by_admin(complaint, form.cleaned_data["department"], actor=request.user,
                                          note=form.cleaned_data["note"], add_to_training=form.cleaned_data["add_to_training"])
        return "Department set." + (f" {training_note}" if training_note else "")

    def get_redirect(self, pk):
        return redirect("adminpanel:complaint", pk=pk)


class RejectView(AdminActionView):
    success_message = "Complaint rejected."

    def perform(self, request, pk):
        complaint = get_object_or_404(Complaint, pk=pk)
        form = RejectForm(request.POST)
        if not form.is_valid():
            raise WorkflowError(first_error(form))
        reject_complaint(complaint, actor=request.user, reason=form.cleaned_data["reason"])

    def get_redirect(self, pk):
        return redirect("adminpanel:complaint", pk=pk)


class DuplicateReviewView(AdminActionView):
    def perform(self, request, pk, flag_id):
        complaint = get_object_or_404(Complaint, pk=pk)
        flag = get_object_or_404(DuplicateFlag, pk=flag_id, complaint=complaint)
        decision = request.POST.get("decision")
        if decision not in ("duplicate", "not_duplicate"):
            raise WorkflowError("Choose whether this is a duplicate.")
        return review_duplicate(flag, actor=request.user, is_duplicate=decision == "duplicate")

    def get_redirect(self, pk, flag_id):
        return redirect("adminpanel:complaint", pk=pk)


class QueueView(AdminMixin, ListView):
    template_name = "adminpanel/queue.html"
    context_object_name = "complaints"
    paginate_by = 20
    active_tab = "queue"

    def get_queryset(self):
        return (Complaint.objects.filter(status=S.NEEDS_VERIFICATION).select_related("location__area", "location__ward__area", "predicted_department")
                .order_by("sla_deadline", "created_at"))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["departments"] = Department.objects.filter(is_active=True)
        ctx["now"] = timezone.now()
        return ctx


# ------------------------------------------------------------------------------------------ users
class UsersView(AdminMixin, ListView):
    template_name = "adminpanel/users.html"
    context_object_name = "users"
    paginate_by = 25
    active_tab = "users"

    def get_queryset(self):
        qs = User.objects.select_related("officer_profile__department", "worker_profile__department")
        role, active, q = self.request.GET.get("role", ""), self.request.GET.get("active", ""), self.request.GET.get("q", "").strip()[:100]
        if role in Role.values:
            qs = qs.filter(role=role)
        if active in ("yes", "no"):
            qs = qs.filter(is_active=(active == "yes"))
        for term in q.split()[:5]:
            qs = qs.filter(Q(full_name__icontains=term) | Q(email__icontains=term) | Q(phone__icontains=term))
        return qs.order_by("role", "full_name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(roles=Role.choices, f_role=self.request.GET.get("role", ""), f_active=self.request.GET.get("active", ""),
                   f_q=self.request.GET.get("q", ""))
        return ctx


class UserCreateView(AdminMixin, FormView):
    template_name = "adminpanel/user_form.html"
    form_class = StaffCreateForm
    active_tab = "users"

    def form_valid(self, form):
        try:
            user = services.create_staff(self.request.user, form.cleaned_data)
        except WorkflowError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, f"Account created for {user.full_name}.")
        return redirect("adminpanel:users")


class UserActionView(AdminActionView):
    redirect_to = "adminpanel:users"
    ACTIONS = {"activate", "deactivate", "available", "unavailable", "make_head"}

    def perform(self, request, pk, action):
        if action not in self.ACTIONS:
            raise WorkflowError("Unknown action.")
        user = get_object_or_404(User, pk=pk)
        if action in ("activate", "deactivate"):
            services.set_user_active(request.user, user, action == "activate")
        elif action in ("available", "unavailable"):
            services.set_worker_available(request.user, user, action == "available")
        else:
            services.set_department_head(request.user, user)
        return "Done."

    def get_redirect(self, **kwargs):
        return redirect("adminpanel:users")


# ------------------------------------------------------------------------------------------ departments and SLA
class DepartmentsView(AdminMixin, TemplateView):
    template_name = "adminpanel/departments.html"
    active_tab = "departments"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["departments"] = Department.objects.annotate(
            officers_n=Count("officers", distinct=True), workers_n=Count("field_workers", distinct=True),
            active_n=Count("complaints", filter=Q(complaints__status__in=ACTIVE_STATUSES), distinct=True)).order_by("name")
        ctx["form"] = kwargs.get("form") or DepartmentForm()
        trained = set(MLModel.objects.filter(is_active=True).values_list("labels", flat=True).first() or [])
        ctx["trained_codes"] = trained
        return ctx


class DepartmentCreateView(AdminMixin, View):
    def post(self, request):
        form = DepartmentForm(request.POST)
        if form.is_valid():
            dept = services.create_department(request.user, form.cleaned_data)
            messages.success(request, f"{dept.name} was added. Import training examples for it and train a new model so complaints can be routed to it automatically.")
        else:
            messages.error(request, first_error(form))
        return redirect("adminpanel:departments")


class DepartmentToggleView(AdminActionView):
    redirect_to = "adminpanel:departments"

    def perform(self, request, pk, active):
        services.set_department_active(request.user, get_object_or_404(Department, pk=pk), active == "on")
        return "Department updated."


class SLAView(AdminMixin, FormView):
    template_name = "adminpanel/sla.html"
    form_class = SLAForm
    active_tab = "departments"

    def get_initial(self):
        from departments.services import sla_hours_for
        return {p: sla_hours_for(p) for p in Priority.values}

    def form_valid(self, form):
        changed = services.update_sla(self.request.user, form.cleaned_data)
        messages.success(self.request, "SLA settings saved. They apply to complaints submitted from now on." if changed else "Nothing changed.")
        return redirect("adminpanel:sla")


# ------------------------------------------------------------------------------------------ AI model and dataset
class AIView(AdminMixin, TemplateView):
    template_name = "adminpanel/ai.html"
    active_tab = "ai"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        models = list(MLModel.objects.all())
        active = next((m for m in models if m.is_active), None)
        ctx.update(models=models, model=active, ai=analytics.ai_overview(), threshold_form=ThresholdForm(initial={"threshold": active.conf_threshold}) if active else None)
        if active:
            ctx["matrix"] = [{"label": lab, "cells": row} for lab, row in zip(active.labels, active.confusion_matrix)]
            ctx["per_class"] = [{"label": k, **v} for k, v in active.per_class_metrics.items()]
        return ctx


class TrainView(AdminActionView):
    redirect_to = "adminpanel:ai"

    def perform(self, request):
        model = services.train_new_model(request.user)
        return f"Model v{model.version} trained. Review its results below, then activate it."


class ActivateView(AdminActionView):
    redirect_to = "adminpanel:ai"

    def perform(self, request, pk):
        get_object_or_404(MLModel, pk=pk).activate(request.user)
        return "Model activated."


class ThresholdView(AdminActionView):
    redirect_to = "adminpanel:ai"

    def perform(self, request, pk):
        form = ThresholdForm(request.POST)
        if not form.is_valid():
            raise WorkflowError(first_error(form))
        services.set_threshold(request.user, get_object_or_404(MLModel, pk=pk), form.cleaned_data["threshold"])
        return "Threshold updated."


class ModelTraceView(AdminMixin, View):
    """POST: show how the active model reads one piece of text, stage by stage. Nothing is saved."""

    def post(self, request):
        from django.shortcuts import render
        text = (request.POST.get("text") or "").strip()[:500]
        if not text:
            messages.error(request, "Type some text to explain.")
            return redirect("adminpanel:ai")
        try:
            trace = pipeline_trace(text)
        except MLEngineError as exc:
            messages.error(request, str(exc))
            return redirect("adminpanel:ai")
        ctx = {"trace": trace, "text": text, "active_tab": "ai", "queue_count": Complaint.objects.filter(status=S.NEEDS_VERIFICATION).count()}
        return render(request, "adminpanel/trace.html", ctx)


class DatasetView(AdminMixin, ListView):
    template_name = "adminpanel/dataset.html"
    context_object_name = "samples"
    paginate_by = 25
    active_tab = "ai"

    def get_queryset(self):
        qs = TrainingSample.objects.select_related("department").order_by("-id")
        dept, verified = self.request.GET.get("department", ""), self.request.GET.get("verified", "")
        if dept.isdigit():
            qs = qs.filter(department_id=int(dept))
        if verified in ("yes", "no"):
            qs = qs.filter(is_verified=(verified == "yes"))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        stats = statistics()
        top = max(stats["per_class"].values(), default=0)
        ctx.update(stats=stats, bars=[{"label": k, "value": v, "percent": round(100 * v / top)} for k, v in sorted(stats["per_class"].items())],
                   departments=Department.objects.all(), upload_form=DatasetUploadForm(), add_form=AddSampleForm(),
                   report=self.request.session.pop("import_report", None))
        return ctx


class DatasetUploadView(AdminMixin, View):
    def post(self, request):
        form = DatasetUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, first_error(form))
            return redirect("adminpanel:dataset")
        try:
            rows = read_csv_upload(form.cleaned_data["file"])
            report = services.import_dataset(request.user, rows, version=form.cleaned_data["dataset_version"], dry_run=form.cleaned_data["dry_run"])
        except DatasetError as exc:
            messages.error(request, str(exc))
            return redirect("adminpanel:dataset")
        request.session["import_report"] = {
            "summary": report.summary(), "invalid": [f"Row {n}: {r}" for n, r in report.invalid[:10]],
            "conflicts": [f"Row {n}: labelled {a} and {b}" for n, _, a, b in report.conflicts[:10]],
            "unknown": dict(report.unknown_departments), "dry_run": report.dry_run}
        return redirect("adminpanel:dataset")


class AddSampleView(AdminMixin, View):
    def post(self, request):
        form = AddSampleForm(request.POST)
        if not form.is_valid():
            messages.error(request, first_error(form))
        else:
            sample, reason = add_verified_sample(text=form.cleaned_data["text"], department=form.cleaned_data["department"])
            if sample:
                from audit.services import log_action
                log_action(request.user, "SAMPLE_ADDED", target=sample, summary=f"Training example added for {sample.department.name}")
                messages.success(request, "Training example added.")
            else:
                messages.error(request, f"Not added: {reason}.")
        return redirect("adminpanel:dataset")


def _safe_cell(value):
    """Stops spreadsheet programs from running a cell that starts with = + - or @ as a formula."""
    value = str(value)
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value


class DatasetExportView(AdminMixin, View):
    def get(self, request):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="training_data.csv"'
        writer = csv.writer(response)
        writer.writerow(["text", "department_code", "source", "is_verified", "dataset_version"])
        for s in TrainingSample.objects.filter(is_verified=True).select_related("department").order_by("id").iterator():
            writer.writerow([_safe_cell(s.text), s.department.code, s.source, "true", s.dataset_version])
        return response


# ------------------------------------------------------------------------------------------ audit
class AuditView(AdminMixin, ListView):
    template_name = "adminpanel/audit.html"
    context_object_name = "entries"
    paginate_by = 30
    active_tab = "audit"

    def get_queryset(self):
        qs = AuditLog.objects.select_related("user")
        action, q = self.request.GET.get("action", ""), self.request.GET.get("q", "").strip()[:100]
        if action:
            qs = qs.filter(action=action)
        for term in q.split()[:5]:
            qs = qs.filter(Q(summary__icontains=term) | Q(user__full_name__icontains=term))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(actions=AuditLog.objects.order_by().values_list("action", flat=True).distinct().order_by("action"),
                   f_action=self.request.GET.get("action", ""), f_q=self.request.GET.get("q", ""))
        return ctx
