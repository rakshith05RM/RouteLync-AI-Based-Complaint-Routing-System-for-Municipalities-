import logging

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from django.urls import reverse_lazy
from django.views.generic import FormView

from django.conf import settings
from django.contrib.auth.views import PasswordResetView

from . import emails, otp, throttle
from .models import Role, User
from .registration import register_citizen
from .forms import (CitizenRegistrationForm, DeliveryAwarePasswordResetForm, EmailAuthenticationForm, ProfileForm,
                    VerifyCodeForm)
from .roles import home_url_for

logger = logging.getLogger("routelync")
PENDING_KEY = "pending_verification_email"


@login_required
def dashboard_router(request):
    """After authentication Django decides the landing page from the user's role."""
    return redirect(home_url_for(request.user))


class RegisterView(FormView):
    template_name = "accounts/register.html"
    form_class = CitizenRegistrationForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(home_url_for(request.user))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        if not throttle.allow("register", throttle.client_ip(self.request), settings.REGISTER_LIMIT_PER_IP, 3600):
            logger.warning("Registration rate limit hit from %s", throttle.client_ip(self.request))
            form.add_error(None, "Too many accounts have been created from this network recently. Please try again later.")
            return self.form_invalid(form)
        result = register_citizen(form.cleaned_data)
        self.request.session[PENDING_KEY] = form.cleaned_data["email"]
        if result.delivery_failed:
            messages.error(self.request, "We could not send the verification email right now. Check the address and press "
                                         "\"Send a new code\", or try again in a few minutes.")
        else:
            messages.success(self.request, "If this address can be used, we have sent a 6-digit verification code to it. "
                                           "Enter the code below to finish creating your account.")
        return redirect("accounts:verify_email")


class RoleLoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        # Used when there is no safe ?next= parameter. Django already blocks open redirects.
        return home_url_for(self.request.user)

    def form_invalid(self, form):
        if getattr(form, "unverified_user", None) is not None:       # right password, but the email is not verified yet
            self.request.session[PENDING_KEY] = form.unverified_user.email
            messages.info(self.request, "Please verify your email address first. Enter the code we sent, or ask for a new one.")
            return redirect("accounts:verify_email")
        return super().form_invalid(form)


# ---------------------------------------------------------------- Profile
class ProfileView(LoginRequiredMixin, FormView):
    template_name = "accounts/profile.html"
    form_class = ProfileForm
    success_url = reverse_lazy("accounts:profile")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Profile updated.")
        return super().form_valid(form)


class ChangePasswordView(LoginRequiredMixin, SuccessMessageMixin, auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:profile")
    success_message = "Password changed."

    def form_valid(self, form):
        response = super().form_valid(form)
        try:
            emails.send_password_changed_notice(form.user)
        except emails.EmailDeliveryError:
            logger.warning("Password-changed notice could not be sent to user %s", form.user.pk)
        return response



class ConfirmPasswordResetView(auth_views.PasswordResetConfirmView):
    """After a successful reset: the mailbox is proven to be theirs, and they are told by email (never the password)."""

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.user
        if not user.email_verified:
            user.email_verified = True
            user.save(update_fields=["email_verified", "updated_at"])
        try:
            emails.send_password_changed_notice(user)
        except emails.EmailDeliveryError:
            logger.warning("Password-changed notice could not be sent to user %s", user.pk)
        return response


class ThrottledPasswordResetView(PasswordResetView):
    form_class = DeliveryAwarePasswordResetForm

    """Limits how many reset emails one address / network can trigger. When the limit is hit the user sees the
    same "check your email" page, so the limit does not reveal which addresses have accounts."""

    def form_valid(self, form):
        ip, email = throttle.client_ip(self.request), form.cleaned_data["email"]
        within = (throttle.allow("reset-ip", ip, settings.RESET_LIMIT_PER_IP, 3600)
                  & throttle.allow("reset-email", email, settings.RESET_LIMIT_PER_EMAIL, 3600))
        if not within:
            logger.warning("Password-reset rate limit hit for %s from %s", email, ip)
            return redirect(self.get_success_url())
        response = super().form_valid(form)
        if form.delivery_failed:                       # never tell the person it was sent when it was not
            form.add_error(None, "We could not send the email right now. Please try again in a few minutes.")
            return self.form_invalid(form)
        return response


class VerifyEmailView(FormView):
    """Step 2 of registration: enter the emailed code. Every failure gives the same message."""

    template_name = "accounts/verify_email.html"
    form_class = VerifyCodeForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(home_url_for(request.user))
        if not request.session.get(PENDING_KEY):
            return redirect("accounts:register")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["email"] = self.request.session.get(PENDING_KEY)
        ctx["otp_minutes"] = settings.OTP_TTL_MINUTES
        return ctx

    def form_valid(self, form):
        email = self.request.session[PENDING_KEY]
        if not throttle.allow("otp-verify", email, settings.OTP_VERIFY_LIMIT_PER_HOUR, 3600):
            form.add_error("code", "Too many attempts. Please wait a while before trying again.")
            return self.form_invalid(form)
        user = User.objects.filter(email__iexact=email, email_verified=False, role=Role.CITIZEN, is_active=True).first()
        if user is None or not otp.verify_otp(user, form.cleaned_data["code"]):
            form.add_error("code", "That code is not valid or has expired.")
            return self.form_invalid(form)
        del self.request.session[PENDING_KEY]
        login(self.request, user, backend="django.contrib.auth.backends.ModelBackend")
        logger.info("Email verified for user %s", user.pk)
        messages.success(self.request, "Your email address is verified. Welcome to RouteLync!")
        return redirect(home_url_for(user))


@require_POST
def resend_code(request):
    """POST: email a new code to the address being verified. The reply never says whether the address has an account."""
    email = request.session.get(PENDING_KEY)
    if not email:
        return redirect("accounts:register")
    ip = throttle.client_ip(request)
    if not (throttle.allow("otp-resend-ip", ip, 20, 3600) and throttle.allow("otp-resend-email", email, 10, 3600)):
        messages.error(request, "Too many requests. Please try again later.")
        return redirect("accounts:verify_email")
    user = User.objects.filter(email__iexact=email, email_verified=False, role=Role.CITIZEN, is_active=True).first()
    if user is not None:
        try:
            emails.send_verification_code(user, otp.issue_otp(user))
        except otp.OTPCooldown as exc:
            messages.warning(request, f"Please wait {exc.seconds_left} seconds before asking for another code.")
            return redirect("accounts:verify_email")
        except otp.OTPRateLimited as exc:
            messages.error(request, str(exc))
            return redirect("accounts:verify_email")
        except emails.EmailDeliveryError:
            messages.error(request, "We could not send the email right now. Please try again in a few minutes.")
            return redirect("accounts:verify_email")
    messages.success(request, "If this address can be used, a new code has been sent.")
    return redirect("accounts:verify_email")
