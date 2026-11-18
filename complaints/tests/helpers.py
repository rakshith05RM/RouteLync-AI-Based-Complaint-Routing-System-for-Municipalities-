import os
import shutil
import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from accounts.models import Role
from accounts.tests.helpers import make_department, make_user
from departments.models import Area, Ward

DESCRIPTION = "The streetlight near the junction has not been working for three days and the road is very dark at night."


def make_image_bytes(fmt="PNG", size=(40, 30), exif=False, noise=False):
    # noise=True makes an incompressible image so its file size is predictably large
    img = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3)) if noise else Image.new("RGB", size, (200, 80, 40))
    buffer = BytesIO()
    kwargs = {}
    if exif and fmt == "JPEG":
        data = Image.Exif()
        data[271] = "TestCamera"          # Make
        data[305] = "TestSoftware"        # Software
        kwargs["exif"] = data
    img.save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()


def make_upload(name="photo.png", fmt="PNG", **kwargs):
    return SimpleUploadedFile(name, make_image_bytes(fmt, **kwargs), content_type="image/png")


class ComplaintTestCase(TestCase):
    """Isolates uploaded files in a temp dir and provides common fixtures."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media = tempfile.mkdtemp()
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.area = Area.objects.get_or_create(
            name="Jayanagar", defaults={"service_district": Area.ServiceDistrict.BENGALURU_URBAN})[0]
        self.ward = Ward.objects.get_or_create(area=self.area, number=154)[0]
        self.other_area = Area.objects.get_or_create(
            name="Whitefield", defaults={"service_district": Area.ServiceDistrict.BENGALURU_URBAN})[0]
        self.other_ward = Ward.objects.get_or_create(area=self.other_area, number=84)[0]
        self.citizen = make_user("citizen@example.com", Role.CITIZEN)

    def payload(self, **over):
        """POST data for client.post(): includes a valid photo unless image=None is passed."""
        data = {
            "title": "Streetlight not working near junction",
            "description": DESCRIPTION,
            "area": self.area.pk, "ward": self.ward.number,
            "street": "4th Main Road", "landmark": "Near Metro", "building": "",
            "address_text": "4th Main Road, near Jayanagar Metro station",
            "location_search": "Jayanagar 4th Main Road",
            "latitude": "12.925000", "longitude": "77.593800",
        }
        data["image"] = make_upload("evidence.png")
        data.update(over)
        if "location_token" not in over and data["latitude"] and data["longitude"]:
            try:
                float(data["latitude"])
                float(data["longitude"])
            except (TypeError, ValueError):
                pass
            else:
                from core.geo.service import sign_selection
                data["location_token"] = sign_selection(
                    self.citizen.pk, data["latitude"], data["longitude"], "photon:W42",
                    "4th Main Road, Jayanagar, Bengaluru Urban", "SEARCH",
                    district="Bengaluru Urban", area_hint="Jayanagar")
        if data["image"] is None:
            del data["image"]
        return data

    def form_args(self, **over):
        """(data, files) for building a ComplaintForm directly."""
        data = self.payload(**over)
        image = data.pop("image", None)
        return data, ({"image": image} if image is not None else {})
