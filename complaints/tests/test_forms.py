from django.test import override_settings

from complaints.forms import ComplaintForm
from complaints.models import Complaint
from departments.models import Area

from .helpers import ComplaintTestCase


class ComplaintFormTests(ComplaintTestCase):
    def form(self, **over):
        data, files = self.form_args(**over)
        return ComplaintForm(data, files, citizen=self.citizen)

    def test_a_valid_form_has_coordinates(self):
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(str(form.cleaned_data["latitude"]), "12.925000")

    def test_the_location_requires_a_verified_pin(self):
        form = self.form(latitude="", longitude="")
        self.assertFalse(form.is_valid())
        self.assertIn("choose the location of the problem", form.errors["latitude"][0])

    def test_the_photo_is_required(self):
        form = self.form(image=None)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["image"], ["Please upload an image related to your complaint before submitting."])

    def test_text_is_trimmed(self):
        form = self.form(title="   Streetlight   not working  ", street="  4th   Main Road ")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["title"], "Streetlight not working")
        self.assertEqual(form.cleaned_data["street"], "4th Main Road")

    def test_required_fields(self):
        for field in ("title", "description", "location_search", "address_text"):
            form = self.form(**{field: ""})
            self.assertFalse(form.is_valid(), field)
            self.assertIn(field, form.errors)

    def test_area_ward_and_street_are_optional(self):
        form = self.form(area="", ward="", street="")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["area"])
        self.assertIsNone(form.cleaned_data["ward"])
        self.assertEqual(form.cleaned_data["street"], "")

    def test_area_choices_include_five_urban_corps_and_four_rural_taluks(self):
        names = set(ComplaintForm(citizen=self.citizen).fields["area"].queryset.values_list("name", flat=True))
        self.assertTrue({
            "North Corporation", "South Corporation", "Central Corporation", "East Corporation",
            "West Corporation", "Devanahalli Taluk", "Doddaballapura Taluk", "Hoskote Taluk",
            "Nelamangala Taluk",
        }.issubset(names))

    def test_area_must_match_the_verified_district(self):
        rural_area = Area.objects.get(name="Devanahalli Taluk")
        form = self.form(area=rural_area.pk)
        self.assertIn("area", form.errors)
        self.assertIn("verified service district", form.errors["area"][0])

    def test_meaningless_description_rejected(self):
        for bad in ("abc", "test", "hello", "aaaaaaa"):
            self.assertIn("description", self.form(description=bad).errors, bad)

    def test_typed_ward_number_is_accepted_for_selected_area(self):
        form = self.form(ward=999)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["ward_number"], 999)
        self.assertIsNone(form.cleaned_data["ward"])

    def test_existing_ward_suggestion_resolves_to_its_area_record(self):
        form = self.form(ward=self.ward.number)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["ward"], self.ward)

    def test_nonexistent_ward_rejected(self):
        self.assertIn("ward", self.form(ward=99999).errors)
        self.assertIn("ward", self.form(ward="abc").errors)

    def test_valid_gps_is_rounded_to_six_places(self):
        form = self.form(latitude="12.9250123456", longitude="77.5938")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(str(form.cleaned_data["latitude"]), "12.925012")

    def test_invalid_gps_values_rejected(self):
        for lat, lon in (("91", "77"), ("-91", "77"), ("12", "181"), ("12", "-181"), ("abc", "77"), ("NaN", "77")):
            self.assertFalse(self.form(latitude=lat, longitude=lon).is_valid(), (lat, lon))

    def test_half_gps_and_null_island_rejected(self):
        self.assertFalse(self.form(latitude="12.9", longitude="").is_valid())
        self.assertFalse(self.form(latitude="", longitude="77.5").is_valid())
        self.assertFalse(self.form(latitude="0", longitude="0").is_valid())

    @override_settings(MAX_COMPLAINTS_PER_DAY=2)
    def test_daily_limit(self):
        for i in range(2):
            Complaint.objects.create(citizen=self.citizen, title=f"Existing {i}", description="x" * 30)
        form = self.form()
        self.assertFalse(form.is_valid())
        self.assertIn("limit", form.non_field_errors()[0])


class CompulsoryDescriptionTests(ComplaintTestCase):
    def form(self, **over):
        files = over.pop("files", None)
        data, default_files = self.form_args(**over)
        return ComplaintForm(data, files if files is not None else default_files, citizen=self.citizen)

    def test_description_cannot_be_missing_or_blank(self):
        for value in ("", "   ", "\n\n\t"):
            form = self.form(description=value)
            self.assertFalse(form.is_valid(), repr(value))
            self.assertIn("description", form.errors)

    def test_a_photo_alone_is_never_enough(self):
        from .helpers import make_upload
        form = self.form(description="", files={"image": make_upload("proof.png")})
        self.assertFalse(form.is_valid())
        self.assertIn("description", form.errors)
        self.assertNotIn("image", form.errors)             # the photo itself is fine; the missing text is the problem

    def test_minimum_word_count_is_enforced_with_a_helpful_message(self):
        four = "Streetlight near junction broken"          # 4 words
        five = "Streetlight near the junction broken"      # 5 words
        bad = self.form(description=four)
        self.assertFalse(bad.is_valid())
        self.assertIn("at least 5 words (you wrote 4)", bad.errors["description"][0])
        self.assertTrue(self.form(description=five).is_valid())

    def test_padding_with_filler_does_not_count(self):
        for padded in ("test test test test test test test test test", "hello hello hello hello hello hello hello hello",
                       "aaaa bbbb cccc dddd eeee ffff gggg hhhh", "asdf qwer zxcv asdf qwer zxcv asdf qwer"):
            self.assertFalse(self.form(description=padded).is_valid(), padded)

    def test_the_minimum_can_be_changed_in_settings(self):
        with override_settings(COMPLAINT_MIN_WORDS=5):
            self.assertTrue(self.form(description="Streetlight near the junction broken since yesterday").is_valid())
        with override_settings(COMPLAINT_MIN_WORDS=12):
            self.assertFalse(self.form(description="Streetlight near the main junction is not working").is_valid())

    def test_training_examples_keep_a_lower_bar_than_citizen_input(self):
        from complaints.validators import validate_training_text
        validate_training_text("Streetlight stopped working yesterday")      # 4 words: fine as a training example
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            from complaints.validators import validate_description
            validate_description("Streetlight stopped working yesterday")

    def test_form_page_explains_why_the_description_is_required(self):
        from django.urls import reverse
        self.client.force_login(self.citizen)
        page = self.client.get(reverse("complaints:new")).content.decode()
        self.assertIn("at least 5 words", page)
        self.assertIn("RouteLync reads this text", page)
        self.assertIn("Photo of the problem", page)
        self.assertIn('id="desc-words"', page)
        self.assertRegex(page, r'<textarea[^>]*name="description"[^>]*required')
