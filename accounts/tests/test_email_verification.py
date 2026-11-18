import re
import smtplib
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.conf import settings
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import EmailOTP, Role, User
from accounts.tests.helpers import PASSWORD, make_user
from accounts.tests.test_registration import code_from

REGISTER = reverse("accounts:register")
VERIFY = reverse("accounts:verify_email")
RESEND = reverse("accounts:resend_code")
LOGIN = reverse("accounts:login")


def register(client, email="asha@example.com"):
    return client.post(REGISTER, {"full_name": "Asha Rao", "email": email, "phone": "9876543210", "address": "",
                                  "password1": PASSWORD, "password2": PASSWORD})


def pending_session(client, email):
    s = client.session
    s["pending_verification_email"] = email
    s.save()


class VerifyFlowTests(TestCase):
    def setUp(self):
        register(self.client)
        self.user = User.objects.get(email="asha@example.com")
        self.code = code_from(mail.outbox[0])

    def test_correct_code_verifies_the_account_and_signs_the_person_in(self):
        response = self.client.post(VERIFY, {"code": self.code})
        self.assertRedirects(response, reverse("complaints:my_complaints"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_verification_email_uses_no_reply_address(self):
        self.assertEqual(mail.outbox[0].reply_to, [settings.DEFAULT_REPLY_TO_EMAIL])

    def test_a_code_works_only_once(self):
        self.client.post(VERIFY, {"code": self.code})
        other = Client()
        pending_session(other, "asha@example.com")
        response = other.post(VERIFY, {"code": self.code})
        self.assertContains(response, "not valid or has expired")
        self.assertNotIn("_auth_user_id", other.session)

    def test_wrong_codes_all_get_the_same_message(self):
        for bad in ("000000" if self.code != "000000" else "111111", "abc", "12345", "1234567", ""):
            self.assertEqual(self.client.post(VERIFY, {"code": bad}).status_code, 200, bad)
        self.assertContains(self.client.post(VERIFY, {"code": "12345"}), "not valid or has expired")
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)

    def test_attempt_limit_locks_the_code_even_for_the_right_answer(self):
        wrong = "111111" if self.code != "111111" else "222222"
        for _ in range(5):
            self.client.post(VERIFY, {"code": wrong})
        self.assertContains(self.client.post(VERIFY, {"code": self.code}), "not valid or has expired")
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)
        self.assertEqual(EmailOTP.objects.get().attempts, 5)

    def test_an_expired_code_is_refused(self):
        EmailOTP.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertContains(self.client.post(VERIFY, {"code": self.code}), "not valid or has expired")
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)

    def test_the_code_is_stored_only_as_a_hash(self):
        stored = EmailOTP.objects.get().code_hash
        self.assertEqual(len(stored), 64)
        self.assertNotIn(self.code, stored)

    def test_throttle_on_verification_attempts_per_address(self):
        with override_settings(OTP_VERIFY_LIMIT_PER_HOUR=2):
            from django.core.cache import cache
            cache.clear()
            wrong = "111111" if self.code != "111111" else "222222"
            self.client.post(VERIFY, {"code": wrong})
            self.client.post(VERIFY, {"code": wrong})
            self.assertContains(self.client.post(VERIFY, {"code": self.code}), "Too many attempts")
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)

    def test_verify_page_needs_a_pending_registration_and_is_not_for_signed_in_people(self):
        self.assertRedirects(Client().get(VERIFY), REGISTER)
        signed_in = Client()
        signed_in.force_login(make_user("other@example.com"))
        self.assertRedirects(signed_in.get(VERIFY), reverse("complaints:my_complaints"))


class ResendTests(TestCase):
    def setUp(self):
        register(self.client)
        self.old = code_from(mail.outbox[0])

    def test_resend_sends_a_new_code_and_cancels_the_old_one(self):
        response = self.client.post(RESEND, follow=True)
        self.assertContains(response, "a new code has been sent")
        self.assertEqual(len(mail.outbox), 2)
        new = code_from(mail.outbox[1])
        if new != self.old:
            self.assertContains(self.client.post(VERIFY, {"code": self.old}), "not valid or has expired")
        self.assertRedirects(self.client.post(VERIFY, {"code": new}), reverse("complaints:my_complaints"))

    @override_settings(OTP_RESEND_COOLDOWN_SECONDS=60)
    def test_cooldown_blocks_a_rapid_second_email(self):
        response = self.client.post(RESEND, follow=True)
        self.assertContains(response, "Please wait")
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(OTP_MAX_SENDS_PER_HOUR=2)
    def test_hourly_cap(self):
        self.client.post(RESEND)
        response = self.client.post(RESEND, follow=True)
        self.assertContains(response, "Too many codes")
        self.assertEqual(len(mail.outbox), 2)

    def test_resend_is_post_only_and_needs_a_pending_registration(self):
        self.assertEqual(self.client.get(RESEND).status_code, 405)
        self.assertRedirects(Client().post(RESEND), REGISTER)

    def test_resend_for_an_unknown_or_verified_address_looks_the_same_and_sends_nothing(self):
        make_user("done@example.com")
        c = Client()
        pending_session(c, "done@example.com")
        before = len(mail.outbox)
        self.assertContains(c.post(RESEND, follow=True), "If this address can be used")
        self.assertEqual(len(mail.outbox), before)


class DeliveryFailureTests(TestCase):
    def test_a_failed_email_is_never_reported_as_sent(self):
        for error in (smtplib.SMTPException("refused"), TimeoutError("timed out"), ConnectionRefusedError("down")):
            User.objects.all().delete()
            c = Client()
            with mock.patch("accounts.emails.send_routelync_email", side_effect=error):
                response = register(c, "fail@example.com")
                page = c.get(VERIFY)
            self.assertRedirects(response, VERIFY, fetch_redirect_response=False)
            self.assertContains(page, "could not send the verification email")
            self.assertNotContains(page, "we have sent a 6-digit")
            self.assertFalse(User.objects.get(email="fail@example.com").email_verified)

    def test_recovery_after_a_failure_is_one_click(self):
        c = Client()
        with mock.patch("accounts.emails.send_routelync_email", side_effect=smtplib.SMTPException("refused")):
            register(c, "retry@example.com")
        self.assertEqual(len(mail.outbox), 0)
        self.assertContains(c.post(RESEND, follow=True), "a new code has been sent")
        self.assertEqual(len(mail.outbox), 1)
        self.assertRedirects(c.post(VERIFY, {"code": code_from(mail.outbox[0])}), reverse("complaints:my_complaints"))

    def test_resend_reports_a_failure_honestly(self):
        c = Client()
        register(c, "later@example.com")
        with mock.patch("accounts.emails.send_routelync_email", side_effect=OSError("network down")):
            self.assertContains(c.post(RESEND, follow=True), "could not send the email")


class LoginPolicyTests(TestCase):
    def setUp(self):
        register(self.client)
        self.code = code_from(mail.outbox[0])
        self.client = Client()                                              # a fresh browser

    def test_unverified_citizen_with_the_right_password_is_sent_to_verification(self):
        response = self.client.post(LOGIN, {"username": "asha@example.com", "password": PASSWORD}, follow=True)
        self.assertRedirects(response, VERIFY)
        self.assertContains(response, "verify your email address first")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_password_gets_the_normal_generic_error(self):
        response = self.client.post(LOGIN, {"username": "asha@example.com", "password": "WrongPass#1"})
        self.assertContains(response, "Incorrect email or password")

    def test_unverified_sign_in_attempts_do_not_count_toward_the_lockout(self):
        for _ in range(7):
            self.client.post(LOGIN, {"username": "asha@example.com", "password": PASSWORD})
        pending_session(self.client, "asha@example.com")
        self.client.post(VERIFY, {"code": self.code})
        self.client.logout()
        response = self.client.post(LOGIN, {"username": "asha@example.com", "password": PASSWORD})
        self.assertRedirects(response, reverse("complaints:my_complaints"))

    def test_after_verification_login_works_normally(self):
        pending_session(self.client, "asha@example.com")
        self.client.post(VERIFY, {"code": self.code})
        self.client.logout()
        self.assertRedirects(self.client.post(LOGIN, {"username": "asha@example.com", "password": PASSWORD}), reverse("complaints:my_complaints"))

    def test_staff_and_script_made_accounts_never_need_verification(self):
        for role in (Role.OFFICER, Role.FIELD_WORKER, Role.ADMIN, Role.CITIZEN):
            self.assertTrue(make_user(f"{role}@staff.example.com", role).email_verified, role)


class PasswordResetEmailTests(TestCase):
    def setUp(self):
        self.user = make_user("reset@example.com", full_name="Reset Person")

    def reset_link(self):
        return re.search(r"(/accounts/reset/\S+)", mail.outbox[-1].body).group(1)

    def test_link_goes_to_the_registered_address_and_works_once(self):
        self.client.post(reverse("accounts:password_reset"), {"email": "reset@example.com"})
        self.assertEqual(mail.outbox[0].to, ["reset@example.com"])
        link = self.reset_link()
        set_url = self.client.get(link, follow=True).redirect_chain[-1][0]
        new = "Brand-New-Pass#42"
        self.assertRedirects(self.client.post(set_url, {"new_password1": new, "new_password2": new}), reverse("accounts:password_reset_complete"))
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password(new))
        self.assertFalse(User.objects.get(pk=self.user.pk).check_password(PASSWORD))            # the old password is dead
        again = Client().get(link, follow=True)                                                   # the same link cannot be used again
        self.assertContains(again, "expired or invalid")

    def test_a_confirmation_email_is_sent_and_never_contains_the_password(self):
        self.client.post(reverse("accounts:password_reset"), {"email": "reset@example.com"})
        set_url = self.client.get(self.reset_link(), follow=True).redirect_chain[-1][0]
        new = "Brand-New-Pass#42"
        self.client.post(set_url, {"new_password1": new, "new_password2": new})
        notice = mail.outbox[-1]
        self.assertEqual(notice.to, ["reset@example.com"])
        self.assertIn("was just changed", notice.body)
        self.assertNotIn(new, notice.body)
        self.assertNotIn(PASSWORD, notice.body)

    def test_the_new_password_must_pass_the_strength_rules(self):
        self.client.post(reverse("accounts:password_reset"), {"email": "reset@example.com"})
        set_url = self.client.get(self.reset_link(), follow=True).redirect_chain[-1][0]
        self.assertEqual(self.client.post(set_url, {"new_password1": "12345678", "new_password2": "12345678"}).status_code, 200)
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password(PASSWORD))

    def test_resetting_proves_mailbox_ownership_for_a_pending_account(self):
        pending = User.objects.create_user("pending@example.com", PASSWORD, full_name="Pending", email_verified=False)
        self.client.post(reverse("accounts:password_reset"), {"email": "pending@example.com"})
        set_url = self.client.get(self.reset_link(), follow=True).redirect_chain[-1][0]
        self.client.post(set_url, {"new_password1": "Brand-New-Pass#42", "new_password2": "Brand-New-Pass#42"})
        pending.refresh_from_db()
        self.assertTrue(pending.email_verified)

    def test_unknown_address_gets_the_same_page_and_no_email(self):
        response = self.client.post(reverse("accounts:password_reset"), {"email": "nobody@example.com"})
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_a_mail_failure_is_reported_not_hidden(self):
        with mock.patch("django.core.mail.message.EmailMessage.send", side_effect=smtplib.SMTPException("refused")):
            response = self.client.post(reverse("accounts:password_reset"), {"email": "reset@example.com"})
        self.assertContains(response, "could not send the email")

    def test_changing_the_password_in_the_profile_sends_a_notice(self):
        self.client.force_login(self.user)
        new = "Another-Str0ng#Pass"
        self.client.post(reverse("accounts:password_change"), {"old_password": PASSWORD, "new_password1": new, "new_password2": new})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("was just changed", mail.outbox[0].body)
        self.assertNotIn(new, mail.outbox[0].body)


class EmailConfigurationTests(TestCase):
    @override_settings(DEBUG=False, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_production_check_warns_about_a_development_email_backend(self):
        from core.checks import email_is_configured
        self.assertEqual([w.id for w in email_is_configured(None)], ["routelync.W001"])

    @override_settings(DEBUG=False, EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="", EMAIL_HOST_USER="", EMAIL_HOST_PASSWORD="")
    def test_production_check_warns_about_missing_smtp_settings(self):
        from core.checks import email_is_configured
        self.assertEqual([w.id for w in email_is_configured(None)], ["routelync.W002"])

    @override_settings(DEBUG=False, EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="smtp.example.com", EMAIL_HOST_USER="u", EMAIL_HOST_PASSWORD="p")
    def test_a_complete_smtp_configuration_passes(self):
        from core.checks import email_is_configured
        self.assertEqual(email_is_configured(None), [])

    def test_send_test_email_command(self):
        out = StringIO()
        call_command("send_test_email", "me@example.com", stdout=out)
        self.assertEqual(mail.outbox[-1].to, ["me@example.com"])
        self.assertIn("accepted the message", out.getvalue())
        with mock.patch("core.management.commands.send_test_email.send_routelync_email", side_effect=smtplib.SMTPAuthenticationError(535, b"bad credentials")):
            with self.assertRaisesMessage(CommandError, "Sending failed"):
                call_command("send_test_email", "me@example.com", stdout=StringIO())

    def test_codes_are_never_written_to_the_logs(self):
        with self.assertLogs("routelync", level="DEBUG") as logs:
            c = Client()
            register(c, "log@example.com")
            code = code_from(mail.outbox[-1])
            c.post(VERIFY, {"code": code})
        self.assertFalse(any(code in line for line in logs.output))
