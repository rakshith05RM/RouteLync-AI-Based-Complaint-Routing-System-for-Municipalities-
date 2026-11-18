import logging
import mimetypes

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import DetailView, FormView, ListView, View

from accounts.mixins import RoleRequiredMixin
from accounts.models import Role

import uuid

from ..forms import ComplaintForm
from ..models import ComplaintImage, SubmissionAttempt
from departments.models import Area, Ward
from ..selectors import complaints_visible_to
from django.conf import settings

from ..models import ComplaintStatus as S, RemarkVisibility, ResolutionOutcome
from ..presenters import citizen_timeline, citizen_tracker
from ..services.attempts import discard_attempt, record_rejection
from ..services import (WorkflowError, confirm_resolution, reopen_complaint, route_complaint, submit_complaint,
                        submit_feedback)
from ..workflow_forms import FeedbackForm, ReopenForm

logger = logging.getLogger("routelync")


class CitizenOnlyMixin(RoleRequiredMixin):
    allowed_roles = (Role.CITIZEN,)


class ComplaintCreateView(CitizenOnlyMixin, FormView):
    template_name = "complaints/complaint_form.html"
    form_class = ComplaintForm

    def get_attempt(self):
        """The earlier rejected submission being corrected (only ever the signed-in citizen's own)."""
        if not hasattr(self, "_attempt"):
            raw = self.request.POST.get("attempt") or self.request.GET.get("attempt") or ""
            self._attempt = SubmissionAttempt.objects.filter(pk=int(raw), citizen=self.request.user).first() if raw.isdigit() else None
        return self._attempt

    def get_initial(self):
        initial = {"submission_token": uuid.uuid4().hex}
        a = self.get_attempt()
        if a is not None and self.request.method == "GET":
            initial.update(title=a.title, description=a.description,
                           area=a.area_id or (a.ward.area_id if a.ward else None),
                           ward=a.ward.number if a.ward_id else a.ward_text,
                           location_search=a.address_text,
                           street=a.street, landmark=a.landmark, building=a.building, address_text=a.address_text,
                           latitude=a.latitude, longitude=a.longitude)
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["citizen"] = self.request.user
        kwargs["attempt"] = self.get_attempt()
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        form = ctx["form"]
        from departments.models import Department
        ctx.update(service_bbox=settings.LOCATION_MAP_BOUNDS, min_words=settings.COMPLAINT_MIN_WORDS, attempt=self.get_attempt(), rejection=form.rejection,
                   supported=", ".join(d.name.lower() for d in Department.objects.filter(is_active=True)))
        ctx["ward_suggestions"] = Ward.objects.filter(
            area__service_district__in=Area.ServiceDistrict.values
        ).select_related("area").order_by("area__service_district", "area__name", "number")
        return ctx

    def form_invalid(self, form):
        if form.rejection is not None:                # description refused: keep the work as a draft, not as a complaint
            self._attempt = record_rejection(self.request.user, form, form.rejection, self.get_attempt())
        return super().form_invalid(form)

    def form_valid(self, form):
        token = form.cleaned_data.get("submission_token") or ""
        used = self.request.session.get("submitted_tokens", {})
        if token and token in used:                    # the same form sent twice (double click): do not create a second complaint
            earlier = complaints_visible_to(self.request.user).filter(pk=used[token]).first()
            if earlier is not None:
                messages.info(self.request, f"Complaint {earlier.reference} was already submitted.")
                return redirect("complaints:detail", pk=earlier.pk)
        try:
            complaint = submit_complaint(
                citizen=self.request.user, data=form.cleaned_data, image=form.cleaned_data.get("image"))
        except Exception:  # noqa: BLE001 - log the technical detail, show a friendly message
            logger.exception("Complaint submission failed for user %s", self.request.user.pk)
            form.add_error(None, "Sorry, we could not save your complaint. Please try again in a moment.")
            return self.form_invalid(form)
        attempt = self.get_attempt()
        if attempt is not None:                        # the corrected draft has become a real complaint
            discard_attempt(attempt)
        if token:
            used[token] = complaint.pk
            self.request.session["submitted_tokens"] = dict(list(used.items())[-20:])
        try:
            route_complaint(complaint)          # the complaint is already saved; routing can never lose it
        except Exception:  # noqa: BLE001
            logger.exception("Routing failed for %s; run route_pending_complaints", complaint.reference)
        messages.success(self.request, f"Complaint {complaint.reference} submitted successfully.")
        return redirect("complaints:detail", pk=complaint.pk)   # redirect after POST: no double-submit on refresh


class MyComplaintsView(CitizenOnlyMixin, ListView):
    template_name = "complaints/my_complaints.html"
    context_object_name = "complaints"
    paginate_by = 10

    def get_queryset(self):
        return complaints_visible_to(self.request.user).select_related("department", "location__area", "location__ward")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["attempts"] = list(SubmissionAttempt.objects.filter(citizen=self.request.user)[:10])
        return ctx


class AttemptDiscardView(CitizenOnlyMixin, View):
    """POST: remove one of the citizen's own rejected drafts."""

    def post(self, request, pk):
        attempt = get_object_or_404(SubmissionAttempt, pk=pk, citizen=request.user)
        discard_attempt(attempt)
        messages.success(request, "The draft was removed.")
        return redirect("complaints:my_complaints")


class ComplaintDetailView(CitizenOnlyMixin, DetailView):
    template_name = "complaints/complaint_detail.html"
    context_object_name = "complaint"

    def get_queryset(self):
        # Someone else's complaint is simply "not found" (404), which also avoids ID enumeration.
        return (complaints_visible_to(self.request.user)
                .select_related("department", "location__area", "location__ward")
                .prefetch_related("images", "status_history", "remarks__author", "resolutions__images", "feedback"))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        c = self.object
        shown = [r for r in c.resolutions.all() if r.outcome in (ResolutionOutcome.VERIFIED, ResolutionOutcome.DISPUTED)]
        resolution = shown[0] if shown else None          # newest first
        window_open = bool(c.resolved_at) and (timezone.now() - c.resolved_at).days < settings.REOPEN_WINDOW_DAYS
        ctx.update(
            timeline=citizen_timeline(c), tracker=citizen_tracker(c),
            public_remarks=[r for r in c.remarks.all() if r.visibility == RemarkVisibility.PUBLIC],
            resolution=resolution if c.status in (S.RESOLVED, S.CLOSED) else None,
            proof_photo=bool(c.resolution_photo) and c.status in (S.RESOLVED, S.CLOSED),
            can_respond=c.status == S.RESOLVED, can_reopen=c.status == S.RESOLVED and window_open,
            reopen_days=settings.REOPEN_WINDOW_DAYS, reopen_form=ReopenForm(),
            feedback=getattr(c, "feedback", None), can_give_feedback=c.status in (S.RESOLVED, S.CLOSED) and not hasattr(c, "feedback"),
            feedback_form=FeedbackForm())
        return ctx


class ComplaintRespondView(CitizenOnlyMixin, View):
    """POST only. Subclasses confirm or reopen; the citizen can only act on their own complaint (404 otherwise)."""

    def post(self, request, pk):
        complaint = get_object_or_404(complaints_visible_to(request.user), pk=pk)
        try:
            self.act(request, complaint)
        except WorkflowError as exc:
            messages.error(request, str(exc))
        return redirect("complaints:detail", pk=pk)

    def act(self, request, complaint):
        raise NotImplementedError


class ConfirmResolutionView(ComplaintRespondView):
    def act(self, request, complaint):
        confirm_resolution(complaint, citizen=request.user)
        messages.success(request, "Thank you for confirming. This complaint is now closed.")


class ReopenComplaintView(ComplaintRespondView):
    def act(self, request, complaint):
        form = ReopenForm(request.POST)
        if not form.is_valid():
            messages.error(request, next(iter(form.errors.values()))[0])
            return
        reopen_complaint(complaint, citizen=request.user, reason=form.cleaned_data["reason"])
        messages.success(request, "Your complaint has been reopened and sent back to the department.")


@login_required
def complaint_image(request, pk, image_id):
    """Streams a complaint photo only to people who may see that complaint."""
    image = get_object_or_404(
        ComplaintImage.objects.filter(complaint__in=complaints_visible_to(request.user)),
        pk=image_id, complaint_id=pk)
    if (image.kind == "RESOLUTION" and request.user.role == Role.CITIZEN
            and not (image.resolution and image.resolution.outcome in (ResolutionOutcome.VERIFIED, ResolutionOutcome.DISPUTED))):
        raise Http404("Image not available")
    try:
        handle = image.image.open("rb")
    except FileNotFoundError:
        logger.error("Image file missing for ComplaintImage %s", image.pk)
        raise Http404("Image not available")
    content_type = mimetypes.guess_type(image.image.name)[0] or "application/octet-stream"
    response = FileResponse(handle, content_type=content_type)
    response["Cache-Control"] = "private, max-age=300"
    response["X-Content-Type-Options"] = "nosniff"
    return response



class FeedbackView(ComplaintRespondView):
    def act(self, request, complaint):
        form = FeedbackForm(request.POST)
        if not form.is_valid():
            messages.error(request, next(iter(form.errors.values()))[0])
            return
        submit_feedback(complaint, citizen=request.user, rating=form.cleaned_data["rating"], comment=form.cleaned_data["comment"])
        messages.success(request, "Thank you for your feedback.")


@login_required
def resolution_photo(request, pk):
    """The photo of the completed fix. Citizens see it once the complaint is Resolved or Closed (never before
    an officer has verified the work); staff see it on complaints they are allowed to open."""
    complaint = get_object_or_404(complaints_visible_to(request.user), pk=pk)
    if not complaint.resolution_photo:
        raise Http404("No photo")
    if request.user.role == Role.CITIZEN and complaint.status not in (S.RESOLVED, S.CLOSED):
        raise Http404("No photo")
    try:
        handle = complaint.resolution_photo.open("rb")
    except FileNotFoundError:
        logger.error("Resolution photo missing for %s", complaint.reference)
        raise Http404("Image not available")
    response = FileResponse(handle, content_type=mimetypes.guess_type(complaint.resolution_photo.name)[0] or "application/octet-stream")
    response["Cache-Control"] = "private, max-age=300"
    response["X-Content-Type-Options"] = "nosniff"
    return response
