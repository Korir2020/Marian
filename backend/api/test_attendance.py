from datetime import date

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import AcademicYear, School, SchoolAdminProfile, Student, Term


class AttendanceInterventionTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Attendance School", code="ATT")
        self.other = School.objects.create(name="Other", code="OTH")
        self.admin = User.objects.create_user("attendanceadmin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.student = Student.objects.create(school=self.school, first_name="Attend", last_name="Student", admission_number="AT1")
        self.outsider = Student.objects.create(school=self.other, first_name="Other", last_name="Student", admission_number="OT1")

    def test_bulk_attendance_is_saved_and_school_scoped(self):
        self.client.force_authenticate(self.admin)
        day = "2026-10-13"
        saved = self.client.post("/api/attendance/", {"date": day, "records": [{"student_id": self.student.id, "status": "late"}, {"student_id": self.outsider.id, "status": "absent"}]}, format="json")
        self.assertEqual(saved.status_code, 200)
        rows = self.client.get(f"/api/attendance/?date={day}")
        self.assertEqual(rows.status_code, 200)
        self.assertEqual(rows.json()["students"][0]["status"], "late")
        self.assertEqual(len(rows.json()["students"]), 1)

    def test_intervention_can_be_created_and_closed(self):
        self.client.force_authenticate(self.admin)
        created = self.client.post(f"/api/students/{self.student.id}/interventions/", {"reason": "absence", "notes": "Three absences this month", "action_plan": "Parent meeting", "follow_up_date": "2026-10-20"}, format="json")
        self.assertEqual(created.status_code, 201)
        intervention_id = created.json()["id"]
        closed = self.client.patch(f"/api/students/{self.student.id}/interventions/", {"id": intervention_id, "outcome": "improved"}, format="json")
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.json()["outcome"], "improved")
