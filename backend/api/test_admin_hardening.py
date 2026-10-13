from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from api.admin_throttle import AdminAccountThrottle
from schools.models import MarkAuditLog, School, SchoolAdminProfile, TeacherProfile

LIST = "/api/admin-accounts/"
NEW = "Str0ng-pass-91"


class AdminHardeningTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.a = School.objects.create(name="HA", code="HA1")
        self.b = School.objects.create(name="HB", code="HB1")
        self.root = User.objects.create_superuser("hroot", "r@x.com", "pass12345")
        self.boss = self.admin("hboss", self.a)
        self.dep = self.admin("hdep", self.a, True)
        self.dep2 = self.admin("hdep2", self.a, True)
        self.bossb = self.admin("hbossb", self.b)
        self.depb = self.admin("hdepb", self.b, True)
        self.teacher = User.objects.create_user("hteach", password="pass12345")
        TeacherProfile.objects.create(user=self.teacher, school=self.a)
        self.plain = User.objects.create_user("hplain", password="pass12345")

    def tearDown(self):
        cache.clear()

    def admin(self, name, school, deputy=False):
        u = User.objects.create_user(name, password="pass12345")
        return SchoolAdminProfile.objects.create(user=u, school=school, is_deputy=deputy)

    def status(self, user, profile, active=False):
        self.client.force_authenticate(user)
        return self.client.patch(f"{LIST}{profile.id}/status/", {"is_active": active}, format="json")

    def reset(self, user, profile, pw=NEW):
        self.client.force_authenticate(user)
        return self.client.post(f"{LIST}{profile.id}/reset-password/", {"password": pw}, format="json")

    def active(self, profile):
        return User.objects.get(pk=profile.user_id).is_active

    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.patch(f"{LIST}{self.dep.id}/status/", {"is_active": False}, format="json").status_code, 401)
        self.assertEqual(self.client.post(f"{LIST}{self.dep.id}/reset-password/", {"password": NEW}, format="json").status_code, 401)

    def test_wrong_roles_get_403(self):
        for u in (self.dep2.user, self.teacher, self.plain):
            self.assertEqual(self.status(u, self.dep).status_code, 403)
            self.assertEqual(self.reset(u, self.dep).status_code, 403)
        self.assertTrue(self.active(self.dep))
        self.assertTrue(User.objects.get(pk=self.dep.user_id).check_password("pass12345"))

    def test_other_school_gets_404(self):
        self.assertEqual(self.status(self.boss.user, self.depb).status_code, 404)
        self.assertEqual(self.status(self.bossb.user, self.dep).status_code, 404)
        self.assertEqual(self.reset(self.bossb.user, self.dep).status_code, 404)
        self.assertTrue(self.active(self.depb))
        self.assertTrue(self.active(self.dep))

    def test_school_admin_cannot_manage_another_full_admin(self):
        boss2 = self.admin("hboss2", self.a)
        self.assertEqual(self.status(self.boss.user, boss2).status_code, 403)
        self.assertEqual(self.reset(self.boss.user, boss2).status_code, 403)
        self.assertTrue(self.active(boss2))

    def test_deactivating_deputy_ends_sessions_and_blocks_access_token(self):
        refresh = RefreshToken.for_user(self.dep.user)
        access = str(refresh.access_token)
        self.assertEqual(self.status(self.boss.user, self.dep).status_code, 200)
        self.assertFalse(self.active(self.dep))
        self.assertEqual(BlacklistedToken.objects.filter(token__user=self.dep.user).count(), 1)
        self.assertTrue(MarkAuditLog.objects.filter(action="admin_deactivated", school=self.a).exists())
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        r = self.client.post("/api/auth/refresh/", {"refresh": str(refresh)}, format="json")
        self.assertEqual(r.status_code, 401)
        self.client.credentials()

    def test_nobody_can_deactivate_themselves(self):
        self.assertEqual(self.status(self.boss.user, self.boss).status_code, 400)
        ru = User.objects.create_superuser("hroot2", "r2@x.com", "pass12345")
        rp = SchoolAdminProfile.objects.create(user=ru, school=self.a)
        self.assertEqual(self.status(ru, rp).status_code, 400)
        self.assertTrue(self.active(self.boss))
        self.assertTrue(self.active(rp))

    def test_last_full_admin_is_protected_even_if_a_deputy_remains(self):
        self.assertEqual(self.status(self.root, self.bossb).status_code, 409)
        self.assertTrue(self.active(self.bossb))
        self.assertEqual(self.status(self.root, self.depb).status_code, 200)

    def test_last_admin_in_deputy_only_school_is_protected(self):
        c = School.objects.create(name="HC", code="HC1")
        only = self.admin("honly", c, True)
        self.assertEqual(self.status(self.root, only).status_code, 409)
        self.assertTrue(self.active(only))

    def test_back_to_back_deactivations_never_leave_zero_full_admins(self):
        boss2 = self.admin("hboss2", self.a)
        self.assertEqual(self.status(self.root, self.boss).status_code, 200)
        self.assertEqual(self.status(self.root, boss2).status_code, 409)
        self.assertTrue(self.active(boss2))
        self.assertEqual(self.status(self.root, self.boss, True).status_code, 200)
        self.assertTrue(self.active(self.boss))

    def test_repeated_deactivation_is_idempotent(self):
        self.assertEqual(self.status(self.boss.user, self.dep).status_code, 200)
        self.assertEqual(self.status(self.boss.user, self.dep).status_code, 200)
        self.assertFalse(self.active(self.dep))

    def test_cannot_touch_deputy_accounts_with_elevated_flags(self):
        for flag in ("is_staff", "is_superuser"):
            u = self.dep.user
            setattr(u, flag, True)
            u.save()
            self.assertEqual(self.status(self.boss.user, self.dep).status_code, 403)
            self.assertEqual(self.reset(self.boss.user, self.dep).status_code, 403)
            u.refresh_from_db()
            self.assertTrue(u.is_active)
            self.assertTrue(u.check_password("pass12345"))
            setattr(u, flag, False)
            u.save()

    def test_invalid_is_active_values_rejected(self):
        for bad in ("false", 0, None, ""):
            self.client.force_authenticate(self.boss.user)
            r = self.client.patch(f"{LIST}{self.dep.id}/status/", {"is_active": bad}, format="json")
            self.assertEqual(r.status_code, 400)
        self.assertTrue(self.active(self.dep))

    def test_non_dict_bodies_fail_safely(self):
        self.client.force_authenticate(self.boss.user)
        r = self.client.patch(f"{LIST}{self.dep.id}/status/", [1], format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post(f"{LIST}{self.dep.id}/reset-password/", [1], format="json")
        self.assertEqual(r.status_code, 400)

    def test_reset_audit_never_contains_the_password(self):
        self.assertEqual(self.reset(self.boss.user, self.dep).status_code, 200)
        log = MarkAuditLog.objects.get(action="admin_password_reset", school=self.a)
        self.assertNotIn(NEW, str(log.details))

    def test_admin_endpoints_are_throttled(self):
        with mock.patch.object(AdminAccountThrottle, "THROTTLE_RATES", {"admin_account": "2/min"}):
            codes = [self.status(self.boss.user, self.dep, True).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])
