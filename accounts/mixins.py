"""
Backend authorisation helpers (hiding a button in HTML is never enough).

Behaviour:
  * anonymous user        -> redirected to the login page
  * wrong role            -> HTTP 403 (friendly error page)
Phase 3 adds DepartmentScopedMixin on top of these.
"""
from functools import wraps

from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


class RoleRequiredMixin(UserPassesTestMixin):
    """Class-based views: set `allowed_roles = (Role.OFFICER,)` etc."""

    allowed_roles: tuple = ()

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and user.is_active and user.role in self.allowed_roles


def role_required(*roles):
    """Function-based views: @role_required(Role.ADMIN)."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not request.user.is_active or request.user.role not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
