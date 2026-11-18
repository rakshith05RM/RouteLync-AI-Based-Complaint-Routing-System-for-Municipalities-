from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
import re

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from departments.models import Area, Ward

from .models import Complaint
from core.geo import service as geo_service

from .services.description_check import check_description
from .validators import (normalize_text, validate_address, validate_image_upload,
                         validate_latitude, validate_longitude, validate_street, validate_title)


class CoordinateField(forms.DecimalField):
    """Accepts the browser's long decimals, rounds to 6 places (~0.1 m), then range-checks."""

    def __init__(self, **kwargs):
        super().__init__(required=False, max_digits=9, decimal_places=6, widget=forms.HiddenInput, **kwargs)

    def to_python(self, value):
        if value in self.empty_values:
            return None
        try:
            number = Decimal(str(value).strip())
            if not number.is_finite():
                raise InvalidOperation
            return number.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        except InvalidOperation:
            raise ValidationError("Enter a valid coordinate.", code="invalid")


class WardSelect(forms.Select):
    """Adds data-area to every <option> so JavaScript can filter wards by the chosen area."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, "instance", None)
        if instance is not None:
            option["attrs"]["data-area"] = instance.area_id
        return option


class WardChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, ward):
        return f"Ward {ward.number}" + (f" - {ward.name}" if ward.name else "")


class ComplaintAreaSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, "instance", None)
        if instance is not None:
            option["attrs"]["data-area-name"] = instance.name
            option["attrs"]["data-district"] = instance.service_district
        return option


class ComplaintAreaField(forms.ModelChoiceField):
    def label_from_instance(self, area):
        return f"{area.name} ({area.service_district})"


class ComplaintForm(forms.Form):
    # ---- the issue
    title = forms.CharField(max_length=120, help_text="A short summary, e.g. \"Streetlight not working near junction\"")
    description = forms.CharField(
        max_length=2000, widget=forms.Textarea(attrs={"rows": 5, "maxlength": 2000, "required": True}),
        help_text="Required. Write at least %d words: what is wrong, since when, and how it affects people. "
                  "RouteLync reads this text to decide which department handles your complaint." % settings.COMPLAINT_MIN_WORDS)
    # ---- the location
    location_search = forms.CharField(
        max_length=120, label="Search for the place",
        widget=forms.TextInput(attrs={"id": "location-search", "class": "form-control", "role": "combobox",
                                     "aria-autocomplete": "list", "aria-expanded": "false",
                                     "aria-controls": "location-results", "autocomplete": "off",
                                     "placeholder": "Type a place, street or landmark"}),
    )
    area = ComplaintAreaField(
        queryset=Area.objects.filter(service_district__in=Area.ServiceDistrict.values)
        .order_by("service_district", "name"),
        required=False, empty_label="Select area", widget=ComplaintAreaSelect,
        help_text="Choose a corporation, taluk or known locality in the verified district.")
    ward = forms.CharField(
        max_length=100, required=False, label="Ward",
        widget=forms.TextInput(attrs={"list": "ward-suggestions", "inputmode": "numeric",
                                     "placeholder": "Enter a ward number or choose a suggestion",
                                     "autocomplete": "off"}))
    street = forms.CharField(max_length=150, required=False, label="Street name")
    landmark = forms.CharField(max_length=150, required=False, help_text="Optional, e.g. \"Near Metro station\"")
    building = forms.CharField(max_length=150, required=False, label="House / building",
                               help_text="Optional")
    address_text = forms.CharField(max_length=300, label="Complete address",
                                   widget=forms.Textarea(attrs={"rows": 2}))
    latitude = CoordinateField(validators=[validate_latitude])
    longitude = CoordinateField(validators=[validate_longitude])
    # Issued by our own location service (core/geo): ties the chosen address to the coordinates so they cannot be mixed.
    location_token = forms.CharField(required=False, widget=forms.HiddenInput)
    location_source = forms.CharField(required=False, widget=forms.HiddenInput)
    # ---- the evidence
    image = forms.FileField(required=True, label="Photo of the problem", validators=[validate_image_upload],
                            error_messages={"required": "Please upload an image related to your complaint before submitting."},
                            help_text="Required. JPG, PNG or WEBP. Show the problem clearly; it is shown to the department with your description.",
                            widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp", "required": True}))

    submission_token = forms.CharField(required=False, widget=forms.HiddenInput)      # stops a double click creating two complaints

    def __init__(self, *args, citizen, attempt=None, **kwargs):
        self.citizen = citizen
        self.attempt = attempt
        self.rejection = None          # set when the description is refused; the view keeps the submission as a draft
        super().__init__(*args, **kwargs)
        self.fields["image"].widget.attrs["data-max-bytes"] = int(settings.MAX_IMAGE_SIZE_MB * 1024 * 1024)
        if attempt is not None and attempt.image:       # the photo from the previous try is kept
            self.fields["image"].required = False
            self.fields["image"].widget.attrs.pop("required", None)

    # Note: FileField (not ImageField) on purpose. validate_image_upload is the single authority for
    # size, real format, dimensions and extension, so the error messages are consistent.
    def _clean_text(self, name, validator):
        value = normalize_text(self.cleaned_data[name])
        validator(value)
        return value

    def clean_title(self):
        return self._clean_text("title", validate_title)

    def clean_description(self):
        text = normalize_text(self.cleaned_data["description"])
        result = check_description(text)
        if not result.accepted:
            self.rejection = result
            raise ValidationError(result.message, code=result.verdict.value.lower())
        return text

    def clean_street(self):
        value = normalize_text(self.cleaned_data.get("street", ""))
        if value:
            validate_street(value)
        return value

    def clean_ward(self):
        value = normalize_text(self.cleaned_data.get("ward", ""))
        if not value:
            return None
        match = re.fullmatch(r"(?:ward\s*)?(\d+)", value, re.IGNORECASE)
        if not match:
            raise ValidationError("Enter a ward number or choose one of the suggestions.")
        number = int(match.group(1))
        if not 1 <= number <= 32767:
            raise ValidationError("Enter a ward number between 1 and 32767.")
        return number

    def clean_location_search(self):
        value = normalize_text(self.cleaned_data["location_search"])
        if len(value) < 3:
            raise ValidationError("Enter at least 3 characters in the place search.")
        return value

    def clean_address_text(self):
        return self._clean_text("address_text", validate_address)

    def clean_landmark(self):
        return normalize_text(self.cleaned_data.get("landmark", ""))

    def clean_building(self):
        return normalize_text(self.cleaned_data.get("building", ""))

    def _check_selection(self, cleaned, lat, lon):
        """If the browser sent a location token, the address, place and coordinates must be the ones our server issued."""
        token = (cleaned.get("location_token") or "").strip()
        if not token:
            self.add_error("location_token", "Please select a searched place or wait for the map to verify its location.")
            return
        payload = geo_service.read_selection(token, self.citizen.pk)
        if payload is None:
            self.add_error("location_token", "The location selection has expired. Please choose the location again.")
        elif abs(float(payload["lat"]) - float(lat)) > 1e-5 or abs(float(payload["lng"]) - float(lon)) > 1e-5:
            self.add_error("location_token", "The place you selected and the pin on the map do not match. Please choose the location again.")
        elif not payload.get("service_area"):
            message = ("We could not verify this location's district. Complaints are accepted only in Bengaluru Urban or Bengaluru Rural."
                       if payload.get("service_area_status") == "unknown" else
                       "Sorry, RouteLync currently serves only Bengaluru Urban and Bengaluru Rural.")
            self.add_error("latitude", message)
        else:
            cleaned.update(formatted_address=payload["label"], place_id=payload["id"], location_source=payload["src"])
            area = cleaned.get("area")
            if area and area.service_district != payload["service_area"]:
                self.add_error("area", "The selected area does not belong to the verified service district.")

    def clean(self):
        cleaned = super().clean()
        if self.attempt is not None and self.attempt.image and not cleaned.get("image") and "image" not in self.errors:
            import mimetypes
            import os
            from django.core.files.uploadedfile import SimpleUploadedFile
            try:
                with self.attempt.image.open("rb") as handle:
                    stored = SimpleUploadedFile(os.path.basename(self.attempt.image.name), handle.read(),
                                                content_type=mimetypes.guess_type(self.attempt.image.name)[0] or "image/jpeg")
                validate_image_upload(stored)
                cleaned["image"] = stored
            except (OSError, ValidationError):
                self.add_error("image", "Please upload an image related to your complaint before submitting.")
        area, ward_number = cleaned.get("area"), cleaned.get("ward")
        cleaned["ward_number"] = ward_number
        if ward_number and not area:
            self.add_error("area", "Choose an area before entering a ward.")
        cleaned["ward"] = Ward.objects.filter(area=area, number=ward_number).first() if area and ward_number else None

        lat, lon = cleaned.get("latitude"), cleaned.get("longitude")
        cleaned.update(formatted_address="", place_id="", location_source="")
        if "latitude" not in self.errors and "longitude" not in self.errors:
            if lat is None and lon is None:
                self.add_error("latitude", "Please choose the location of the problem: search for it, tap the map, or use your current location.")
            elif (lat is None) != (lon is None):
                self.add_error(None, "The location is incomplete. Please choose it again.")
            elif lat == 0 and lon == 0:
                self.add_error(None, "The location (0, 0) is not valid. Please choose it again.")
            else:
                self._check_selection(cleaned, lat, lon)

        if self.citizen and not self.errors:
            since = timezone.now() - timedelta(hours=24)
            recent = Complaint.objects.filter(citizen=self.citizen, created_at__gte=since).count()
            if recent >= settings.MAX_COMPLAINTS_PER_DAY:
                raise ValidationError(
                    f"You have reached the limit of {settings.MAX_COMPLAINTS_PER_DAY} complaints in 24 hours.")
        return cleaned
