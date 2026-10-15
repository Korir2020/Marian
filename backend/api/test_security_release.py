import re
import time
from datetime import date

from django.contrib.auth.models import User
from django.core import mail
from django.test import override_settings
from rest_framework.test import APITestCase

from schools.models import School, SchoolAdminProfile, SchoolRegistration
from .totp import code_for


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SecurityReleaseTests(APITestCase):
    def test_registration_email_otp_is_hashed_single_use_and_required(self):
        response = self.client.post("/api/school-registration/", {
            "school_name": "OTP Academy", "proposed_school_code": "OTP1",
            "school_type": "secondary", "school_phone": "+254712345678",
            "county": "Nairobi", "administrator_name": "A Person",
            "administrator_username": "otpadmin", "administrator_email": "otp@example.com",
            "administrator_phone": "+254712345679", "password": "Strong-pass-123!",
            "confirm_password": "Strong-pass-123!", "authorized": True,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        reg = SchoolRegistration.objects.get()
        self.assertNotEqual(reg.otp_hash, "")
        self.assertNotIn("123456", reg.otp_hash)
        code = re.search(r"\b(\d{6})\b", mail.outbox[0].body).group(1)
        verified = self.client.post("/api/school-registration/verify/", {"reference": reg.reference, "code": code}, format="json")
        self.assertEqual(verified.status_code, 200, verified.content)
        reg.refresh_from_db()
        self.assertEqual(reg.verification_status, "verified")
        self.assertEqual(self.client.post("/api/school-registration/verify/", {"reference": reg.reference, "code": code}, format="json").status_code, 400)

    def test_superadmin_mfa_is_required_for_sensitive_account_change(self):
        root = User.objects.create_superuser("root", "root@example.com", "RootPass-123!")
        other = User.objects.create_superuser("other", "other@example.com", "OtherPass-123!")
        self.client.force_authenticate(root)
        setup = self.client.get("/api/auth/mfa/setup/")
        self.assertEqual(setup.status_code, 200)
        secret = setup.json()["secret"]
        self.assertEqual(self.client.post("/api/auth/mfa/confirm/", {"code": "000000"}, format="json").status_code, 400)
        confirmed = self.client.post("/api/auth/mfa/confirm/", {"code": code_for(secret, int(time.time()) // 30)}, format="json")
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        blocked = self.client.patch(f"/api/superadmin-accounts/{other.id}/status/", {"is_active": False, "mfa_code": "000000"}, format="json")
        self.assertEqual(blocked.status_code, 403)
        code = code_for(secret, int(time.time()) // 30)
        changed = self.client.patch(f"/api/superadmin-accounts/{other.id}/status/", {"is_active": False, "mfa_code": code}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)

    def test_last_active_superadmin_cannot_be_disabled(self):
        root = User.objects.create_superuser("root", "root@example.com", "RootPass-123!")
        self.client.force_authenticate(root)
        setup = self.client.get("/api/auth/mfa/setup/")
        secret = setup.json()["secret"]
        self.client.post("/api/auth/mfa/confirm/", {"code": code_for(secret, int(time.time()) // 30)}, format="json")
        response = self.client.patch(f"/api/superadmin-accounts/{root.id}/status/", {"is_active": False, "mfa_code": code_for(secret, int(time.time()) // 30)}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.get(pk=root.id).is_active)

    def test_school_admin_cannot_view_other_school_data(self):
        a = School.objects.create(name="A", code="SEC-A")
        b = School.objects.create(name="B", code="SEC-B")
        admin = User.objects.create_user("aadmin", password="AdminPass-123!")
        SchoolAdminProfile.objects.create(user=admin, school=a)
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.get("/api/students/", {"school": b.id}).json().get("count"), 0)
        self.assertEqual(self.client.get("/api/audit-logs/").status_code, 200)
        self.assertFalse(any(row.get("school") == b.id for row in self.client.get("/api/audit-logs/").json()))
