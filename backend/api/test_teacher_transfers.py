from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import School, SchoolAdminProfile, TeacherProfile, TeacherTransferRequest


class TeacherTransferTests(APITestCase):
    def setUp(self):
        self.source = School.objects.create(name="Source School", code="SRC")
        self.target = School.objects.create(name="Target School", code="TGT")
        self.source_admin = User.objects.create_user("sourceadmin", password="pass12345")
        self.target_admin = User.objects.create_user("targetadmin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.source_admin, school=self.source)
        SchoolAdminProfile.objects.create(user=self.target_admin, school=self.target)
        self.teacher_user = User.objects.create_user("transferteacher", password="pass12345")
        self.teacher = TeacherProfile.objects.create(user=self.teacher_user, school=self.source, staff_id="T1")

    def test_source_requests_target_approves_and_access_moves(self):
        self.client.force_authenticate(self.source_admin)
        created = self.client.post("/api/teacher-transfers/", {"teacher_id": self.teacher.id, "target_school_id": self.target.id, "reason": "Staff relocation"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        transfer_id = created.json()["id"]
        self.client.force_authenticate(self.target_admin)
        approved = self.client.post(f"/api/teacher-transfers/{transfer_id}/action/", {"action": "approve"}, format="json")
        self.assertEqual(approved.status_code, 200, approved.content)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.school_id, self.target.id)
        self.assertEqual(TeacherTransferRequest.objects.get(pk=transfer_id).status, "approved")
        self.client.force_authenticate(self.source_admin)
        source_rows = self.client.get("/api/teacher-transfers/").json()["results"]
        self.assertEqual(len(source_rows), 1)

    def test_source_cannot_approve_and_duplicate_is_blocked(self):
        self.client.force_authenticate(self.source_admin)
        created = self.client.post("/api/teacher-transfers/", {"teacher_id": self.teacher.id, "target_school_id": self.target.id}, format="json")
        self.assertEqual(created.status_code, 201)
        duplicate = self.client.post("/api/teacher-transfers/", {"teacher_id": self.teacher.id, "target_school_id": self.target.id}, format="json")
        self.assertEqual(duplicate.status_code, 409)
        denied = self.client.post(f"/api/teacher-transfers/{created.json()['id']}/action/", {"action": "approve"}, format="json")
        self.assertEqual(denied.status_code, 403)

    def test_rejection_preserves_source_access(self):
        self.client.force_authenticate(self.source_admin)
        created = self.client.post("/api/teacher-transfers/", {"teacher_id": self.teacher.id, "target_school_id": self.target.id}, format="json")
        self.client.force_authenticate(self.target_admin)
        rejected = self.client.post(f"/api/teacher-transfers/{created.json()['id']}/action/", {"action": "reject", "note": "Position unavailable"}, format="json")
        self.assertEqual(rejected.status_code, 200)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.school_id, self.source.id)
