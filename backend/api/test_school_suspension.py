from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import School, SchoolAdminProfile
from .suspension import school_for_user, suspended_school_for

PW = "Xk9-secure-pass"


class SchoolSuspensionTests(APITestCase):
    def setUp(self):
        self.a = School.objects.create(name="A", code="A1")
        self.b = School.objects.create(name="B", code="B1")
        self.root = User.objects.create_superuser("root", "r@example.com", PW)
        self.boss = User.objects.create_user("boss", password=PW)
        SchoolAdminProfile.objects.create(user=self.boss, school=self.a)

    def url(self, s):
        return f"/api/schools/{s.id}/suspension/"

    def patch(self, s, data, who=None):
        if who:
            self.client.force_authenticate(who)
        return self.client.patch(self.url(s), data, format="json")

    def test_school_admin_cannot_suspend(self):
        r = self.patch(self.a, {"suspended": True, "reason": "Fraud investigation"}, self.boss)
        self.assertEqual(r.status_code, 403)
        self.a.refresh_from_db()
        self.assertFalse(self.a.is_suspended)

    def test_anonymous_rejected(self):
        r = self.patch(self.a, {"suspended": True, "reason": "Fraud investigation"})
        self.assertIn(r.status_code, (401, 403))

    def test_reason_required(self):
        r = self.patch(self.a, {"suspended": True, "reason": "short"}, self.root)
        self.assertEqual(r.status_code, 400)
        self.a.refresh_from_db()
        self.assertFalse(self.a.is_suspended)

    def test_flag_must_be_boolean(self):
        r = self.patch(self.a, {"suspended": "yes", "reason": "Fraud investigation"}, self.root)
        self.assertEqual(r.status_code, 400)

    def test_suspend_then_reinstate_only_that_school(self):
        r = self.patch(self.a, {"suspended": True, "reason": "Fraud investigation"}, self.root)
        self.assertEqual(r.status_code, 200)
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertTrue(self.a.is_suspended)
        self.assertFalse(self.b.is_suspended)
        self.assertEqual(self.a.suspended_by, self.root)
        r = self.patch(self.a, {"suspended": False}, self.root)
        self.assertEqual(r.status_code, 200)
        self.a.refresh_from_db()
        self.assertFalse(self.a.is_suspended)
        self.assertEqual(self.a.suspended_reason, "")

    def test_helper_finds_users_school(self):
        self.assertEqual(school_for_user(self.boss), self.a)
        self.assertIsNone(school_for_user(self.root))
        self.assertIsNone(suspended_school_for(self.boss))
        self.a.is_suspended = True
        self.a.save()
        self.assertEqual(suspended_school_for(self.boss), self.a)
