import csv
import io

from django.db import transaction
from django.http import HttpResponse
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiTypes

from schools.models import AcademicYear, Enrollment, SchoolAdminProfile, Student, Stream
from .views import _scope

_HEADERS = ["first_name", "last_name", "admission_number", "class_level", "stream"]


def _admin(request):
    return request.is_superuser or SchoolAdminProfile.objects.filter(user=request).exists()


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiResponse(description="CSV preview or student roster export."), 201: OpenApiResponse(description="Validated student rows committed."), 400: OpenApiResponse(description="CSV validation failure."), 403: OpenApiResponse(description="Administrator authorization required."), 413: OpenApiResponse(description="CSV exceeds the 5 MB upload limit.")})
@api_view(["GET", "POST"])
@parser_classes([MultiPartParser, FormParser])
def student_import(request):
    school_id, error = _scope(request)
    if error: return error
    if not _admin(request.user): return Response({"detail": "Only school administrators can import students."}, status=403)
    if request.method == "GET":
        rows = Student.objects.filter(school_id=school_id).select_related("school") if school_id else Student.objects.all()
        out = io.StringIO(); writer = csv.writer(out); writer.writerow(_HEADERS)
        for student in rows.order_by("last_name", "first_name"):
            enrollment = Enrollment.objects.filter(student=student, is_active=True).select_related("class_level", "stream").first()
            writer.writerow([student.first_name, student.last_name, student.admission_number, enrollment.class_level.name if enrollment else "", enrollment.stream.name if enrollment and enrollment.stream else ""])
        response = HttpResponse(out.getvalue(), content_type="text/csv"); response["Content-Disposition"] = 'attachment; filename="students.csv"'; return response
    upload = request.FILES.get("file")
    if not upload: return Response({"detail": "Attach a CSV file."}, status=400)
    if upload.size > 5 * 1024 * 1024: return Response({"detail": "CSV files must be 5 MB or smaller."}, status=413)
    try: rows = list(csv.DictReader(io.TextIOWrapper(upload.file, encoding="utf-8-sig")))
    except (UnicodeDecodeError, csv.Error): return Response({"detail": "The file must be a valid UTF-8 CSV."}, status=400)
    missing = [x for x in _HEADERS if x not in (rows[0].keys() if rows else [])]
    if missing: return Response({"detail": f"Missing columns: {', '.join(missing)}"}, status=400)
    errors, valid = [], []
    for index, row in enumerate(rows, start=2):
        values = {k: (row.get(k) or "").strip() for k in _HEADERS}
        if not values["first_name"] or not values["last_name"] or not values["admission_number"]: errors.append({"row": index, "error": "First name, last name, and admission number are required."}); continue
        if Student.objects.filter(admission_number=values["admission_number"], **({"school_id": school_id} if school_id else {})).exists() or any(x["admission_number"] == values["admission_number"] for x in valid): errors.append({"row": index, "error": "Admission number already exists."}); continue
        stream = Stream.objects.filter(name__iexact=values["stream"], school_id=school_id).select_related("class_level").first() if values["stream"] else None
        if values["stream"] and not stream: errors.append({"row": index, "error": f"Stream not found: {values['stream']}"}); continue
        if values["class_level"] and stream and stream.class_level.name.lower() != values["class_level"].lower(): errors.append({"row": index, "error": "Class level does not match the stream."}); continue
        valid.append({**values, "stream_obj": stream})
    commit = str(request.data.get("commit", "false")).lower() == "true"
    if errors or not commit: return Response({"preview": [{k: v for k, v in row.items() if k != "stream_obj"} for row in valid], "errors": errors, "ready": not errors and bool(valid), "committed": False})
    with transaction.atomic():
        for row in valid:
            student = Student.objects.create(school_id=school_id, first_name=row["first_name"], last_name=row["last_name"], admission_number=row["admission_number"])
            if row["stream_obj"]:
                year = AcademicYear.objects.filter(school_id=school_id, is_active=True).first()
                if year: Enrollment.objects.create(student=student, academic_year=year, class_level=row["stream_obj"].class_level, stream=row["stream_obj"], is_active=True)
    return Response({"preview": [{k: v for k, v in row.items() if k != "stream_obj"} for row in valid], "errors": [], "ready": True, "committed": True, "created": len(valid)}, status=201)
