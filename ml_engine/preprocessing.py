"""
NLP preprocessing pipeline (one function per documented step).

    raw complaint
      -> 1. lower-case and unify apostrophes
      -> 2. remove URLs
      -> 3. expand contractions            ("isn't" -> "is not", "can't" -> "cannot")
      -> 4. normalise domain spellings     ("street light", "street-lamp" -> "streetlight"; "pot hole" -> "pothole")
      -> 5. remove digits and punctuation
      -> 6. tokenise                       (NLTK RegexpTokenizer; needs no downloaded corpora)
      -> 7. drop 1-letter tokens and stop-words (custom list that KEEPS negations and "off/out/down")
      -> 8. stem                           (NLTK Snowball English stemmer)
      -> cleaned text, e.g. "streetlight not work three day"

Why a custom stop-word list? Standard lists remove "no", "not", "nor", "off" and "out", but
"no water", "not working", "power cut off" and "water not coming out" depend on exactly those
words. Removing them would damage the meaning of the complaint.

Limitations (state in the report): English/Latin script only (other scripts produce empty
output); stemming is rule-based and sometimes produces non-words such as "pothol".
"""
import re
from functools import lru_cache

from nltk.stem import SnowballStemmer
from nltk.tokenize import RegexpTokenizer

_TOKENIZER = RegexpTokenizer(r"[a-z]+")
_STEMMER = SnowballStemmer("english")

# Words deliberately NOT treated as stop-words.
KEEP_WORDS = frozenset({"no", "not", "nor", "never", "none", "nothing", "without", "cannot", "off", "out", "down"})

STOP_WORDS = frozenset("""
a an the and or but if while of at by for with about against between into through during above below
to from in on over under again further then once here there when where why how all any both each few
other some such own same so than too very s t can will just should now i me my myself we our ours
ourselves you your yours he him his she her hers it its they them their theirs what which who whom this
that these those am is are was were be been being have has had having do does did doing would could
shall may might must also please kindly sir madam hello hi dear regards thanks thank sorry
""".split()) - KEEP_WORDS

_URL = re.compile(r"https?://\S+|www\.\S+")
_CONTRACTIONS = [
    (re.compile(r"\bcan't\b"), "cannot"), (re.compile(r"\bwon't\b"), "will not"),
    (re.compile(r"\bain't\b"), "is not"), (re.compile(r"n't\b"), " not"),
    (re.compile(r"'re\b"), " are"), (re.compile(r"'ve\b"), " have"), (re.compile(r"'ll\b"), " will"),
    (re.compile(r"'m\b"), " am"), (re.compile(r"'s\b"), ""),
]
_NORMALISATIONS = [
    (re.compile(r"\bstreet[\s\-]*(?:light|lamp)s?\b"), "streetlight"),
    (re.compile(r"\blamp[\s\-]*posts?\b"), "lamppost"),
    (re.compile(r"\bpot[\s\-]+holes?\b"), "pothole"),
    (re.compile(r"\bman[\s\-]+holes?\b"), "manhole"),
    (re.compile(r"\bfoot[\s\-]+paths?\b"), "footpath"),
    (re.compile(r"\bdust[\s\-]+bins?\b"), "dustbin"),
    (re.compile(r"\bbore[\s\-]+wells?\b"), "borewell"),
    (re.compile(r"\bwater[\s\-]*logging\b"), "waterlogging"),
    (re.compile(r"\bspeed[\s\-]+(?:breakers?|humps?|bumps?)\b"), "speedbreaker"),
]
_ORDINAL = re.compile(r"\b\d+(?:st|nd|rd|th)\b")   # "4th", "2nd" carry no department signal
_NON_LETTERS = re.compile(r"[^a-z]+")


def clean_text(text: str) -> str:
    """Steps 1-5: lower-case, remove URLs, expand contractions, normalise, strip digits/punctuation."""
    text = (text or "").lower().replace("\u2019", "'").replace("\u2018", "'")
    text = _URL.sub(" ", text)
    for pattern, replacement in _CONTRACTIONS:
        text = pattern.sub(replacement, text)
    for pattern, replacement in _NORMALISATIONS:
        text = pattern.sub(replacement, text)
    text = _ORDINAL.sub(" ", text)
    return _NON_LETTERS.sub(" ", text).strip()


def tokenize(clean: str) -> list[str]:
    """Step 6."""
    return _TOKENIZER.tokenize(clean)


@lru_cache(maxsize=50_000)
def _stem(word: str) -> str:
    return _STEMMER.stem(word)


def analyse(text: str) -> list[tuple[str, str]]:
    """Steps 1-8, keeping each stem aligned with the word it came from (used by explainability)."""
    return [(_stem(w), w) for w in tokenize(clean_text(text)) if len(w) > 1 and w not in STOP_WORDS]


def preprocess_text(text: str) -> str:
    """The full pipeline. Used as the TfidfVectorizer preprocessor so training and prediction
    always apply exactly the same steps (the saved model carries them)."""
    return " ".join(stem for stem, _ in analyse(text))


def whitespace_tokens(cleaned: str) -> list[str]:
    """Tokenizer handed to TfidfVectorizer (the text is already tokenised and cleaned)."""
    return cleaned.split()
