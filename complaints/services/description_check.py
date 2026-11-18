"""
Is this text a complaint RouteLync can act on?  Runs on the server before anything is saved or routed.

Outcomes (Verdict):
  OK            describes an identifiable problem in a supported area
  REVIEW        cannot be judged by rules or model (for example a local language) but is not obviously junk:
                accepted, and the routing step sends it to a person instead of guessing a department
  NONSENSE      gibberish, filler, repeated words, placeholders, numbers/symbols only, links, advertising
  UNCLEAR       real words, but no identifiable municipal problem (too vague, or off-topic text)
  UNSUPPORTED   a municipal-sounding matter outside the supported departments
  TOO_SHORT     not enough words to understand

A word count is only ONE signal: a short text such as "Large pothole near the school gate" is accepted, while a long
essay is not. The department itself is decided later by the existing classifier; a confident classifier is never
treated as proof that the text is a valid complaint.
"""
import re
from dataclasses import dataclass
from enum import Enum

from django.core.exceptions import ValidationError

from ml_engine.model_manager import get_active_model
from ml_engine.preprocessing import analyse, _stem

from ..municipal_terms import OUT_OF_SCOPE, PROBLEM, SPAM, STRONG, WEAK
from ..validators import _gibberish_token, normalize_text, validate_description


class Verdict(str, Enum):
    OK = "OK"
    REVIEW = "REVIEW"
    NONSENSE = "NONSENSE"
    UNCLEAR = "UNCLEAR"
    UNSUPPORTED = "UNSUPPORTED"
    TOO_SHORT = "TOO_SHORT"


MESSAGES = {
    Verdict.NONSENSE: "Your complaint could not be submitted because the description does not explain a municipal issue. Please describe the problem clearly.",
    Verdict.UNCLEAR: "We could not identify the issue from your description. Please explain what happened and where it occurred.",
    Verdict.UNSUPPORTED: "This issue is outside the currently supported complaint categories. Please review the supported categories or contact the appropriate municipal authority.",
    Verdict.TOO_SHORT: "Your description is too short to understand the problem. Please explain what happened and where it occurred.",
}
LABELS = {Verdict.NONSENSE: "Not a municipal issue", Verdict.UNCLEAR: "Description not clear",
          Verdict.UNSUPPORTED: "Outside supported categories", Verdict.TOO_SHORT: "Description too short"}

_STRONG, _WEAK, _PROBLEM = ({_stem(w) for w in words} for words in (STRONG, WEAK, PROBLEM))
_OUT, _SPAM = ({_stem(w) for w in words} for words in (OUT_OF_SCOPE, SPAM))
_NON_LATIN_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
_VALIDATOR_CODES = {"too_short": Verdict.TOO_SHORT, "too_few_words": Verdict.TOO_SHORT}      # everything else from the validators is nonsense


@dataclass(frozen=True)
class DescriptionResult:
    verdict: Verdict
    message: str = ""
    detail: str = ""

    @property
    def accepted(self) -> bool:
        return self.verdict in (Verdict.OK, Verdict.REVIEW)

    @property
    def label(self) -> str:
        return LABELS.get(self.verdict, "")


def _is_mostly_non_latin(text: str) -> bool:
    letters = _NON_LATIN_LETTER.findall(text)
    return bool(letters) and sum(not ch.isascii() for ch in letters) / len(letters) > 0.5


def _classifier_recognises(text: str, words: set) -> bool:
    """A second opinion for texts the vocabulary does not recognise, so a valid complaint is not refused only because it uses
    an unusual word. The trained classifier must know most of the words, enough of them, and be reasonably sure. This can only
    ACCEPT text that already passed the format checks and is not spam or out of scope; it never overrides those refusals.
    Without an active model this returns False (the vocabulary alone decides)."""
    try:
        _, pipeline = get_active_model()
        vocabulary = pipeline.named_steps["tfidf"].vocabulary_
        known = [w for w in words if w in vocabulary]
        if len(known) < 4 or len(known) / max(len(words), 1) < 0.6:
            return False
        top = float(pipeline.predict_proba([text])[0].max())
    except Exception:  # noqa: BLE001 - no model, or a damaged one: fall back to the vocabulary
        return False
    return top >= 0.5 and (len(known) >= 5 or top >= 0.85)


def check_description(description: str) -> DescriptionResult:
    """Judge the DESCRIPTION on its own: a good title cannot rescue a description that explains nothing."""
    text = normalize_text(description)
    try:
        validate_description(text)                       # whitespace, length, links, filler, gibberish, repeated words
    except ValidationError as exc:
        verdict = _VALIDATOR_CODES.get(exc.code, Verdict.NONSENSE)
        if verdict == Verdict.TOO_SHORT and any(_gibberish_token(t) for t in re.findall(r"[^\W\d_]+", text)):
            verdict = Verdict.NONSENSE                   # two keyboard-mash words are nonsense, not just "short"
        message = (f"{exc.messages[0]} Please explain what happened and where it occurred."
                   if verdict == Verdict.TOO_SHORT else MESSAGES[verdict])
        return DescriptionResult(verdict, message, exc.messages[0])

    if _is_mostly_non_latin(text):                      # a local language: rules and classifier are English-only
        return DescriptionResult(Verdict.REVIEW, detail="non-Latin script; a person will route it")

    stems = [stem for stem, _ in analyse(text)]
    words = set(stems)
    strong, weak, problem = words & _STRONG, words & _WEAK, words & _PROBLEM
    spam, out = words & _SPAM, words & _OUT
    if _stem("driving") in words:                       # a driving licence is not a trade licence (the transport office, not the municipality)
        strong, weak = strong - {_stem("licence"), _stem("license")}, weak - {_stem("licence"), _stem("license")}
    n = max(len(stems), 1)

    if len(spam) >= 2 or (spam and not strong):
        return DescriptionResult(Verdict.NONSENSE, MESSAGES[Verdict.NONSENSE], "advertising wording")
    if strong or (weak and problem):
        # a longer text with very few municipal words is an essay or pasted text, not a complaint
        domain_hits = sum(s in _STRONG or s in _WEAK for s in stems)
        if len(stems) >= 25 and domain_hits / n < 0.12:
            return DescriptionResult(Verdict.UNCLEAR, MESSAGES[Verdict.UNCLEAR], "long text with almost no municipal content")
        return DescriptionResult(Verdict.OK)
    if out:
        return DescriptionResult(Verdict.UNSUPPORTED, MESSAGES[Verdict.UNSUPPORTED], "outside the supported departments")
    if _classifier_recognises(text, words):
        return DescriptionResult(Verdict.OK, detail="recognised by the trained classifier")
    if weak:
        return DescriptionResult(Verdict.UNCLEAR, MESSAGES[Verdict.UNCLEAR], "mentions a place or thing but no problem")
    return DescriptionResult(Verdict.NONSENSE, MESSAGES[Verdict.NONSENSE], "no municipal issue identified")
