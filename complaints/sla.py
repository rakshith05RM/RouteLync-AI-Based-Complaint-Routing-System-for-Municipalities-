"""Service-level helpers. Deadline = submission time + SLA hours for the complaint's priority."""
from dataclasses import dataclass

from django.utils import timezone


@dataclass(frozen=True)
class SlaState:
    is_overdue: bool
    seconds: int          # remaining seconds (negative when overdue)
    label: str


def _format(seconds: int) -> str:
    seconds = abs(int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days} d {hours} h"
    if hours:
        return f"{hours} h {minutes} min" if minutes else f"{hours} h"
    return f"{minutes} min"


def sla_state(deadline, now=None) -> SlaState:
    if deadline is None:
        return SlaState(False, 0, "No deadline set")
    now = now or timezone.now()
    seconds = int((deadline - now).total_seconds())
    if seconds >= 0:
        return SlaState(False, seconds, f"{_format(seconds)} remaining")
    return SlaState(True, seconds, f"Overdue by {_format(seconds)}")
