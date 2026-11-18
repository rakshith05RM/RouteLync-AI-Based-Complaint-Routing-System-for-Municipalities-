from django.core.management.base import BaseCommand, CommandError

from ml_engine.exceptions import MLEngineError
from ml_engine.predict import predict


class Command(BaseCommand):
    help = "Classify one complaint text with the active model (useful for demos and viva)."

    def add_arguments(self, parser):
        parser.add_argument("text")

    def handle(self, *args, **opts):
        try:
            p = predict(opts["text"])
        except MLEngineError as exc:
            raise CommandError(str(exc))
        out = self.stdout.write
        out(f"Cleaned text : {p.cleaned_text or '(empty)'}")
        out(f"Model        : v{p.model_version}, threshold {p.threshold}")
        for code, prob in p.probabilities.items():
            out(f"  {code:<14} {prob:.3f}")
        out(f"Prediction   : {p.department_code} (confidence {p.confidence:.3f})")
        out("Decision     : " + (f"NEEDS VERIFICATION ({p.reason})" if p.needs_verification else "auto-route"))
        if p.top_terms:
            out("Influential terms (vs next most likely department): " + ", ".join(f"{t['term']} ({t['score']})" for t in p.top_terms))
