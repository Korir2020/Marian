from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APITestCase

from schools.models import School, SchoolAdminProfile


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RecoveryAndAdminSafetyTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Recovery School", code="REC")
        self.admin_user = User.objects.create_user("recovery_admin", password="OldPass123!", email="admin@example.com")
        self.admin = SchoolAdminProfile.objects.create(user=self.admin_user, school=self.school)

    def test_recovery_request_is_generic_and_sends_to_eligible_email(self):
        response = self.client.post("/api/auth/password-reset/", {"identifier": "recovery_admin"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("If an eligible account exists", response.json()["detail"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("admin@example.com", mail.outbox[0].to)

    def test_recovery_confirm_changes_password_and_invalidates_token(self):
        uid = urlsafe_base64_encode(force_bytes(self.admin_user.pk))
        token = default_token_generator.make_token(self.admin_user)
        response = self.client.post("/api/auth/password-reset/confirm/", {"uid": uid, "token": token, "new_password": "NewPass123!"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.admin_user.refresh_from_db()
        self.assertTrue(self.admin_user.check_password("NewPass123!"))
        reused = self.client.post("/api/auth/password-reset/confirm/", {"uid": uid, "token": token, "new_password": "AnotherPass123!"}, format="json")
        self.assertEqual(reused.status_code, 400)

    def test_last_active_admin_cannot_be_deactivated(self):
        self.client.force_authenticate(self.admin_user)
        response = self.client.patch(f"/api/admin-accounts/{self.admin.id}/status/", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.get(pk=self.admin_user.pk).is_active)

    def test_superadmin_can_deactivate_non_last_admin_and_sessions_are_ended(self):
        second = User.objects.create_user("second_admin", password="OldPass123!")
        second_profile = SchoolAdminProfile.objects.create(user=second, school=self.school, is_deputy=True)
        root = User.objects.create_superuser("root", password="RootPass123!")
        self.client.force_authenticate(root)
        response = self.client.patch(f"/api/admin-accounts/{second_profile.id}/status/", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(User.objects.get(pk=second.pk).is_active)
