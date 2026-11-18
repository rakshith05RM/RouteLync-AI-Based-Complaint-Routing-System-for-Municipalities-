"""
Transparent, rule-based priority. No machine learning is used here, so every decision can be
explained by pointing at ONE rule. The highest-severity matching rule wins; if nothing matches the
priority is MEDIUM.

CRITICAL  danger to life: live/exposed/hanging electric wire, electric shock, sparks or fire,
          exploded transformer, fallen or leaning pole, collapse or injury, gas leak, a person trapped / rescue needed
HIGH      public-health or safety risk: open/missing manhole, burst water main, sewage, animal bites or
          attacks, disease outbreaks (dengue, cholera ...),
          contaminated water or illness, accidents/skidding, an essential service (water, power)
          out for two or more days, explicitly dangerous/hazardous
LOW       cosmetic or minor: faded markings, paint, replacement requests, "minor"
MEDIUM    everything else (the default)

Known limitations (state them in the report): keyword rules can be fooled by unusual wording, do not
understand negation ("no sparks"), and can be gamed by a citizen who types alarming words. Officers
can change a priority later (Phase 8), and every change will be audited.
"""
import re
from dataclasses import dataclass

from departments.models import Priority

_RANK = {Priority.CRITICAL: 4, Priority.HIGH: 3, Priority.MEDIUM: 2, Priority.LOW: 1}


@dataclass(frozen=True)
class Rule:
    code: str
    priority: str
    pattern: re.Pattern
    explanation: str


def _rx(*patterns: str) -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


RULES = [
    Rule("LIVE_WIRE", Priority.CRITICAL,
         _rx(r"\b(live|exposed|bare|snapped|dangling|hanging)\b[^.]{0,40}\b(wires?|cables?|power lines?)\b",
             r"\b(wires?|cables?|power lines?)\b[^.]{0,40}\b(hanging|dangling|snapped|exposed|lying open|fallen|touching)\b"),
         "Live or hanging electric wire"),
    Rule("ELECTRIC_SHOCK", Priority.CRITICAL,
         _rx(r"\belectric(?:al)?\s+shocks?\b", r"\belectrocut\w*", r"\bget(?:ting)?\s+shocks?\b",
             r"\bgiving\s+(?:\w+\s+)?shocks?\b"),
         "Electric shock reported"),
    Rule("SPARKS_OR_FIRE", Priority.CRITICAL,
         _rx(r"\bsparks?\b", r"\bsparking\b", r"\bfire\b", r"\bflames?\b", r"\b(?:burning|burnt)\s+smell\b",
             r"\bexplo(?:de|ded|sion)\b"),
         "Sparks, fire or explosion"),
    Rule("TRANSFORMER_FAILURE", Priority.CRITICAL,
         _rx(r"\btransformer\b[^.]{0,30}\b(?:blast|blown|burst|burnt|exploded)\b"),
         "Transformer failure"),
    Rule("FALLEN_POLE", Priority.CRITICAL,
         _rx(r"\b(?:pole|poles)\b[^.]{0,30}\b(?:fell|fall|fallen|falling|leaning|tilted|collapsed)\b",
             r"\b(?:fallen|leaning)\s+(?:electric\s+)?poles?\b"),
         "Fallen or leaning pole"),
    Rule("COLLAPSE_OR_INJURY", Priority.CRITICAL,
         _rx(r"\bcollaps(?:e|ed|ing)\b", r"\bcaved in\b", r"\bsinkhole\b", r"\binjur(?:y|ed|ies)\b",
             r"\bdied\b", r"\bdead body\b"),
         "Collapse or injury"),
    Rule("GAS_LEAK", Priority.CRITICAL, _rx(r"\bgas leak\w*\b"), "Gas leak"),

    Rule("PERSON_TRAPPED", Priority.CRITICAL,
         _rx(r"\btrapped\b", r"\bstuck (?:in|inside) the (?:lift|elevator)\b", r"\brescue (?:is )?(?:needed|required)\b", r"\bneeds? (?:to be )?rescue\w*\b"),
         "Person trapped or rescue needed"),
    Rule("OPEN_MANHOLE", Priority.HIGH,
         _rx(r"\b(?:manhole|drain|sewer)\b[^.]{0,30}\b(?:open|missing|uncovered)\b",
             r"\bmissing\b[^.]{0,20}\b(?:manhole|drain)\b", r"\bmanhole cover\b[^.]{0,15}\b(?:missing|broken)\b"),
         "Open or missing manhole/drain cover"),
    Rule("BURST_PIPE", Priority.HIGH,
         _rx(r"\b(?:pipe|pipeline|main)\b[^.]{0,30}\b(?:burst|gushing|flooding)\b",
             r"\bburst(?:ing)?\b[^.]{0,20}\b(?:pipe|pipeline|main)\b", r"\bwater is gushing\b"),
         "Burst pipe or water main"),
    Rule("SEWAGE", Priority.HIGH,
         _rx(r"\bsewage\b", r"\bsewer\b[^.]{0,30}\b(?:overflow\w*|chok\w*|burst)\b",
             r"\bseptic tank\b[^.]{0,30}\boverflow\w*"),
         "Sewage: public-health risk"),
    Rule("HEALTH_RISK_WATER", Priority.HIGH,
         _rx(r"\b(?:contaminated|worms?|insects?)\b[^.]{0,40}\bwater\b", r"\bwater\b[^.]{0,40}\b(?:contaminated|worms?|insects?)\b",
             r"\b(?:fell|fallen|got|made)\s+(?:sick|ill)\b", r"\bdiarr?hoea\b", r"\bcholera\b", r"\btyphoid\b"),
         "Contaminated water or illness"),
    Rule("ANIMAL_ATTACK", Priority.HIGH,
         _rx(r"\bbitten\b", r"\bbites?\b", r"\bbiting\b", r"\bbit (?:my|our|a|the|him|her|me|them)\b", r"\battack(?:s|ed|ing)?\b", r"\brabid\b", r"\brabies\b"),
         "Animal attack or rabies risk"),
    Rule("DISEASE_OUTBREAK", Priority.HIGH,
         _rx(r"\bdengue\b", r"\bmalaria\b", r"\bcholera\b", r"\btyphoid\b", r"\boutbreak\b", r"\bepidemic\b", r"\bfood poisoning\b"),
         "Disease outbreak"),
    Rule("ACCIDENT_RISK", Priority.HIGH,
         _rx(r"\baccidents?\b", r"\bskidd?ing\b", r"\bfell into\b", r"\bgot stuck\b"),
         "Accidents or injury risk"),
    Rule("STATED_DANGER", Priority.HIGH,
         _rx(r"\bdangerous(?:ly)?\b", r"\bdanger\b", r"\bhazard\w*\b", r"\blife[- ]threatening\b"),
         "Citizen describes a danger"),
]

LOW_RULE = Rule("MINOR_ISSUE", Priority.LOW,
                _rx(r"\bfaded\b", r"\bfading\b", r"\bworn off\b", r"\bpaint\b", r"\bmarkings?\b", r"\breplace\w*\b",
                    r"\bminor\b", r"\bsmall crack\b", r"\bsuggest\w*\b", r"\brequest\b"),
                "Minor or cosmetic issue")

OUTAGE = _rx(r"\bno\s+(?:drinking\s+)?(?:water|power|electricity|current)\b",
             r"\b(?:power|electricity|water supply)\s+(?:cut|outage|failure)s?\b",
             r"\bwithout\s+(?:water|power|electricity)\b",
             r"\b(?:taps?|supply)\s+(?:is\s+|are\s+|has\s+|have\s+)?(?:dry|stopped)\b",
             r"\bwater\b[^.]{0,20}\bnot\s+(?:coming|available|reaching|supplied)\b",
             r"\b(?:lost|lose)\s+(?:power|electricity|current)\b")

_NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                 "eight": 8, "nine": 9, "ten": 10, "few": 3, "several": 3, "couple of": 2}
_DURATION = re.compile(r"\b(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|few|several|couple of)\s+"
                       r"(day|days|week|weeks|month|months)\b", re.IGNORECASE)
_UNIT_DAYS = {"day": 1, "days": 1, "week": 7, "weeks": 7, "month": 30, "months": 30}


def mentioned_days(text: str) -> int:
    """Longest duration the citizen mentions, in days (0 if none). 'yesterday'/'last night' = 1."""
    longest = 1 if re.search(r"\b(yesterday|last night)\b", text, re.IGNORECASE) else 0
    for unit in re.findall(r"\b(?:past|last)\s+(week|month)\b", text, re.IGNORECASE):
        longest = max(longest, _UNIT_DAYS[unit.lower()])
    for number, unit in _DURATION.findall(text):
        count = int(number) if number.isdigit() else _NUMBER_WORDS[number.lower()]
        longest = max(longest, count * _UNIT_DAYS[unit.lower()])
    return longest


@dataclass(frozen=True)
class PriorityDecision:
    priority: str
    rule_code: str
    reason: str


def decide_priority(text: str) -> PriorityDecision:
    text = " ".join((text or "").split())
    matched = [rule for rule in RULES if rule.pattern.search(text)]
    if OUTAGE.search(text) and mentioned_days(text) >= 2:
        matched.append(Rule("PROLONGED_OUTAGE", Priority.HIGH, OUTAGE, "Essential service out for 2+ days"))
    if matched:
        best = max(matched, key=lambda r: _RANK[r.priority])
        return PriorityDecision(best.priority, best.code, best.explanation)
    if LOW_RULE.pattern.search(text):
        return PriorityDecision(LOW_RULE.priority, LOW_RULE.code, LOW_RULE.explanation)
    return PriorityDecision(Priority.MEDIUM, "DEFAULT", "No special rule matched")
