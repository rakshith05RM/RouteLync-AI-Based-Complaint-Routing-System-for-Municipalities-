"""
Single source of truth for "where does each role land after login".

Later phases replace the placeholder targets below with the real dashboards;
nothing else in the project needs to change.
"""
from django.urls import reverse

from .models import Role

ROLE_HOME_URL_NAMES = {
    Role.CITIZEN: "complaints:my_complaints",     # Phase 4 -> own complaints (tracking detail in Phase 8)
    Role.OFFICER: "officer:dashboard",
    Role.FIELD_WORKER: "worker:dashboard",
    Role.ADMIN: "adminpanel:dashboard",
}


def home_url_for(user) -> str:
    return reverse(ROLE_HOME_URL_NAMES.get(user.role, "core:home"))
