from django.test import SimpleTestCase

from complaints.services.priority import decide_priority, mentioned_days
from departments.models import Priority as P


class PriorityRuleTests(SimpleTestCase):
    def check(self, text, expected, rule=None):
        decision = decide_priority(text)
        self.assertEqual(decision.priority, expected, f"{text!r} -> {decision}")
        if rule:
            self.assertEqual(decision.rule_code, rule, text)
        self.assertTrue(decision.reason)

    def test_critical_rules(self):
        for text, rule in (
            ("A live electric wire is hanging low near the school", "LIVE_WIRE"),
            ("Power line has snapped and is lying across the lane", "LIVE_WIRE"),
            ("The lamp post is giving electric shocks when touched", "ELECTRIC_SHOCK"),
            ("Sparks are coming from the electric pole", "SPARKS_OR_FIRE"),
            ("There is a burning smell coming from the electric panel", "SPARKS_OR_FIRE"),
            ("The transformer has blown up with a loud noise", "TRANSFORMER_FAILURE"),
            ("The electric pole is leaning and may fall on houses", "FALLEN_POLE"),
            ("The approach road of the bridge has caved in", "COLLAPSE_OR_INJURY"),
            ("There is a gas leak near the kitchen block", "GAS_LEAK"),
        ):
            self.check(text, P.CRITICAL, rule)

    def test_high_rules(self):
        for text, rule in (
            ("The manhole cover is missing on the road", "OPEN_MANHOLE"),
            ("The main water pipe has burst and water is flooding the lane", "BURST_PIPE"),
            ("Sewage water is flowing on the street", "SEWAGE"),
            ("Contaminated drinking water is being supplied to us", "HEALTH_RISK_WATER"),
            ("A pothole filled with water is causing accidents", "ACCIDENT_RISK"),
            ("The old building wall is in a dangerous condition", "STATED_DANGER"),
        ):
            self.check(text, P.HIGH, rule)

    def test_prolonged_outage_needs_two_or_more_days(self):
        self.check("There is no water supply for the last three days", P.HIGH, "PROLONGED_OUTAGE")
        self.check("no power in our lane for more than a week", P.HIGH, "PROLONGED_OUTAGE")
        self.check("There is no water supply since yesterday", P.MEDIUM, "DEFAULT")
        self.check("There is no water supply", P.MEDIUM, "DEFAULT")

    def test_low_rules(self):
        for text in ("The zebra crossing markings have faded", "The paint on the speed hump has worn off",
                     "The bulb on the street pole needs replacement"):
            self.check(text, P.LOW, "MINOR_ISSUE")

    def test_default_is_medium(self):
        for text in ("Garbage has not been collected for a week", "The streetlight near the junction is not working",
                     "The footpath is broken near the market"):
            self.check(text, P.MEDIUM, "DEFAULT")

    def test_highest_severity_wins(self):
        self.check("Faded markings and also sparks coming from the pole", P.CRITICAL)
        self.check("Sewage overflow and the paint is faded", P.HIGH)

    def test_case_insensitive_and_whitespace_tolerant(self):
        self.check("SPARKS   are\ncoming from THE pole", P.CRITICAL)

    def test_word_boundaries_avoid_false_matches(self):
        self.check("The firefly park lights are fine but the road needs sweeping", P.MEDIUM)
        self.check("Please ensure the offices are repaired", P.MEDIUM)

    def test_empty_text(self):
        self.check("", P.MEDIUM, "DEFAULT")

    def test_mentioned_days(self):
        for text, days in (("for three days", 3), ("for more than a week", 7), ("for two weeks now", 14),
                           ("for 10 days", 10), ("since yesterday", 1), ("since last night", 1),
                           ("for several days", 3), ("for the past month", 30), ("hello", 0)):
            self.assertEqual(mentioned_days(text), days, text)


class PriorityRulesForAddedDepartmentsTests(SimpleTestCase):
    def check(self, text, expected, rule):
        decision = decide_priority(text)
        self.assertEqual((decision.priority, decision.rule_code), (expected, rule), text)

    def test_rescue_and_attacks_and_outbreaks(self):
        self.check("A person is trapped in the collapsed wall and rescue is needed", P.CRITICAL, "COLLAPSE_OR_INJURY")        # the older rule also fits
        self.check("Two workers are trapped inside the tank and need rescue", P.CRITICAL, "PERSON_TRAPPED")
        self.check("A man is stuck in the lift of our building and the power is gone", P.CRITICAL, "PERSON_TRAPPED")
        self.check("A stray dog has bitten a child in our lane", P.HIGH, "ANIMAL_ATTACK")
        self.check("Stray dogs are attacking people near the park", P.HIGH, "ANIMAL_ATTACK")
        self.check("Dengue cases are rising in our locality", P.HIGH, "DISEASE_OUTBREAK")
        self.check("There is a cholera outbreak in our colony", P.HIGH, "HEALTH_RISK_WATER")           # the older health rule already covers cholera
        self.check("A malaria outbreak has been reported in the slum", P.HIGH, "DISEASE_OUTBREAK")

    def test_everyday_words_do_not_trigger_them(self):
        for text in ("There is a bit of garbage near the market", "The park gate is locked all day", "The birth certificate has not been issued",
                     "The property tax bill is wrong", "The hoarding blocks the view at the turn"):
            self.assertEqual(decide_priority(text).priority, P.MEDIUM, text)
