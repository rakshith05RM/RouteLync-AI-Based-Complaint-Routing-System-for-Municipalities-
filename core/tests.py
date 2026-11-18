from django.test import TestCase
from django.urls import reverse


class CoreViewTests(TestCase):
    def test_home_page_renders_with_brand(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "RouteLync")
        self.assertContains(response, "Civic issue reported")
        self.assertContains(response, "Every report has a clear next step.")
        self.assertNotContains(response, "Streetlight outage")

    def test_unknown_url_uses_friendly_404(self):
        response = self.client.get("/this-page-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page not found", status_code=404)
        self.assertNotContains(response, "Traceback", status_code=404)


class StaticReferenceTests(TestCase):
    def test_every_static_file_used_in_a_template_exists(self):
        """Guards against typos and renames that would silently leave a page without its CSS or JS."""
        import re
        from pathlib import Path

        from django.conf import settings

        missing = []
        for template in Path(settings.BASE_DIR, "templates").rglob("*.html"):
            for ref in re.findall(r"\{% static '([^']+)' %\}", template.read_text()):
                if not Path(settings.BASE_DIR, "static", ref).exists():
                    missing.append((template.name, ref))
        self.assertEqual(missing, [])

from core.tests_security import *  # noqa: E402,F401,F403  (security checklist tests)
from core.tests_geo import *  # noqa: E402,F401,F403
