"""
Department-scoped authorisation. Phase 7 builds every officer query on top of this, so an
Electricity officer can never receive Water Supply rows, whatever URL they type.
"""
import logging

from django.core.exceptions import PermissionDenied
from django.utils.functional import cached_property

from accounts.mixins import RoleRequiredMixin
from accounts.models import Role

from .services import department_for

logger = logging.getLogger("routelync")


class DepartmentScopedMixin(RoleRequiredMixin):
    """
    For officer (default) or field-worker views. Grants access only when the user's role is
    allowed AND they have a profile in an ACTIVE department. Exposes `self.department`.
    """

    allowed_roles = (Role.OFFICER,)

    @cached_property
    def department(self):
        return department_for(self.request.user)

    def test_func(self):
        if not super().test_func():
            return False
        if self.department is None or not self.department.is_active:
            logger.warning("User %s has no active department; access denied", self.request.user.pk)
            return False
        return True

    def scope_queryset(self, queryset, field="department"):
        """Restrict any queryset to the user's own department."""
        return queryset.filter(**{field: self.department})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["department"] = self.department
        return ctx


def ensure_same_department(user, department):
    """Object-level check for single records: raises 403 if the object is another department's."""
    if department_for(user) != department:
        raise PermissionDenied
