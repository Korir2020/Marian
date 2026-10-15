from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from schools.models import AcademicYear, School, SchoolAdminProfile, Student


class StudentImportTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Import School", code="IMP")
        self.admin = User.objects.create_user("importadmin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.year = AcademicYear.objects.create(school=self.school, name="2026", start_date="2026-01-01", end_date="2026-12-31", is_active=True)
        self.client.force_authenticate(self.admin)

    def test_preview_rejects_duplicate_and_commit_creates_valid_rows(self):
        csv = b"first_name,last_name,admission_number,class_level,stream\nNew,Student,N1,,\nDuplicate,Student,N1,,\n"
        preview = self.client.post("/api/students/import/", {"file": SimpleUploadedFile("students.csv", csv, content_type="text/csv")}, format="multipart")
        self.assertEqual(preview.status_code, 200)
        self.assertFalse(preview.json()["ready"])
        self.assertEqual(Student.objects.count(), 0)
        valid_csv = b"first_name,last_name,admission_number,class_level,stream\nNew,Student,N2,,\n"
        committed = self.client.post("/api/students/import/", {"file": SimpleUploadedFile("students.csv", valid_csv, content_type="text/csv"), "commit": "true"}, format="multipart")
        self.assertEqual(committed.status_code, 201)
        self.assertEqual(Student.objects.filter(school=self.school).count(), 1)

    def test_roster_export_is_csv(self):
        result = self.client.get("/api/students/import/")
        self.assertEqual(result["Content-Type"], "text/csv")
        self.assertIn(b"admission_number", result.content)
