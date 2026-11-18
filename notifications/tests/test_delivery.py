import json
import urllib.error
from unittest import mock
from urllib.parse import parse_qs

from django.conf import settings
from django.core import mail
from django.test import TestCase, override_settings

from accounts.models import Role
from accounts.tests.helpers import make_user
from complaints.services import assign_worker
from complaints.tests.workflow_helpers import WorkflowTestCase
from notifications import delivery
from notifications.models import Notification
from notifications.services import notify

EMAIL_ON = dict(NOTIFY_EMAIL_ENABLED=True, NOTIFY_WHATSAPP_ENABLED=False, NOTIFY_ASYNC=False, SITE_URL="https://city.example")
TWILIO = dict(NOTIFY_EMAIL_ENABLED=False, NOTIFY_WHATSAPP_ENABLED=True, NOTIFY_ASYNC=False, WHATSAPP_PROVIDER="twilio",
              TWILIO_ACCOUNT_SID="ACtest", TWILIO_AUTH_TOKEN="secret-token", TWILIO_WHATSAPP_FROM="+14155238886", SITE_URL="https://city.example")
META = dict(NOTIFY_EMAIL_ENABLED=False, NOTIFY_WHATSAPP_ENABLED=True, NOTIFY_ASYNC=False, WHATSAPP_PROVIDER="meta",
            META_WHATSAPP_TOKEN="meta-secret", META_WHATSAPP_PHONE_ID="12345", SITE_URL="https://city.example")


class FakeResponse:
    def __init__(self, status=201): self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): return False


class Base(TestCase):
    def setUp(self):
        self.user = make_user("c@example.com", Role.CITIZEN, phone="9876543210", full_name="Asha Rao")

    def send(self, user=None, message="Complaint RL-000001 was submitted successfully.", link="/complaints/1/"):
        with self.captureOnCommitCallbacks(execute=True):
            notify(user or self.user, message, link=link, kind="SUBMITTED")


@override_settings(**EMAIL_ON)
class EmailTests(Base):
    def test_notification_is_also_emailed_with_a_full_link(self):
        self.send()
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertEqual(m.reply_to, [settings.DEFAULT_REPLY_TO_EMAIL])
        self.assertEqual(m.to, ["c@example.com"])
        self.assertIn("RL-000001 was submitted successfully", m.subject)
        tracking_url = "https://city.example/complaints/1/"
        self.assertIn(tracking_url, m.body)
        self.assertEqual(len(m.alternatives), 1)
        self.assertIn(f'href="{tracking_url}"', m.alternatives[0][0])
        self.assertIn("Track this complaint", m.alternatives[0][0])
        self.assertEqual(Notification.objects.filter(recipient=self.user).count(), 1)     # the in-app one still exists

    def test_nothing_is_sent_before_the_transaction_commits(self):
        notify(self.user, "Hello", link="/x/")
        self.assertEqual(len(mail.outbox), 0)

    def test_unverified_inactive_and_excluded_roles_get_no_email(self):
        unverified = make_user("u@example.com", Role.CITIZEN, email_verified=False)
        self.send(unverified)
        self.assertEqual(len(mail.outbox), 0)
        gone = make_user("g@example.com", Role.CITIZEN, is_active=False)
        self.send(gone)
        self.assertEqual(len(mail.outbox), 0)
        with override_settings(NOTIFY_EXTERNAL_ROLES=["CITIZEN"]):
            self.send(make_user("o@example.com", Role.ADMIN))
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(NOTIFY_EMAIL_ENABLED=False)
    def test_can_be_switched_off(self):
        self.send()
        self.assertEqual(len(mail.outbox), 0)

    def test_links_are_never_arbitrary_addresses(self):
        self.send(link="https://evil.example/phish")
        self.assertNotIn("evil.example", mail.outbox[0].body)
        self.send(link="//evil.example")
        self.assertNotIn("evil.example", mail.outbox[1].body)

    def test_a_broken_mail_server_does_not_break_the_caller(self):
        with mock.patch("notifications.delivery.send_routelync_email", side_effect=OSError("boom")):
            self.send()                                   # must not raise
        self.assertEqual(Notification.objects.filter(recipient=self.user).count(), 1)


@override_settings(**TWILIO)
class TwilioTests(Base):
    def test_whatsapp_message_is_posted_to_twilio_with_the_international_number(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            self.send()
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.twilio.com/2010-04-01/Accounts/ACtest/Messages.json")
        body = parse_qs(request.data.decode())
        self.assertEqual(body["To"], ["whatsapp:+919876543210"])
        self.assertEqual(body["From"], ["whatsapp:+14155238886"])
        self.assertIn("RL-000001", body["Body"][0])
        self.assertIn("https://city.example/complaints/1/", body["Body"][0])
        self.assertTrue(request.get_header("Authorization").startswith("Basic "))
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 8)

    def test_no_phone_means_no_whatsapp(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            self.send(make_user("n@example.com", Role.CITIZEN, phone=""))
        urlopen.assert_not_called()

    def test_provider_error_is_logged_without_secrets_or_numbers_and_does_not_raise(self):
        err = urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=err), self.assertLogs("routelync", "ERROR") as logs:
            self.send()
        text = " ".join(logs.output)
        self.assertIn("HTTP 401", text)
        for secret in ("secret-token", "9876543210", "ACtest", "RL-000001"):
            self.assertNotIn(secret, text)

    def test_incomplete_settings_are_reported_clearly(self):
        with override_settings(TWILIO_AUTH_TOKEN=""), self.assertLogs("routelync", "ERROR") as logs:
            self.send()
        self.assertIn("provider settings are incomplete", " ".join(logs.output))

    @override_settings(NOTIFY_EMAIL_ENABLED=True)
    def test_one_channel_failing_does_not_stop_the_other(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("down")), self.assertLogs("routelync", "ERROR"):
            self.send()
        self.assertEqual(len(mail.outbox), 1)


@override_settings(**META)
class MetaTests(Base):
    def sent_json(self, urlopen):
        request = urlopen.call_args.args[0]
        return request, json.loads(request.data)

    def test_plain_text_message_without_a_template(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(200)) as urlopen:
            self.send()
        request, data = self.sent_json(urlopen)
        self.assertEqual(request.full_url, "https://graph.facebook.com/v20.0/12345/messages")
        self.assertEqual(request.get_header("Authorization"), "Bearer meta-secret")
        self.assertEqual((data["to"], data["type"]), ("919876543210", "text"))
        self.assertIn("RL-000001", data["text"]["body"])

    @override_settings(WHATSAPP_TEMPLATE_NAME="complaint_update")
    def test_template_message_has_one_single_line_variable(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(200)) as urlopen:
            self.send()
        _, data = self.sent_json(urlopen)
        self.assertEqual(data["type"], "template")
        self.assertEqual(data["template"]["name"], "complaint_update")
        param = data["template"]["components"][0]["parameters"][0]["text"]
        self.assertNotIn("\n", param)
        self.assertIn("RL-000001", param)


class NumberTests(TestCase):
    def test_numbers(self):
        self.assertEqual(delivery.whatsapp_number("9876543210"), "919876543210")
        self.assertEqual(delivery.whatsapp_number("+91 98765 43210"), "919876543210")
        self.assertEqual(delivery.whatsapp_number(""), "")
        self.assertEqual(delivery.whatsapp_number("12345"), "")


@override_settings(**EMAIL_ON)
class RealJourneyTests(WorkflowTestCase):
    """The citizen's actual complaint events produce real emails, with the same plain wording as in the app."""

    def test_completion_and_resolution_are_emailed_as_separate_states(self):
        from complaints.services import complete_work, review_resolution, start_work
        from complaints.tests.helpers import make_upload

        with self.captureOnCommitCallbacks(execute=True):
            assign_worker(self.complaint, self.worker, actor=self.officer)
        self.assertTrue(any(self.citizen.email in message.to for message in mail.outbox))

        with self.captureOnCommitCallbacks(execute=True):
            start_work(self.complaint, actor=self.worker)
            complete_work(self.complaint, actor=self.worker, remarks="Work completed.", photo=make_upload())
        completion_email = next(
            message for message in mail.outbox
            if self.citizen.email in message.to and "waiting for department verification" in message.body
        )
        self.assertIn("Track this complaint:", completion_email.body)
        self.assertNotIn("has been resolved", completion_email.body)

        with self.captureOnCommitCallbacks(execute=True):
            review_resolution(self.complaint, actor=self.officer, approve=True)
        self.assertTrue(any(
            self.citizen.email in message.to and "has been resolved" in message.body
            for message in mail.outbox
        ))

    def test_citizen_is_emailed_when_a_worker_is_assigned_and_staff_are_emailed_too(self):
        with self.captureOnCommitCallbacks(execute=True):
            assign_worker(self.complaint, self.worker, actor=self.officer)
        recipients = {m.to[0] for m in mail.outbox}
        self.assertIn(self.citizen.email, recipients)
        self.assertIn(self.worker.email, recipients)
        citizen_mail = next(m for m in mail.outbox if m.to[0] == self.citizen.email)
        for internal in ("priority", "confidence", "model", "scalat", "SLA"):
            self.assertNotIn(internal, citizen_mail.subject + citizen_mail.body)
