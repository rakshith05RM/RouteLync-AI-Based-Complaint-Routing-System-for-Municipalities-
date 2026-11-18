import logging
from io import BytesIO

from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image, ImageOps

from departments.models import Ward

from .errors import WorkflowError
from ..models import (Complaint, ComplaintImage, ComplaintLocation, ComplaintStatus,
                      ComplaintStatusHistory, ImageKind)

logger = logging.getLogger("routelync")

_SAVE_OPTIONS = {"JPEG": {"quality": 85, "optimize": True}, "PNG": {"optimize": True}, "WEBP": {"quality": 85}}
_EXTENSION = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


def sanitize_image(upload) -> ContentFile:
    """
    Re-encode the (already validated) image. This drops EXIF/metadata, including any GPS position
    embedded by the phone camera (privacy), and removes anything appended to the file that is not
    pixel data. Orientation is applied first so photos are not rotated.
    """
    upload.seek(0)
    with Image.open(upload) as img:
        fmt = img.format
        img = ImageOps.exif_transpose(img)
        if fmt == "JPEG":
            img = img.convert("RGB")
        buffer = BytesIO()
        img.save(buffer, format=fmt, **_SAVE_OPTIONS[fmt])
    return ContentFile(buffer.getvalue(), name=f"upload{_EXTENSION[fmt]}")


@transaction.atomic
def submit_complaint(*, citizen, data, image) -> Complaint:
    """
    Save a validated complaint with its location, first history entry and optional image.
    All database writes happen in one transaction: if any step fails, nothing is saved.
    The image file is written last so a failure earlier cannot leave an orphan file.

    A complaint without a photo is never created, whatever calls this function.
    """
    if image is None:
        raise WorkflowError("Please upload an image related to your complaint before submitting.")
    area = data.get("area")
    ward = data.get("ward")
    if ward is None and data.get("ward_number") and area:
        ward, _ = Ward.objects.get_or_create(area=area, number=data["ward_number"])
    complaint = Complaint.objects.create(
        citizen=citizen, title=data["title"], description=data["description"])
    ComplaintLocation.objects.create(
        complaint=complaint, area=area, ward=ward, street=data.get("street", ""),
        landmark=data.get("landmark", ""), building=data.get("building", ""),
        address_text=data["address_text"],
        latitude=data.get("latitude"), longitude=data.get("longitude"),
        formatted_address=data.get("formatted_address", ""), place_id=data.get("place_id", ""),
        location_source=data.get("location_source", ""))
    ComplaintStatusHistory.objects.create(
        complaint=complaint, from_status="", to_status=ComplaintStatus.SUBMITTED,
        changed_by=citizen, note="Complaint submitted")
    if True:
        ComplaintImage.objects.create(
            complaint=complaint, image=sanitize_image(image), kind=ImageKind.EVIDENCE, uploaded_by=citizen)
    from . import alerts
    alerts.to_citizen(complaint, "SUBMITTED", f"Complaint {complaint.reference} was submitted successfully.")
    logger.info("Complaint %s submitted by user %s", complaint.reference, citizen.pk)
    return complaint
