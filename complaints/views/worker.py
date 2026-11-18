"""Field worker pages: only complaints with an ACTIVE assignment to the signed-in worker are reachable."""
from django.contrib import messages
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import DetailView, ListView, View

from accounts.models import Role
from departments.mixins import DepartmentScopedMixin

from ..filters import sort_complaints
from ..models import ComplaintStatus as S, ResolutionOutcome, Resolution
from ..selectors import complaints_visible_to
from ..services import WorkflowError, add_remark, complete_work, start_work
from ..workflow_forms import CompleteWorkForm, WorkerRemarkForm

SHOW_CHOICES = {"todo": "To do", "review": "Awaiting review", "done": "Completed"}


class WorkerMixin(DepartmentScopedMixin):
    allowed_roles = (Role.FIELD_WORKER,)

    def scoped(self):
        return self.scope_queryset(complaints_visible_to(self.request.user))


def _awaiting():
    return Exists(Resolution.objects.filter(complaint=OuterRef("pk"), outcome=ResolutionOutcome.PENDING_VERIFICATION))


class WorkerDashboardView(WorkerMixin, ListView):
    template_name = "worker/dashboard.html"
    context_object_name = "complaints"
    paginate_by = 15

    def get_queryset(self):
        self.show = self.request.GET.get("show") if self.request.GET.get("show") in SHOW_CHOICES else "todo"
        qs = self.scoped().select_related("location__area", "location__ward").annotate(awaiting_verification=_awaiting())
        if self.show == "todo":
            qs = qs.filter(status__in=[S.ASSIGNED_TO_WORKER, S.IN_PROGRESS], awaiting_verification=False)
        elif self.show == "review":
            qs = qs.filter(status=S.IN_PROGRESS, awaiting_verification=True)
        else:
            qs = qs.filter(status=S.RESOLVED)
        return sort_complaints(qs, "priority")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base = self.scoped().annotate(awaiting_verification=_awaiting())
        counts = {
            "todo": base.filter(status__in=[S.ASSIGNED_TO_WORKER, S.IN_PROGRESS], awaiting_verification=False).count(),
            "review": base.filter(status=S.IN_PROGRESS, awaiting_verification=True).count(),
            "done": base.filter(status=S.RESOLVED).count(),
        }
        ctx.update(show=self.show, tabs=[(key, label, counts[key]) for key, label in SHOW_CHOICES.items()])
        return ctx


class WorkerDetailView(WorkerMixin, DetailView):
    template_name = "worker/detail.html"
    context_object_name = "complaint"

    def get_queryset(self):
        return (self.scoped().select_related("citizen", "department", "location__area", "location__ward")
                .prefetch_related("images", "remarks__author", "resolutions__reviewed_by"))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        c = self.object
        resolutions = list(c.resolutions.all())
        pending = next((r for r in resolutions if r.outcome == ResolutionOutcome.PENDING_VERIFICATION), None)
        loc = c.location
        ctx.update(
            resolutions=resolutions, pending_resolution=pending, remarks=list(c.remarks.all()),
            evidence=[i for i in c.images.all() if i.kind == "EVIDENCE"],
            sla=c.sla_state() if c.sla_active else None,
            map_point={"lat": float(loc.latitude), "lng": float(loc.longitude)} if loc.has_gps else None,
            can_start=c.status == S.ASSIGNED_TO_WORKER, can_complete=c.status == S.IN_PROGRESS and pending is None,
            remark_form=WorkerRemarkForm(), complete_form=CompleteWorkForm())
        return ctx


class WorkerActionView(WorkerMixin, View):
    form_class = None
    success_message = ""

    def get_form(self):
        return self.form_class(self.request.POST, self.request.FILES)

    def perform(self, complaint, data):
        raise NotImplementedError

    def post(self, request, pk):
        complaint = get_object_or_404(self.scoped(), pk=pk)          # not assigned to this worker -> 404
        form = self.get_form()
        if not form.is_valid():
            messages.error(request, next(iter(form.errors.values()))[0])
        else:
            try:
                self.perform(complaint, form.cleaned_data)
                messages.success(request, self.success_message)
            except WorkflowError as exc:
                messages.error(request, str(exc))
        return redirect("worker:detail", pk=pk)


class StartWorkView(WorkerActionView):
    success_message = "Work started."

    def get_form(self):
        from django import forms
        return forms.Form(self.request.POST)

    def perform(self, complaint, data):
        start_work(complaint, actor=self.request.user)


class FieldRemarkView(WorkerActionView):
    form_class = WorkerRemarkForm
    success_message = "Remark added."

    def perform(self, complaint, data):
        add_remark(complaint, author=self.request.user, text=data["text"])


class CompleteWorkView(WorkerActionView):
    form_class = CompleteWorkForm
    success_message = "Marked as completed. The officer will verify it."

    def perform(self, complaint, data):
        complete_work(complaint, actor=self.request.user, remarks=data["remarks"], photo=data.get("photo"))
