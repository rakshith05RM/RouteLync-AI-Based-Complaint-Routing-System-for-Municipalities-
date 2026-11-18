import logging

from django.shortcuts import render

logger = logging.getLogger("routelync")


def home(request):
    """Public landing page. Role-based redirect for signed-in users arrives in Phase 2."""
    return render(request, "home.html")


# ---- Friendly error pages: users never see tracebacks; details go to the log. ----
def permission_denied(request, exception=None):
    return render(request, "errors/403.html", status=403)


def page_not_found(request, exception=None):
    return render(request, "errors/404.html", status=404)


def server_error(request):
    logger.exception("Unhandled server error at %s", request.path)
    return render(request, "errors/500.html", status=500)


def csrf_failure(request, reason=""):
    """The form's security token was missing or expired (often a page left open too long)."""
    logger.warning("CSRF failure on %s: %s", request.path, reason)
    return render(request, "errors/csrf.html", status=403)


def bad_request(request, exception=None):
    return render(request, "errors/400.html", status=400)
