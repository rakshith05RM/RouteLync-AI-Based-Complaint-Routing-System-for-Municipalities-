from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.RoleLoginView.as_view(), name="login"),
    path("verify-email/", views.VerifyEmailView.as_view(), name="verify_email"),
    path("verify-email/resend/", views.resend_code, name="resend_code"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),  # POST only (Django 5)
    path("dashboard/", views.dashboard_router, name="dashboard"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("password/change/", views.ChangePasswordView.as_view(), name="password_change"),

    # Forgot / reset password: Django's built-in, secure token mechanism
    path("password/reset/", views.ThrottledPasswordResetView.as_view(
        template_name="accounts/password_reset_form.html",
        email_template_name="accounts/password_reset_email.txt",
        subject_template_name="accounts/password_reset_subject.txt",
        success_url=reverse_lazy("accounts:password_reset_done")), name="password_reset"),
    path("password/reset/sent/", auth_views.PasswordResetDoneView.as_view(
        template_name="accounts/password_reset_done.html"), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", views.ConfirmPasswordResetView.as_view(
        template_name="accounts/password_reset_confirm.html",
        success_url=reverse_lazy("accounts:password_reset_complete")), name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(
        template_name="accounts/password_reset_complete.html"), name="password_reset_complete"),

    # Role landing pages (placeholders until later phases)
]
