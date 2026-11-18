from .models import CITIZEN_STATUS_LABELS


def citizen_timeline(complaint):
    """Citizen-safe progress: internal steps (AI processing, verification) are folded into plain
    wording, and consecutive steps that look identical to the citizen are shown once."""
    entries, previous = [], None
    for item in complaint.status_history.all():
        label = CITIZEN_STATUS_LABELS.get(item.to_status, item.to_status)
        if label != previous:
            entries.append({"label": label, "timestamp": item.timestamp})
            previous = label
    return entries


def citizen_tracker(complaint):
    """Step-by-step progress for the citizen: done / current / todo. After a reopen the work steps start over."""
    pre_routing = {"SUBMITTED", "AI_PROCESSING", "NEEDS_VERIFICATION"}
    routed, reached, stamps = False, set(), {}
    for item in complaint.status_history.all():
        status = str(item.to_status)
        if status == "REOPENED":
            reached.clear()
        if status not in pre_routing:
            routed = True
        reached.add(status)
        stamps[status] = item.timestamp
    status = str(complaint.status)
    dept = complaint.department.name if complaint.department_id else ""
    steps = [
        ("Submitted", True, stamps.get("SUBMITTED")),
        (f"Sent to {dept}" if dept else "Sent to department", routed, stamps.get("DEPARTMENT_ASSIGNED")),
        ("Field worker assigned", "ASSIGNED_TO_WORKER" in reached, stamps.get("ASSIGNED_TO_WORKER")),
        ("Work in progress", "IN_PROGRESS" in reached, stamps.get("IN_PROGRESS")),
        ("Resolved", status in ("RESOLVED", "CLOSED") or "RESOLVED" in reached, stamps.get("RESOLVED")),
        ("Closed", status == "CLOSED", stamps.get("CLOSED")),
    ]
    out, current_marked = [], False
    for label, done, stamp in steps:
        if done:
            state = "done"
        elif not current_marked and status not in ("REJECTED", "CLOSED"):
            state, current_marked = "current", True
        else:
            state = "todo"
        out.append({"label": label, "state": state, "timestamp": stamp if done else None})
    return out


def duplicate_panel(complaint, visible_queryset):
    """Suspected duplicates for the staff screens. Details of a complaint the viewer may not see
    (another department's) are never exposed: only the fact that a similar complaint exists."""
    outgoing = list(complaint.duplicate_flags.select_related("possible_duplicate_of"))
    incoming = list(complaint.duplicate_reports.select_related("complaint"))
    ids = {f.possible_duplicate_of_id for f in outgoing} | {f.complaint_id for f in incoming}
    visible = set(visible_queryset.filter(pk__in=ids).values_list("pk", flat=True)) if ids else set()

    def item(flag, other):
        return {"flag": flag, "other": other if other.pk in visible else None, "percent": round(flag.similarity * 100)}

    pending = [item(f, f.possible_duplicate_of) for f in outgoing if f.status == "PENDING"]
    reviewed = [item(f, f.possible_duplicate_of) for f in outgoing if f.status != "PENDING"]
    newer = [item(f, f.complaint) for f in incoming]
    return {"pending": pending, "reviewed": reviewed, "newer": newer, "any": bool(pending or reviewed or newer)}
