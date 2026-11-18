"""Dataset management: read, validate, de-duplicate, import and describe training data."""
import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction

from complaints.validators import normalize_text, validate_training_text
from departments.models import Department

from .exceptions import DatasetError
from .models import TrainingSample

TRUE_VALUES = {"1", "true", "yes", "y", "t"}


@dataclass
class ImportReport:
    rows_read: int = 0
    imported: int = 0
    duplicates: int = 0
    conflicts: list = field(default_factory=list)          # same text, different department
    invalid: list = field(default_factory=list)            # (row_number, reason)
    unknown_departments: Counter = field(default_factory=Counter)
    dry_run: bool = False

    def summary(self) -> str:
        return (f"rows read: {self.rows_read}, imported: {self.imported}, duplicates skipped: {self.duplicates}, "
                f"conflicting labels: {len(self.conflicts)}, invalid rows: {len(self.invalid)}, "
                f"unknown departments: {sum(self.unknown_departments.values())}"
                + (" (DRY RUN, nothing saved)" if self.dry_run else ""))


def _rows_from(handle) -> list[dict]:
    reader = csv.DictReader(handle)
    missing = {"text", "department_code"} - set(reader.fieldnames or [])
    if missing:
        raise DatasetError(f"CSV is missing required column(s): {', '.join(sorted(missing))}")
    return list(reader)


def read_csv(path) -> list[dict]:
    path = Path(path)
    if not path.is_file():
        raise DatasetError(f"Dataset file not found: {path}")
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return _rows_from(handle)


MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_UPLOAD_ROWS = 20_000


def read_csv_upload(upload) -> list[dict]:
    """Rows from an uploaded CSV (size, encoding and row count are limited)."""
    import io
    if upload.size > MAX_UPLOAD_BYTES:
        raise DatasetError("The file is larger than 2 MB.")
    try:
        text = upload.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        raise DatasetError("The file is not UTF-8 text.")
    try:
        rows = _rows_from(io.StringIO(text, newline=""))
    except csv.Error as exc:
        raise DatasetError(f"The file is not a valid CSV: {exc}")
    if len(rows) > MAX_UPLOAD_ROWS:
        raise DatasetError(f"The file has more than {MAX_UPLOAD_ROWS} rows.")
    return rows


def add_verified_sample(*, text, department, complaint=None):
    """One administrator-verified example. Returns (sample, "") or (None, reason)."""
    text = normalize_text(text)
    try:
        validate_training_text(text)
    except ValidationError as exc:
        return None, f"not usable as training text ({exc.messages[0]})"
    existing = TrainingSample.objects.filter(text_hash=TrainingSample.hash_text(text)).select_related("department").first()
    if existing:
        if existing.department_id == department.pk:
            return None, "an identical example already exists"
        return None, f"the same text is already labelled {existing.department.name}"
    sample = TrainingSample.objects.create(
        text=text, department=department, source=TrainingSample.Source.VERIFIED_COMPLAINT if complaint else TrainingSample.Source.IMPORTED,
        is_verified=True, dataset_version="verified", complaint=complaint)
    return sample, ""


def import_rows(rows, *, source=TrainingSample.Source.IMPORTED, version="", mark_verified=True,
                dry_run=False) -> ImportReport:
    """Validate every row; import the good ones. Idempotent: re-importing creates no duplicates."""
    report = ImportReport(dry_run=dry_run)
    departments = {d.code: d for d in Department.objects.all()}
    seen_in_file: dict[str, str] = {}
    to_create = []

    for number, row in enumerate(rows, start=2):  # row 1 is the CSV header
        report.rows_read += 1
        text = normalize_text(row.get("text") or "")
        code = (row.get("department_code") or "").strip().upper()

        if code not in departments:
            report.unknown_departments[code or "(blank)"] += 1
            continue
        try:
            validate_training_text(text)
        except ValidationError as exc:
            report.invalid.append((number, exc.messages[0]))
            continue

        digest = TrainingSample.hash_text(text)
        existing_code = seen_in_file.get(digest)
        if existing_code is None:
            found = TrainingSample.objects.filter(text_hash=digest).select_related("department").first()
            existing_code = found.department.code if found else None
        if existing_code is not None:
            if existing_code == code:
                report.duplicates += 1
            else:
                report.conflicts.append((number, text[:70], existing_code, code))
            continue

        seen_in_file[digest] = code
        verified = mark_verified if row.get("is_verified") in (None, "") else row["is_verified"].strip().lower() in TRUE_VALUES
        to_create.append(TrainingSample(
            text=text, department=departments[code], source=row.get("source") or source,
            is_verified=verified, dataset_version=row.get("dataset_version") or version))

    report.imported = len(to_create)
    if not dry_run and to_create:
        with transaction.atomic():
            for sample in to_create:          # save() computes text_hash; bulk_create would skip it
                sample.save()
    return report


def statistics(queryset=None) -> dict:
    """Dataset size, class balance and text lengths (verified rows are what training uses)."""
    qs = queryset if queryset is not None else TrainingSample.objects.all()
    verified = qs.filter(is_verified=True)
    per_class = dict(Counter(verified.values_list("department__code", flat=True)))
    lengths = [len(t.split()) for t in verified.values_list("text", flat=True)]
    counts = list(per_class.values())
    return {
        "total_rows": qs.count(),
        "verified_rows": verified.count(),
        "unverified_rows": qs.filter(is_verified=False).count(),
        "per_class": per_class,
        "imbalance_ratio": round(max(counts) / min(counts), 2) if counts else None,
        "mean_words": round(sum(lengths) / len(lengths), 1) if lengths else None,
        "min_words": min(lengths) if lengths else None,
        "max_words": max(lengths) if lengths else None,
        "by_source": dict(Counter(qs.values_list("source", flat=True))),
    }
