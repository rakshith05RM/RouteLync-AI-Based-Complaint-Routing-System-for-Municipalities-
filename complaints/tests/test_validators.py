from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from complaints.validators import (normalize_text, validate_description, validate_image_upload,
                                   validate_street, validate_title)

from .helpers import DESCRIPTION, make_image_bytes, make_upload


class TextValidatorTests(SimpleTestCase):
    def test_valid_descriptions_pass(self):
        for text in (DESCRIPTION,
                     "Water pipeline has burst near the school and water is flowing on the road.",
                     "There is a large pothole on the road near the bus stop causing accidents."):
            validate_description(normalize_text(text))

    def test_meaningless_descriptions_rejected(self):
        bad = ["abc", "test", "hello", "aaaaaaa", "hello hello hello hello hello hello",
               "test test test test test test test", "aaaa bbbb cccc dddd eeee ffff gggg",
               "asdfghjkl qwertyuiop zxcvbnm asdfgh jklqwe", "12345 67890 12345 67890 12345",
               "!!!! ???? #### @@@@ $$$$ %%%% ^^^^", "x" * 25]
        for text in bad:
            with self.assertRaises(ValidationError, msg=text):
                validate_description(normalize_text(text))

    def test_length_limits(self):
        with self.assertRaises(ValidationError):
            validate_description("word " * 500)   # > 2000 characters
        with self.assertRaises(ValidationError):
            validate_description("too short")

    def test_links_rejected(self):
        with self.assertRaises(ValidationError):
            validate_description("Please visit http://spam.example now for the broken streetlight issue")

    def test_non_latin_text_is_not_flagged_as_gibberish(self):
        validate_description("ರಸ್ತೆಯ ಬೀದಿ ದೀಪ ಮೂರು ದಿನಗಳಿಂದ ಕೆಲಸ ಮಾಡುತ್ತಿಲ್ಲ ದಯವಿಟ್ಟು ಸರಿಪಡಿಸಿ")

    def test_title_and_street(self):
        validate_title("Garbage not collected")
        validate_street("4th Main Road")
        for fn, bad in ((validate_title, "test"), (validate_title, "zzzz"), (validate_street, "ab"), (validate_street, "hello")):
            with self.assertRaises(ValidationError, msg=bad):
                fn(bad)

    def test_normalize_trims_and_collapses_whitespace(self):
        self.assertEqual(normalize_text("  Hello   world \t again \n\n\n\n next  "), "Hello world again\n\nnext")
        self.assertEqual(normalize_text("a\x00b\x07c"), "abc")


class ImageValidatorTests(SimpleTestCase):
    def test_valid_formats_pass(self):
        for name, fmt in (("a.png", "PNG"), ("a.jpg", "JPEG"), ("a.jpeg", "JPEG"), ("a.webp", "WEBP")):
            validate_image_upload(make_upload(name, fmt))

    def test_text_file_renamed_to_jpg_rejected(self):
        fake = SimpleUploadedFile("evil.jpg", b"<?php echo 1; ?>" * 10, content_type="image/jpeg")
        with self.assertRaisesMessage(ValidationError, "not a valid image"):
            validate_image_upload(fake)

    def test_wrong_extension_rejected(self):
        for name in ("a.gif", "a.svg", "a.exe", "a"):
            with self.assertRaises(ValidationError, msg=name):
                validate_image_upload(SimpleUploadedFile(name, make_image_bytes("PNG")))

    def test_extension_must_match_content(self):
        with self.assertRaisesMessage(ValidationError, "does not match"):
            validate_image_upload(SimpleUploadedFile("a.jpg", make_image_bytes("PNG")))

    def test_gif_content_rejected_even_with_png_name(self):
        with self.assertRaises(ValidationError):
            validate_image_upload(SimpleUploadedFile("a.png", make_image_bytes("GIF")))

    def test_empty_file_rejected(self):
        with self.assertRaisesMessage(ValidationError, "empty"):
            validate_image_upload(SimpleUploadedFile("a.png", b""))

    @override_settings(MAX_IMAGE_SIZE_MB=0.001)   # about 1 KB
    def test_oversized_file_rejected(self):
        with self.assertRaisesMessage(ValidationError, "too large"):
            validate_image_upload(make_upload("big.png", size=(200, 200), noise=True))

    @override_settings(MAX_IMAGE_PIXELS_ALLOWED=1000)
    def test_too_many_pixels_rejected(self):
        with self.assertRaisesMessage(ValidationError, "dimensions"):
            validate_image_upload(make_upload("wide.png", size=(100, 100)))

    def test_truncated_image_rejected(self):
        data = make_image_bytes("PNG", size=(80, 80))
        with self.assertRaises(ValidationError):
            validate_image_upload(SimpleUploadedFile("cut.png", data[: len(data) // 2]))
