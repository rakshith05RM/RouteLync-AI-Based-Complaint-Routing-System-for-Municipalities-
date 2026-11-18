import csv
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse

from complaints.models import Complaint
from complaints.services.description_check import MESSAGES, Verdict, check_description

from .helpers import ComplaintTestCase

ESSAY = ("Last summer my family and I travelled to the hills for a long holiday. We stayed in a small cottage near the lake and every "
         "morning we walked through the forest and watched the birds. The food was delicious and the people were very friendly and kind. "
         "In the evenings we played cards and told stories by the fire. My children loved the boat rides and the ice cream shops. "
         "There was no crowd and we slept peacefully every night. The only thing I did not like was the long road back home, but overall "
         "it was a wonderful trip that we will remember forever and ever with great happiness in our hearts.")


class VerdictTests(SimpleTestCase):
    def verdict(self, text):
        return check_description(text).verdict

    def test_the_examples_in_the_brief_that_must_be_accepted(self):
        for text in ("There is a large pothole near the main bus stop, and vehicles are swerving to avoid it.",
                     "Garbage has not been collected for three days outside our apartment entrance.",
                     "The streetlight near the public park is broken, leaving the road dark at night.",
                     "Rainwater is accumulating near the school gate because the drain is blocked."):
            self.assertEqual(self.verdict(text), Verdict.OK, text)

    def test_a_short_but_meaningful_complaint_is_accepted(self):
        for text in ("A large pothole is near the school entrance", "Large pothole near the school gate", "Garbage near the market entrance"):
            self.assertTrue(check_description(text).accepted, text)

    def test_the_examples_in_the_brief_that_must_be_rejected(self):
        for text in ("asdfghjkl qwerty random words.", "Hello hello hello hello hello", "12345 67890 12345 67890 11111",
                     "!!!! ???? .... ,,,, ---- ****", "I am testing this website", ESSAY,
                     "Buy cheap watches now with a big discount, click the link to order", "tttttttttrttttttttttttttt nsomtehing"):
            self.assertFalse(check_description(text).accepted, text)

    def test_each_rejection_has_the_right_category_and_the_exact_message(self):
        cases = {Verdict.NONSENSE: "asdfghjkl qwertyuiop zxcvbnm poiuytre lkjhgfd",
                 Verdict.UNCLEAR: "The road near my house is a place where many people walk every day",
                 Verdict.UNSUPPORTED: "Please help me correct the name on my ration card as soon as possible",
                 Verdict.TOO_SHORT: "Pothole near school"}
        for expected, text in cases.items():
            result = check_description(text)
            self.assertEqual(result.verdict, expected, text)
            self.assertTrue(result.message and result.label)
        self.assertEqual(MESSAGES[Verdict.NONSENSE], "Your complaint could not be submitted because the description does not explain a municipal issue. Please describe the problem clearly.")
        self.assertEqual(MESSAGES[Verdict.UNCLEAR], "We could not identify the issue from your description. Please explain what happened and where it occurred.")
        self.assertEqual(MESSAGES[Verdict.UNSUPPORTED], "This issue is outside the currently supported complaint categories. Please review the supported categories or contact the appropriate municipal authority.")
        self.assertIn("Please explain what happened and where it occurred.", check_description("Pothole near school").message)

    def test_a_long_essay_is_rejected_but_a_long_real_complaint_is_not(self):
        self.assertEqual(self.verdict(ESSAY), Verdict.UNCLEAR)
        long_real = ("The drain in front of our house has been blocked for two weeks and dirty water overflows onto the road every time it rains. "
                     "The smell is terrible and mosquitoes are breeding everywhere. We have complained to the ward office twice but nobody came. "
                     "Children walk through this water to reach the school and several of them have fallen ill. Please clear the drain urgently.")
        self.assertEqual(self.verdict(long_real), Verdict.OK)

    def test_word_count_is_not_the_only_test(self):
        self.assertFalse(check_description("ok " * 40).accepted)                                       # many words, no meaning
        self.assertFalse(check_description("garbage " * 40).accepted)                                  # a real word repeated
        self.assertFalse(check_description("the quick brown fox jumps over the lazy dog today").accepted)   # enough words, no issue
        self.assertTrue(check_description("Potholes near our school gate").accepted)

    def test_a_good_title_cannot_rescue_a_description_that_explains_nothing(self):
        self.assertFalse(check_description("It is very big and dangerous for the bikes").accepted)
        self.assertFalse(check_description("The quick brown fox jumps over the lazy dog today").accepted)

    def test_local_language_text_is_not_rejected_but_is_flagged_for_a_person(self):
        result = check_description("ರಸ್ತೆಯ ಬೀದಿ ದೀಪ ಮೂರು ದಿನಗಳಿಂದ ಕೆಲಸ ಮಾಡುತ್ತಿಲ್ಲ ದಯವಿಟ್ಟು ಸರಿಪಡಿಸಿ")
        self.assertEqual(result.verdict, Verdict.REVIEW)
        self.assertTrue(result.accepted)
        hindi = check_description("हमारी गली में तीन दिन से कचरा नहीं उठाया गया है कृपया जल्दी साफ करवाइए")
        self.assertTrue(hindi.accepted)
        self.assertFalse(check_description("१२३४५ ६७८९० १२३४५ ६७८९० ११११११").accepted)           # digits in another script

    def test_links_and_spam_are_refused(self):
        self.assertFalse(check_description("Visit http://spam.example now for the garbage and pothole offers").accepted)
        self.assertEqual(self.verdict("Win a free prize in our lottery and subscribe to get your coupon today"), Verdict.NONSENSE)

    def test_a_municipal_word_next_to_an_out_of_scope_matter_is_still_accepted(self):
        self.assertTrue(check_description("The pothole near the bus stop and the broken road need repair for the drivers").accepted)

    def test_ambiguous_words_do_not_count_alone(self):
        self.assertFalse(check_description("My laptop battery drains very fast what should I do").accepted)
        self.assertFalse(check_description("I like the light of the evening and the water in the lake").accepted)


class MeasuredExampleSetsTests(SimpleTestCase):
    """Regression guard: the checker must keep giving the right answer on the example files. These sets were used while
    the vocabulary was written, so passing them shows the rules still work, NOT how well they generalise."""

    def rows(self, name):
        with open(Path(settings.DATASETS_DIR) / name, encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def wrong(self, name, key="expected"):
        out = []
        for r in self.rows(name):
            if check_description(r["text"]).accepted != (r[key] == "accept"):
                out.append((r[key], r["text"][:60]))
        return out

    def test_example_files(self):
        for name in ("description_validation_examples.csv", "description_heldout.csv", "description_heldout2.csv"):
            self.assertEqual(self.wrong(name), [], name)

    def test_the_independent_hand_written_challenge_complaints_are_all_accepted(self):
        rows = self.rows("challenge_set.csv")
        rejected = [r["text"][:60] for r in rows if not check_description(r["text"]).accepted]
        self.assertEqual(rejected, [])


class FormEnforcementTests(ComplaintTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.citizen)
        self.url = reverse("complaints:new")

    def test_each_kind_of_bad_description_is_refused_with_its_message(self):
        cases = {"asdfghjkl qwertyuiop zxcvbnm poiuytre lkjhgfd": MESSAGES[Verdict.NONSENSE],
                 "The road near my house is a place where many people walk every day": MESSAGES[Verdict.UNCLEAR],
                 "Please help me correct the name on my ration card as soon as possible": MESSAGES[Verdict.UNSUPPORTED]}
        for text, message in cases.items():
            response = self.client.post(self.url, self.payload(title="A problem near my home", description=text))
            self.assertEqual(response.status_code, 200, text)
            self.assertContains(response, message)
            self.assertContains(response, "No complaint was created")
        self.assertFalse(Complaint.objects.exists())

    def test_invalid_text_never_reaches_routing_but_valid_text_does(self):
        with mock.patch("complaints.views.citizen.route_complaint") as route:
            self.client.post(self.url, self.payload(description="tttttttttrttttttttttttttt nsomtehing"))
            self.client.post(self.url, self.payload(description="I am testing this website"))
            route.assert_not_called()
            self.client.post(self.url, self.payload())
            route.assert_called_once()

    def test_the_browser_cannot_supply_a_verdict_category_or_department(self):
        forged = self.payload(description="tttttttttrttttttttttttttt nsomtehing", verdict="OK", validation="valid", category="ELECTRICITY",
                              department="1", ai_confidence="0.99", predicted_department="1")
        self.client.post(self.url, forged)
        self.assertFalse(Complaint.objects.exists())
        self.client.post(self.url, self.payload(verdict="OK", category="ELECTRICITY", department="1", ai_confidence="0.99", priority="CRITICAL"))
        c = Complaint.objects.get()
        self.assertIsNone(c.ai_confidence)                       # no model is active here: routing sent it to a person
        self.assertNotEqual(c.priority, "CRITICAL")              # priority comes from the server's rules only

    def test_a_valid_description_with_a_missing_photo_is_refused_for_the_photo(self):
        response = self.client.post(self.url, self.payload(image=None))
        self.assertContains(response, "Please upload an image related to your complaint before submitting.")
        self.assertFalse(Complaint.objects.exists())

    def test_a_local_language_complaint_is_accepted_and_goes_to_a_person(self):
        response = self.client.post(self.url, self.payload(title="ಬೀದಿ ದೀಪ ಸಮಸ್ಯೆ", description="ರಸ್ತೆಯ ಬೀದಿ ದೀಪ ಮೂರು ದಿನಗಳಿಂದ ಕೆಲಸ ಮಾಡುತ್ತಿಲ್ಲ ದಯವಿಟ್ಟು ಸರಿಪಡಿಸಿ"))
        c = Complaint.objects.get()
        self.assertRedirects(response, reverse("complaints:detail", args=[c.pk]))
        self.assertEqual(c.status, "NEEDS_VERIFICATION")

    def test_unsupported_rejection_lists_the_supported_categories(self):
        from accounts.tests.helpers import make_department
        make_department("ELECTRICITY"); make_department("ROADS")
        response = self.client.post(self.url, self.payload(title="Ration card", description="Please help me correct the name on my ration card as soon as possible"))
        self.assertContains(response, "Supported categories: electricity, roads")
