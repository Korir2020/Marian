from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import AcademicYear, FeePayment, FeeStructure, Performance, School, SchoolAdminProfile, Student, StudentFee, Subject, Term


class DocumentExportTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Docs School", code="DOC1", phone="0700000000")
        self.admin = User.objects.create_user("docsadmin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.student = Student.objects.create(school=self.school, first_name="Export", last_name="Student", admission_number="D1")
        year = AcademicYear.objects.create(school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.term = Term.objects.create(academic_year=year, name="Term 1", start_date=date(2026, 1, 1), end_date=date(2026, 4, 1), is_active=True)
        subject = Subject.objects.create(school=self.school, name="Mathematics")
        Performance.objects.create(student=self.student, subject=subject, academic_year=year, term=self.term, marks=Decimal("80"), status="approved")
        structure = FeeStructure.objects.create(school=self.school, academic_year=year, name="Tuition", amount=Decimal("1000"))
        invoice = StudentFee.objects.create(student=self.student, fee_structure=structure, amount_due=Decimal("1000"))
        self.payment = FeePayment.objects.create(student_fee=invoice, amount=Decimal("500"), method="cash", reference="CASH-1", received_by=self.admin)

    def test_preview_and_combined_report_pdf(self):
        self.client.force_authenticate(self.admin)
        preview = self.client.get(f"/api/documents/report-cards/?term_id={self.term.id}")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["eligible_count"], 1)
        pdf = self.client.post("/api/documents/report-cards/", {"term_id": self.term.id, "student_ids": [self.student.id], "format": "combined"}, format="json")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_receipt_uses_stable_payment_id_and_zip(self):
        self.client.force_authenticate(self.admin)
        preview = self.client.get("/api/documents/fee-receipts/")
        self.assertEqual(preview.json()["payments"][0]["receipt_number"], f"RCPT-DOC1-{self.payment.id:06d}")
        archive = self.client.post("/api/documents/fee-receipts/", {"payment_ids": [self.payment.id], "format": "zip"}, format="json")
        self.assertEqual(archive.status_code, 200)
        self.assertEqual(archive["Content-Type"], "application/zip")
        self.assertTrue(archive.content.startswith(b"PK"))
