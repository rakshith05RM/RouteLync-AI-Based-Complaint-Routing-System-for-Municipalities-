"""Forms for workflow actions. Text is normalised and sanity-checked like complaint text."""
from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from departments.models import Priority

from .models import RemarkVisibility
from .validators import normalize_text, validate_image_upload, validate_meaningful_text

User = get_user_model()


class _TextCleaningMixin:
    def clean_text_field(self, name, label, min_chars, max_chars, min_words=2, required=True):
        value = normalize_text(self.cleaned_data.get(name, ""))
        if not value and not required:
            return ""
        validate_meaningful_text(value, label=label, min_chars=min_chars, max_chars=max_chars, min_words=min_words)
        return value


class AssignWorkerForm(forms.Form):
    worker = forms.ModelChoiceField(queryset=User.objects.none(), label="Field worker", empty_label="Choose a field worker")
    note = forms.CharField(required=False, max_length=255, label="Note for the worker (optional)")

    def __init__(self, *args, department, **kwargs):
        super().__init__(*args, **kwargs)
        workers = (User.objects.filter(worker_profile__department=department, worker_profile__is_available=True, is_active=True)
                   .annotate(open_jobs=Count("complaint_assignments", filter=Q(complaint_assignments__ended_at__isnull=True)))
                   .order_by("full_name"))
        self.fields["worker"].queryset = workers
        self.fields["worker"].label_from_instance = lambda u: f"{u.full_name} ({u.open_jobs} open)"

    def clean_note(self):
        return normalize_text(self.cleaned_data.get("note", ""))


class RemarkForm(_TextCleaningMixin, forms.Form):
    text = forms.CharField(max_length=1000, label="Remark", widget=forms.Textarea(attrs={"rows": 3}))
    visibility = forms.ChoiceField(choices=RemarkVisibility.choices, initial=RemarkVisibility.INTERNAL, label="Who can see it")

    def clean_text(self):
        return self.clean_text_field("text", "Remark", 3, 1000, min_words=1)


class WorkerRemarkForm(RemarkForm):
    """Field workers can only write staff-only remarks."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields["visibility"]


class PriorityForm(_TextCleaningMixin, forms.Form):
    priority = forms.ChoiceField(choices=Priority.choices)
    reason = forms.CharField(max_length=100, widget=forms.TextInput())

    def clean_reason(self):
        return self.clean_text_field("reason", "Reason", 5, 100)


class ReviewForm(_TextCleaningMixin, forms.Form):
    decision = forms.ChoiceField(choices=[("approve", "Approve"), ("send_back", "Send back")])
    note = forms.CharField(required=False, max_length=255, widget=forms.Textarea(attrs={"rows": 2}))

    def clean_note(self):
        return normalize_text(self.cleaned_data.get("note", ""))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("decision") == "send_back" and len(cleaned.get("note", "")) < 5 and "note" not in self.errors:
            self.add_error("note", "Explain what still needs to be done.")
        return cleaned


class RejectForm(_TextCleaningMixin, forms.Form):
    reason = forms.CharField(max_length=200, widget=forms.Textarea(attrs={"rows": 2}))

    def clean_reason(self):
        return self.clean_text_field("reason", "Reason", 10, 200)


class CompleteWorkForm(_TextCleaningMixin, forms.Form):
    remarks = forms.CharField(max_length=1000, label="What was done", widget=forms.Textarea(attrs={"rows": 3}))
    photo = forms.FileField(required=True, label="Photo of the finished work", validators=[validate_image_upload],
                            error_messages={"required": "Attach a photo of the finished work. A complaint cannot be resolved without one."},
                            widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}))

    def clean_remarks(self):
        return self.clean_text_field("remarks", "Description of the work", 10, 1000)


class ReopenForm(_TextCleaningMixin, forms.Form):
    reason = forms.CharField(max_length=400, label="What is still wrong?", widget=forms.Textarea(attrs={"rows": 3}))

    def clean_reason(self):
        return self.clean_text_field("reason", "Reason", 10, 400)


class EscalateForm(_TextCleaningMixin, forms.Form):
    reason = forms.CharField(max_length=150, widget=forms.TextInput())

    def clean_reason(self):
        return self.clean_text_field("reason", "Reason", 5, 150)


class FeedbackForm(_TextCleaningMixin, forms.Form):
    rating = forms.ChoiceField(choices=[(str(n), str(n)) for n in range(1, 6)], widget=forms.RadioSelect, label="Your rating")
    comment = forms.CharField(required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 3}), label="Comments (optional)")

    def clean_comment(self):
        return self.clean_text_field("comment", "Comment", 3, 500, min_words=1, required=False)
