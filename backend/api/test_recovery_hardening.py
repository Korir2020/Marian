import smtplib
from unittest import mock

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

REQ = "/api/auth/password-reset/"
CONF = "/api/auth/password-reset/confirm/"


def _pair(user):
    return urlsafe_base64_encode(force_bytes(user.pk)), default_token_generator.make_token(user)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RecoveryHardeningTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("rh_user", password="OldPass123!", email="rh@example.com")

    def tearDown(self):
        cache.clear()

    def _req(self, identifier):
        return self.client.post(REQ, {"identifier": identifier}, format="json")

    def _conf(self, uid, token, pw="NewPass123!"):
        return self.client.post(CONF, {"uid": uid, "token": token, "new_password": pw}, format="json")

    def test_inactive_user_gets_no_email(self):
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self._req("rh_user").status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_missing_email_gets_no_email(self):
        self.user.email = ""
        self.user.save()
        self.assertEqual(self._req("rh_user").status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_known_and_unknown_look_identical(self):
        self.assertEqual(self._req("rh_user").json(), self._req("nobody").json())

    def test_shared_email_is_never_guessed(self):
        User.objects.create_user("rh_twin", password="OldPass123!", email="RH@example.com")
        self._req("rh@example.com")
        self.assertEqual(len(mail.outbox), 0)
        self._req("rh_user")
        self.assertEqual(len(mail.outbox), 1)

    def test_email_failure_is_generic_and_logs_no_secrets(self):
        with mock.patch("api.password_recovery.send_mail", side_effect=smtplib.SMTPException("boom")):
            with self.assertLogs("api.password_recovery", level="WARNING") as cm:
                r = self._req("rh_user")
        self.assertEqual(r.status_code, 200)
        out = " ".join(cm.output)
        for secret in ("token", "uid=", "recovery=1", "rh@example.com"):
            self.assertNotIn(secret, out)

    @override_settings(PASSWORD_RESET_COOLDOWN_SECONDS=60)
    def test_per_account_cooldown(self):
        for _ in range(3):
            self.assertEqual(self._req("rh_user").status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_non_dict_bodies_fail_safely(self):
        self.assertEqual(self.client.post(REQ, [1, 2], format="json").status_code, 200)
        self.assertEqual(self.client.post(CONF, [1, 2], format="json").status_code, 400)

    def test_malformed_uid_and_token_fail_safely(self):
        uid, _ = _pair(self.user)
        for u, t in (("!!!", "x"), ("", ""), (uid, ""), (uid, "bad-token")):
            self.assertEqual(self._conf(u, t).status_code, 400)
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password("OldPass123!"))

    def test_expired_token_fails(self):
        uid, token = _pair(self.user)
        with override_settings(PASSWORD_RESET_TIMEOUT=-1):
            self.assertEqual(self._conf(uid, token).status_code, 400)

    def test_token_is_single_use(self):
        uid, token = _pair(self.user)
        self.assertEqual(self._conf(uid, token).status_code, 200)
        self.assertEqual(self._conf(uid, token, "OtherPass123!").status_code, 400)

    def test_token_is_bound_to_its_user(self):
        other = User.objects.create_user("rh_other", password="OldPass123!", email="o@example.com")
        uid_other, _ = _pair(other)
        _, token = _pair(self.user)
        self.assertEqual(self._conf(uid_other, token).status_code, 400)
        self.assertTrue(User.objects.get(pk=other.pk).check_password("OldPass123!"))

    def test_inactive_user_cannot_confirm(self):
        uid, token = _pair(self.user)
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self._conf(uid, token).status_code, 400)

    def test_weak_password_rejected_and_token_still_usable(self):
        uid, token = _pair(self.user)
        self.assertEqual(self._conf(uid, token, "123").status_code, 400)
        self.assertEqual(self._conf(uid, token).status_code, 200)

    def test_confirm_revokes_refresh_tokens(self):
        refresh = RefreshToken.for_user(self.user)
        uid, token = _pair(self.user)
        self.assertEqual(self._conf(uid, token).status_code, 200)
        r = self.client.post("/api/auth/refresh/", {"refresh": str(refresh)}, format="json")
        self.assertEqual(r.status_code, 401)
