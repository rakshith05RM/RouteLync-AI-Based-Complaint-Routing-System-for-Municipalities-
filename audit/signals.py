from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .services import log_action


def _ip(request):
    return request.META.get("REMOTE_ADDR", "") if request is not None else ""


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    log_action(user, "LOGIN", target=user, summary=f"{user.full_name} signed in", details={"ip": _ip(request)})


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    if user is not None:
        log_action(user, "LOGOUT", target=user, summary=f"{user.full_name} signed out", details={"ip": _ip(request)})


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    attempted = str(credentials.get("email") or credentials.get("username") or "")[:100]   # never the password
    log_action(None, "LOGIN_FAILED", summary=f"Failed sign-in attempt for {attempted}", details={"ip": _ip(request)})
