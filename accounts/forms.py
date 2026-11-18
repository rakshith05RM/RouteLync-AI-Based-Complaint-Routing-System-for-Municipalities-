import logging
from urllib.parse import urlsplit

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm
from django.template import loader
from django.contrib.auth.password_validation import password_validators_help_text_html, validate_password
from django.core.exceptions import ImproperlyConfigured, ValidationError

from core.mailer import send_routelync_email
from core.validators import mobile_number_validator, validate_person_name

from . import throttle
from .models import CitizenProfile, Role

User = get_user_model()
logger = logging.getLogger("routelync")


class CitizenRegistrationForm(forms.Form):
    """
    Registration is for citizens only. The role is NEVER read from the request;
    the service code below sets it, so a tampered POST cannot create an admin.
    """

    full_name = forms.CharField(max_length=150, validators=[validate_person_name],
                                widget=forms.TextInput(attrs={"autocomplete": "name"}))
    email = forms.EmailField(max_length=254, widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    phone = forms.CharField(label="Mobile number", max_length=10, validators=[mobile_number_validator],
                            help_text="10-digit mobile number",
                            widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "tel-national"}))
    address = forms.CharField(required=False, max_length=300,
                              widget=forms.Textarea(attrs={"rows": 2, "autocomplete": "street-address"}),
                              help_text="Optional. You can enter the exact location for each complaint later.")
    password1 = forms.CharField(label="Password", strip=False,
                                widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                help_text=password_validators_help_text_html())
    password2 = forms.CharField(label="Confirm password", strip=False,
                                widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def clean_full_name(self):
        return " ".join(self.cleaned_data["full_name"].split())  # trim and collapse whitespace

    def clean_email(self):
        # Whether the address is already registered is deliberately NOT checked here (see accounts/registration.py).
        return self.cleaned_data["email"].strip().lower()

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords do not match.")
        elif p1:
            # Passing a user object lets the "too similar to your details" validator work.
            candidate = User(email=cleaned.get("email", ""), full_name=cleaned.get("full_name", ""))
            try:
                validate_password(p1, user=candidate)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned

    def save(self):
        from django.db import transaction

        data = self.cleaned_data
        with transaction.atomic():  # user + profile are created together or not at all
            user = User.objects.create_user(
                email=data["email"], password=data["password1"],
                full_name=data["full_name"], phone=data["phone"], role=Role.CITIZEN,
            )
            CitizenProfile.objects.create(user=user, address=data.get("address", "").strip())
        return user


class EmailAuthenticationForm(AuthenticationForm):
    """Login by email with brute-force lockout. Error text never reveals which part was wrong."""

    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}))

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Incorrect email or password.",
        "locked": "Too many failed attempts. Please try again in 15 minutes or reset your password.",
    }

    unverified_user = None

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.role == Role.CITIZEN and not user.email_verified:
            self.unverified_user = user
            raise ValidationError("Please verify your email address before signing in.", code="unverified")

    def clean(self):
        email = self.cleaned_data.get("username", "")
        ip = throttle.client_ip(self.request)
        if email and throttle.is_locked(email, ip):
            logger.warning("Login locked out for %s from %s", email, ip)
            raise ValidationError(self.error_messages["locked"], code="locked")
        try:
            cleaned = super().clean()
        except ValidationError as exc:
            if email and getattr(exc, "code", None) != "unverified":      # unverified is not a wrong-password attempt
                throttle.register_failure(email, ip)
            raise
        throttle.reset(email, ip)
        return cleaned


class ProfileForm(forms.Form):
    """Email and role are deliberately not editable here (email change needs verification)."""

    full_name = forms.CharField(max_length=150, validators=[validate_person_name])
    phone = forms.CharField(label="Mobile number", max_length=10, validators=[mobile_number_validator])
    address = forms.CharField(required=False, max_length=300, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if not user.is_citizen:
            del self.fields["address"]  # only citizens have an address profile
        else:
            profile = CitizenProfile.objects.filter(user=user).first()
            self.fields["address"].initial = profile.address if profile else ""
        self.fields["full_name"].initial = user.full_name
        self.fields["phone"].initial = user.phone

    def clean_full_name(self):
        return " ".join(self.cleaned_data["full_name"].split())

    def save(self):
        from django.db import transaction

        with transaction.atomic():
            self.user.full_name = self.cleaned_data["full_name"]
            self.user.phone = self.cleaned_data["phone"]
            self.user.save(update_fields=["full_name", "phone", "updated_at"])
            if self.user.is_citizen:
                profile, _ = CitizenProfile.objects.get_or_create(user=self.user)
                profile.address = self.cleaned_data.get("address", "").strip()
                profile.save(update_fields=["address"])
        return self.user


class VerifyCodeForm(forms.Form):
    code = forms.CharField(label="Verification code", max_length=12,
                           widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code",
                                                         "autofocus": True, "placeholder": "6-digit code"}))


class DeliveryAwarePasswordResetForm(PasswordResetForm):
    """Django's own form swallows email errors (so a failure cannot reveal which addresses exist) and the page then
    claims success. We record the failure instead, so the person is told the email could not be sent."""

    delivery_failed = False

    def save(self, *args, **kwargs):
        site_url = urlsplit(settings.SITE_URL)
        if site_url.scheme not in {"http", "https"} or not site_url.netloc or site_url.username or site_url.password:
            raise ImproperlyConfigured("SITE_URL must be an absolute http:// or https:// URL without credentials.")
        kwargs["domain_override"] = site_url.netloc
        kwargs["use_https"] = site_url.scheme == "https"
        return super().save(*args, **kwargs)

    def send_mail(self, subject_template_name, email_template_name, context, from_email, to_email, html_email_template_name=None):
        subject = "".join(loader.render_to_string(subject_template_name, context).splitlines())
        body = loader.render_to_string(email_template_name, context)
        try:
            html_body = loader.render_to_string(html_email_template_name, context) if html_email_template_name else None
            send_routelync_email(subject, body, [to_email], from_email=from_email, html_message=html_body)
        except Exception:  # noqa: BLE001 - any SMTP, network or timeout problem
            self.delivery_failed = True
            logger.error("Password-reset email could not be sent")
