from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from accounts.models import Role
from complaints.filters import OfficerFilterForm
from complaints.models import ComplaintStatus
from complaints.validators import normalize_text
from core.validators import mobile_number_validator, validate_person_name
from departments.models import Department, Priority

User = get_user_model()


class AdminComplaintFilterForm(OfficerFilterForm):
    """The officer filters plus a department filter, and every status (including pre-routing ones)."""

    department = forms.ModelChoiceField(queryset=Department.objects.all(), required=False, empty_label="All departments")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, department=None, **kwargs)
        self.fields["status"].choices = [("", "Open complaints"), ("ALL", "All statuses")] + list(ComplaintStatus.choices)
        workers = User.objects.filter(worker_profile__isnull=False).order_by("full_name")
        self.fields["assigned_to"].choices = [("", "Anyone"), ("none", "Unassigned")] + [(str(u.pk), u.full_name) for u in workers]

    @property
    def is_filtered(self):
        return super().is_filtered or bool(getattr(self, "cleaned_data", {}).get("department"))

    def apply(self, queryset, now=None):
        qs = super().apply(queryset, now)
        dept = self.cleaned_data.get("department")
        return qs.filter(department=dept) if dept else qs


class RouteForm(forms.Form):
    department = forms.ModelChoiceField(queryset=Department.objects.filter(is_active=True), empty_label="Choose a department")
    add_to_training = forms.BooleanField(required=False, initial=True, label="Use as a verified training example")
    note = forms.CharField(required=False, max_length=255)

    def clean_note(self):
        return normalize_text(self.cleaned_data.get("note", ""))


class StaffCreateForm(forms.Form):
    full_name = forms.CharField(max_length=150, validators=[validate_person_name])
    email = forms.EmailField(max_length=254)
    phone = forms.CharField(max_length=10, validators=[mobile_number_validator])
    role = forms.ChoiceField(choices=[(Role.OFFICER, "Department officer"), (Role.FIELD_WORKER, "Field worker"), (Role.ADMIN, "Administrator")])
    department = forms.ModelChoiceField(queryset=Department.objects.filter(is_active=True), required=False, empty_label="Not applicable")
    designation = forms.CharField(max_length=100, required=False)
    employee_code = forms.CharField(max_length=20, required=False, help_text="Field workers only; generated if left empty")
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}), strip=False, label="Temporary password")

    def clean_full_name(self):
        return " ".join(self.cleaned_data["full_name"].split())

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        if role in (Role.OFFICER, Role.FIELD_WORKER) and not cleaned.get("department"):
            self.add_error("department", "Choose the department for this staff member.")
        pw = cleaned.get("password")
        if pw:
            try:
                validate_password(pw, user=User(email=cleaned.get("email", ""), full_name=cleaned.get("full_name", "")))
            except ValidationError as exc:
                self.add_error("password", exc)
        return cleaned


class DepartmentForm(forms.Form):
    name = forms.CharField(max_length=80)
    code = forms.RegexField(regex=r"^[A-Z][A-Z0-9_]{1,29}$", max_length=30, help_text="Upper case, e.g. PARKS or STREET_LIGHTS. Cannot be changed later.",
                            error_messages={"invalid": "Use upper-case letters, digits and underscores, e.g. WATER_SUPPLY."})
    description = forms.CharField(max_length=255, required=False)

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if Department.objects.filter(name__iexact=name).exists():
            raise ValidationError("A department with this name already exists.")
        return name

    def clean_code(self):
        if Department.objects.filter(code=self.cleaned_data["code"]).exists():
            raise ValidationError("A department with this code already exists.")
        return self.cleaned_data["code"]


class SLAForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for value, label in Priority.choices:
            self.fields[value] = forms.IntegerField(min_value=1, max_value=720, label=f"{label} priority (hours)")


class ThresholdForm(forms.Form):
    threshold = forms.FloatField(min_value=0.5, max_value=0.99, label="Confidence threshold",
                                 help_text="Complaints below this confidence go to the verification queue (0.50 to 0.99).")


class DatasetUploadForm(forms.Form):
    file = forms.FileField(label="CSV file", help_text="Columns: text, department_code. Maximum 2 MB.")
    dataset_version = forms.CharField(max_length=40, required=False, label="Version label")
    dry_run = forms.BooleanField(required=False, initial=True, label="Check only (do not save)")


class AddSampleForm(forms.Form):
    text = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), max_length=2000, label="Complaint text")
    department = forms.ModelChoiceField(queryset=Department.objects.all(), empty_label="Choose a department")
