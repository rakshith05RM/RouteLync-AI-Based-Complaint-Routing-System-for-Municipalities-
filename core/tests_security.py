"""Security checklist expressed as tests."""
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import URLResolver, get_resolver, reverse

from accounts.models import Role, User
from accounts.tests.helpers import PASSWORD, make_user
from audit.models import AuditLog


def all_named_urls():
    names = set()

    def walk(patterns, namespaces):
        for p in patterns:
            if isinstance(p, URLResolver):
                walk(p.url_patterns, namespaces + ([p.namespace] if p.namespace else []))
            elif p.name:
                names.add(":".join(namespaces + [p.name]))
    walk(get_resolver().url_patterns, [])
    return {n for n in names if not n.startswith("admin:")}


# Pages anyone may open or submit (before signing in).
PUBLIC = {"core:home", "accounts:register", "accounts:login", "accounts:logout", "accounts:password_reset",
          "accounts:verify_email", "accounts:resend_code",
          "accounts:password_reset_done", "accounts:password_reset_confirm", "accounts:password_reset_complete"}

# Everything else must refuse an anonymous visitor. Value = URL arguments used for the check.
PROTECTED = {
    "accounts:dashboard": [], "accounts:profile": [], "accounts:password_change": [],
    "complaints:new": [], "complaints:my_complaints": [], "complaints:detail": [1], "complaints:confirm": [1],
    "complaints:reopen": [1], "complaints:feedback": [1], "complaints:image": [1, 1], "complaints:resolution_photo": [1], "complaints:attempt_discard": [1], "geo:search": [], "geo:reverse": [],
    "officer:dashboard": [], "officer:locations": [], "officer:map": [], "officer:detail": [1], "officer:assign": [1],
    "officer:unassign": [1], "officer:remark": [1], "officer:priority": [1], "officer:escalate": [1], "officer:reject": [1],
    "officer:review": [1], "officer:duplicate_review": [1, 1],
    "worker:dashboard": [], "worker:detail": [1], "worker:start": [1], "worker:remark": [1], "worker:complete": [1],
    "notifications:list": [], "notifications:open": [1], "notifications:read_all": [],
    "adminpanel:dashboard": [], "adminpanel:complaints": [], "adminpanel:complaint": [1], "adminpanel:route": [1],
    "adminpanel:reject": [1], "adminpanel:duplicate_review": [1, 1], "adminpanel:queue": [], "adminpanel:users": [],
    "adminpanel:user_new": [], "adminpanel:user_action": [1, "deactivate"], "adminpanel:departments": [],
    "adminpanel:department_new": [], "adminpanel:department_toggle": [1, "off"], "adminpanel:sla": [],
    "adminpanel:ai": [], "adminpanel:train": [], "adminpanel:activate": [1], "adminpanel:threshold": [1],
    "adminpanel:trace": [], "adminpanel:dataset": [], "adminpanel:dataset_upload": [], "adminpanel:dataset_add": [],
    "adminpanel:dataset_export": [], "adminpanel:audit": [],
}


class AccessMatrixTests(TestCase):
    def test_no_url_has_been_added_without_an_access_decision(self):
        decided = PUBLIC | set(PROTECTED)
        self.assertEqual(all_named_urls() - decided, set(), "A new URL needs an access-control decision: add it to PUBLIC or PROTECTED.")
        self.assertEqual(decided - all_named_urls(), set(), "A listed URL no longer exists.")

    def test_every_protected_url_turns_an_anonymous_visitor_away(self):
        for name, args in PROTECTED.items():
            url = reverse(name, args=args)
            for method in ("get", "post"):
                response = getattr(Client(), method)(url)
                self.assertEqual(response.status_code, 302, f"{method.upper()} {url} ({name}) let an anonymous visitor through")
                self.assertTrue(response["Location"].startswith(reverse("accounts:login")), f"{name} did not redirect to login")

    def test_state_changing_endpoints_refuse_get(self):
        users = {"citizen": make_user("c@example.com", Role.CITIZEN), "officer": make_user("o@example.com", Role.OFFICER, department=None) if False else None}
        from accounts.tests.helpers import make_department
        users["officer"] = make_user("o@example.com", Role.OFFICER, department=make_department("ELECTRICITY"))
        users["admin"] = make_user("root@example.com", Role.ADMIN)
        cases = {"complaints:confirm": "citizen", "complaints:reopen": "citizen", "complaints:feedback": "citizen",
                 "officer:assign": "officer", "officer:review": "officer", "officer:duplicate_review": "officer",
                 "adminpanel:train": "admin", "adminpanel:route": "admin", "adminpanel:department_new": "admin",
                 "notifications:read_all": "admin"}
        for name, who in cases.items():
            client = Client()
            client.force_login(users[who])
            self.assertEqual(client.get(reverse(name, args=PROTECTED[name])).status_code, 405, name)


class HeaderTests(TestCase):
    def test_security_headers_on_normal_pages(self):
        response = self.client.get(reverse("core:home"))
        csp = response["Content-Security-Policy"]
        for directive in ("default-src 'self'", "object-src 'none'", "frame-ancestors 'none'", "base-uri 'self'", "form-action 'self'"):
            self.assertIn(directive, csp)
        self.assertIn("https://server.arcgisonline.com", csp)
        self.assertNotIn("'unsafe-eval'", csp)
        self.assertNotRegex(csp.split("script-src")[1].split(";")[0], "unsafe-inline")
        self.assertIn("geolocation=(self)", response["Permissions-Policy"])
        self.assertEqual(response["Referrer-Policy"], "same-origin")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["Cross-Origin-Opener-Policy"], "same-origin")

    def test_templates_use_no_inline_scripts_or_event_handlers(self):
        offenders = []
        for path in Path(settings.BASE_DIR, "templates").rglob("*.html"):
            text = path.read_text()
            if re.search(r"\son[a-z]+\s*=\s*[\"']", text):
                offenders.append((path.name, "inline event handler"))
            for tag in re.findall(r"<script\b[^>]*>", text):
                if "src=" not in tag and "application/json" not in tag:
                    offenders.append((path.name, "inline script"))
        self.assertEqual(offenders, [])


class ThrottleTests(TestCase):
    def setUp(self):
        cache.clear()

    @override_settings(REGISTER_LIMIT_PER_IP=2)
    def test_registration_is_limited_per_network(self):
        def register(n):
            return self.client.post(reverse("accounts:register"), {
                "full_name": "Asha Rao", "email": f"user{n}@example.com", "phone": "9876543210", "password1": PASSWORD, "password2": PASSWORD})
        for n in (1, 2):
            self.client.logout()
            self.assertEqual(register(n).status_code, 302)
        self.client.logout()
        response = register(3)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Too many accounts")
        self.assertFalse(User.objects.filter(email="user3@example.com").exists())

    @override_settings(RESET_LIMIT_PER_EMAIL=2)
    def test_password_reset_emails_are_limited_without_revealing_anything(self):
        make_user("reset@example.com")
        url = reverse("accounts:password_reset")
        responses = [self.client.post(url, {"email": "reset@example.com"}) for _ in range(4)]
        self.assertEqual({r.status_code for r in responses}, {302})
        self.assertEqual({r["Location"] for r in responses}, {reverse("accounts:password_reset_done")})   # identical for everyone
        self.assertEqual(len(mail.outbox), 2)
        self.client.post(url, {"email": "nobody@example.com"})
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(RESET_LIMIT_PER_IP=1)
    def test_password_reset_is_limited_per_network_too(self):
        make_user("a@example.com")
        make_user("b@example.com")
        url = reverse("accounts:password_reset")
        self.client.post(url, {"email": "a@example.com"})
        self.client.post(url, {"email": "b@example.com"})
        self.assertEqual(len(mail.outbox), 1)


class AuthAuditTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user("citizen@example.com", full_name="Asha Rao")

    def test_sign_in_sign_out_and_failures_are_recorded_without_passwords(self):
        self.client.post(reverse("accounts:login"), {"username": "citizen@example.com", "password": "WrongPassword!1"})
        self.client.post(reverse("accounts:login"), {"username": "citizen@example.com", "password": PASSWORD})
        self.client.post(reverse("accounts:logout"))
        actions = list(AuditLog.objects.order_by("id").values_list("action", flat=True))
        self.assertEqual(actions, ["LOGIN_FAILED", "LOGIN", "LOGOUT"])
        failed = AuditLog.objects.get(action="LOGIN_FAILED")
        self.assertIn("citizen@example.com", failed.summary)
        self.assertEqual(failed.details["ip"], "127.0.0.1")
        everything = " ".join(f"{e.summary} {e.details}" for e in AuditLog.objects.all())
        self.assertNotIn("WrongPassword", everything)
        self.assertNotIn(PASSWORD, everything)


class ErrorPageTests(TestCase):
    def test_csrf_failure_shows_a_friendly_page(self):
        strict = Client(enforce_csrf_checks=True)
        response = strict.post(reverse("accounts:login"), {"username": "a@example.com", "password": "x"})
        self.assertContains(response, "Your session expired", status_code=403)
        self.assertNotContains(response, "CSRF", status_code=403)

    def test_server_errors_show_a_friendly_page_and_no_traceback(self):
        from unittest import mock
        client = Client(raise_request_exception=False)
        client.force_login(make_user("c@example.com"))
        with mock.patch("complaints.views.citizen.MyComplaintsView.get_queryset", side_effect=RuntimeError("secret internal detail")):
            response = client.get(reverse("complaints:my_complaints"))
        self.assertContains(response, "Something went wrong", status_code=500)
        self.assertNotContains(response, "secret internal detail", status_code=500)
        self.assertNotContains(response, "Traceback", status_code=500)

    def test_bad_request_page(self):
        from django.test import RequestFactory
        from core.views import bad_request
        response = bad_request(RequestFactory().get("/"))
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"could not understand", response.content)


class DeploymentChecklistTests(SimpleTestCase):
    def test_django_deploy_check_is_clean_with_production_settings(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("DJANGO_")}
        env.update(DJANGO_DEBUG="False", DJANGO_SECRET_KEY=secrets.token_urlsafe(64), DJANGO_ALLOWED_HOSTS="example.com", DB_ENGINE="sqlite",
                   EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="smtp.example.com", EMAIL_HOST_USER="user", EMAIL_HOST_PASSWORD="not-a-real-password")
        result = subprocess.run([sys.executable, "manage.py", "check", "--deploy"], cwd=settings.BASE_DIR, env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no issues", result.stdout + result.stderr, result.stdout + result.stderr)

    def test_the_deploy_check_warns_when_real_email_is_not_configured(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "EMAIL_"))}
        env.update(DJANGO_DEBUG="False", DJANGO_SECRET_KEY=secrets.token_urlsafe(64), DJANGO_ALLOWED_HOSTS="example.com", DB_ENGINE="sqlite")
        result = subprocess.run([sys.executable, "manage.py", "check", "--deploy"], cwd=settings.BASE_DIR, env=env, capture_output=True, text=True, timeout=120)
        self.assertIn("routelync.W001", result.stdout + result.stderr)

    def test_the_app_refuses_to_start_in_production_without_a_secret_key(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("DJANGO_")}
        env.update(DJANGO_DEBUG="False", DB_ENGINE="sqlite")
        result = subprocess.run([sys.executable, "manage.py", "check"], cwd=settings.BASE_DIR, env=env, capture_output=True, text=True, timeout=120)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", result.stderr)
