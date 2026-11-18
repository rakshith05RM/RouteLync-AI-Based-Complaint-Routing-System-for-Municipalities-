from django.test import SimpleTestCase

from ml_engine.preprocessing import STOP_WORDS, analyse, clean_text, preprocess_text


class PreprocessingTests(SimpleTestCase):
    def tokens(self, text):
        return preprocess_text(text).split()

    def test_lowercase_punctuation_digits_and_ordinals_removed(self):
        out = self.tokens("The Street-Light isn't WORKING near 4th Main!! since 3 days")
        self.assertIn("streetlight", out)
        self.assertIn("not", out)
        self.assertIn("work", out)
        for bad in ("the", "4th", "3", "th", "!!"):
            self.assertNotIn(bad, out)

    def test_negations_and_direction_words_are_kept(self):
        self.assertIn("no", self.tokens("There is no water"))
        self.assertIn("not", self.tokens("The light is not working"))
        self.assertIn("without", self.tokens("We are without power"))
        self.assertIn("off", self.tokens("Power was cut off"))
        self.assertIn("out", self.tokens("Water is not coming out"))
        for word in ("no", "not", "nor", "never", "without", "off", "out", "down", "cannot"):
            self.assertNotIn(word, STOP_WORDS)

    def test_contractions_are_expanded(self):
        self.assertEqual(clean_text("can't"), "cannot")
        self.assertIn("not", clean_text("doesn't work").split())
        self.assertIn("will not", clean_text("won't start"))

    def test_stop_words_removed(self):
        self.assertEqual(preprocess_text("the and of is to a"), "")

    def test_domain_spellings_are_normalised(self):
        forms = ["street light", "street-light", "streetlight", "street lamp", "Street Lights", "streetlamps"]
        self.assertEqual({preprocess_text(f) for f in forms}, {"streetlight"})
        self.assertEqual(preprocess_text("pot hole"), preprocess_text("pot-holes"))
        self.assertEqual(preprocess_text("man hole"), preprocess_text("manhole"))

    def test_empty_and_non_latin_input(self):
        for value in ("", "   ", None, "!!! ??? 123", "ರಸ್ತೆಯ ಬೀದಿ ದೀಪ"):
            self.assertEqual(preprocess_text(value), "", value)

    def test_urls_removed(self):
        self.assertEqual(preprocess_text("water leak https://spam.example/x www.spam.example"), "water leak")

    def test_deterministic(self):
        text = "Garbage has not been collected for a week."
        self.assertEqual(preprocess_text(text), preprocess_text(text))

    def test_alignment_keeps_original_words(self):
        self.assertEqual(analyse("Water pipes are leaking"),
                         [("water", "water"), ("pipe", "pipes"), ("leak", "leaking")])
