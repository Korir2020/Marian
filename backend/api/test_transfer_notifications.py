from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import Notification, School, SchoolAdminProfile, TeacherProfile


class TransferNotificationTests(APITestCase):
    def setUp(self):
        self.source = School.objects.create(name="Notify Source", code="NSRC")
        self.target = School.objects.create(name="Notify Target", code="NTGT")
        self.source_admin = User.objects.create_user("notify_source", password="pass12345")
        self.target_admin = User.objects.create_user("notify_target", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.source_admin, school=self.source)
        SchoolAdminProfile.objects.create(user=self.target_admin, school=self.target)
        self.teacher = User.objects.create_user("notify_teacher", password="pass12345")
        self.profile = TeacherProfile.objects.create(user=self.teacher, school=self.source)

    def test_request_and_approval_notify_only_involved_schools(self):
        self.client.force_authenticate(self.source_admin)
        created = self.client.post("/api/teacher-transfers/", {"teacher_id": self.profile.id, "target_school_id": self.target.id}, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(Notification.objects.filter(school=self.target, kind="teacher_transfer_requested").count(), 1)
        self.assertEqual(Notification.objects.filter(school=self.source).count(), 0)
        self.client.force_authenticate(self.target_admin)
        approved = self.client.post(f"/api/teacher-transfers/{created.json()['id']}/action/", {"action": "approve"}, format="json")
        self.assertEqual(approved.status_code, 200)
        self.assertTrue(Notification.objects.filter(school=self.source, kind="teacher_transfer_approved").exists())
        self.assertTrue(Notification.objects.filter(school=self.target, kind="teacher_transfer_approved").exists())
        self.assertTrue(Notification.objects.filter(recipient=self.teacher, kind="teacher_transfer_approved").exists())
