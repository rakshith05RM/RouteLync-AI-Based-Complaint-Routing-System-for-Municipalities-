"""Writes diagrams generated FROM THE CODE, so they cannot drift from the implementation:
docs/er_diagram.mmd (every table and relationship) and docs/lifecycle.mmd (allowed status changes)."""
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import models

OUR_APPS = ("accounts", "departments", "complaints", "ml_engine", "notifications", "audit")


def _type(field) -> str:
    return field.get_internal_type().replace("Field", "") or "Field"


class Command(BaseCommand):
    help = "Export the ER diagram and the complaint lifecycle diagram (Mermaid) to docs/."

    def handle(self, *args, **opts):
        docs = Path(settings.BASE_DIR) / "docs"
        docs.mkdir(exist_ok=True)
        lines, rels = ["erDiagram"], []
        count = 0
        for config in OUR_APPS:
            for model in apps.get_app_config(config).get_models():
                count += 1
                name = model.__name__
                lines.append(f"    {name} {{")
                for f in model._meta.concrete_fields:
                    marker = "PK" if f.primary_key else ("FK" if f.is_relation else ("UK" if f.unique else ""))
                    lines.append(f"        {_type(f)} {f.name} {marker}".rstrip())
                lines.append("    }")
                for f in model._meta.concrete_fields:
                    if f.is_relation and f.related_model._meta.app_label in OUR_APPS + ("auth",):
                        target = f.related_model.__name__
                        card = "||--||" if isinstance(f, models.OneToOneField) else "}o--||" if not f.null else "}o--o|"
                        rels.append(f"    {name} {card} {target} : {f.name}")
        (docs / "er_diagram.mmd").write_text("\n".join(lines + sorted(set(rels))) + "\n")

        from complaints.services.transitions import ALLOWED_TRANSITIONS
        st = ["stateDiagram-v2", "    [*] --> SUBMITTED"]
        for src, targets in ALLOWED_TRANSITIONS.items():
            for t in sorted(targets, key=str):
                st.append(f"    {src} --> {t}")
        st += ["    CLOSED --> [*]", "    REJECTED --> [*]"]
        (docs / "lifecycle.mmd").write_text("\n".join(st) + "\n")
        self.stdout.write(self.style.SUCCESS(f"Wrote docs/er_diagram.mmd ({count} tables) and docs/lifecycle.mmd"))
