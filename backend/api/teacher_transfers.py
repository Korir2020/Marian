from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiTypes

from schools.models import MarkAuditLog, School, SchoolAdminProfile, TeacherProfile, TeacherTransferRequest
from .notify import notify_admins, notify_user
from .admin_throttle import TransferAdminThrottle


def _admin(user):
    return SchoolAdminProfile.objects.filter(user=user).select_related("school").first()


def _row(x):
    return {"id": x.id, "teacher_id": x.teacher_id, "teacher": x.teacher.user.get_full_name() or x.teacher.user.username, "username": x.teacher.user.username, "source_school_id": x.source_school_id, "source_school": x.source_school.name, "target_school_id": x.target_school_id, "target_school": x.target_school.name, "status": x.status, "reason": x.reason, "decision_note": x.decision_note, "created_at": x.created_at, "decided_at": x.decided_at}


@extend_schema(responses={200: OpenApiResponse(description="Authorized school names available as transfer targets.")})
@api_view(["GET"])
@throttle_classes([TransferAdminThrottle])
def transfer_targets(request):
    if not request.user.is_authenticated or (not request.user.is_superuser and _admin(request.user) is None): return Response({"detail": "Only authorized administrators can view transfer targets."}, status=403)
    return Response([{"id": x.id, "name": x.name, "code": x.code} for x in School.objects.order_by("name")])


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiResponse(description="School-scoped teacher transfer requests."), 201: OpenApiResponse(description="Transfer request created."), 403: OpenApiResponse(description="Administrator authorization required."), 409: OpenApiResponse(description="Duplicate pending request.")})
@api_view(["GET", "POST"])
@throttle_classes([TransferAdminThrottle])
def transfer_collection(request):
    admin = _admin(request.user)
    if not request.user.is_authenticated or (not request.user.is_superuser and admin is None): return Response({"detail": "Only Superadmins and school administrators can manage teacher transfers."}, status=403)
    if request.method == "GET":
        qs = TeacherTransferRequest.objects.all() if request.user.is_superuser else TeacherTransferRequest.objects.filter(Q(source_school=admin.school) | Q(target_school=admin.school))
        qs = qs.select_related("teacher__user", "source_school", "target_school")
        return Response({"results": [_row(x) for x in qs.order_by("-created_at")]})
    teacher = TeacherProfile.objects.filter(pk=request.data.get("teacher_id")).select_related("user", "school").first()
    target = School.objects.filter(pk=request.data.get("target_school_id")).first()
    if not teacher or not target or teacher.school_id == target.id: return Response({"detail": "Choose a valid teacher and a different receiving school."}, status=400)
    if not request.user.is_superuser and teacher.school_id != admin.school_id: return Response({"detail": "You can only transfer teachers from your own school."}, status=403)
    if TeacherTransferRequest.objects.filter(teacher=teacher, target_school=target, status="pending").exists(): return Response({"detail": "A pending transfer already exists."}, status=409)
    try:
        x = TeacherTransferRequest.objects.create(teacher=teacher, source_school_id=teacher.school_id, target_school=target, requested_by=request.user, reason=str(request.data.get("reason", ""))[:2000])
    except IntegrityError: return Response({"detail": "A pending transfer already exists."}, status=409)
    MarkAuditLog.objects.create(school=teacher.school, user=request.user, action="teacher_transfer_requested", details={"transfer_id": x.id, "teacher_id": teacher.id, "target_school_id": target.id})
    notify_admins(target, "teacher_transfer_requested", f"Teacher transfer requested: {teacher.user.get_full_name() or teacher.user.username} from {teacher.school.name}.")
    return Response(_row(x), status=201)


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiResponse(description="Transfer approved or rejected."), 403: OpenApiResponse(description="Only an authorized party may decide this transfer."), 409: OpenApiResponse(description="Transfer state does not allow this action.")})
@api_view(["POST"])
@throttle_classes([TransferAdminThrottle])
def transfer_action(request, pk):
    admin = _admin(request.user)
    if not request.user.is_authenticated or (not request.user.is_superuser and admin is None): return Response({"detail": "Only Superadmins and school administrators can decide transfers."}, status=403)
    action = request.data.get("action")
    with transaction.atomic():
        x = TeacherTransferRequest.objects.select_for_update().select_related("teacher__user", "source_school", "target_school").filter(pk=pk).first()
        if not x: return Response({"detail": "Transfer not found."}, status=404)
        if not request.user.is_superuser and admin.school_id not in (x.source_school_id, x.target_school_id): return Response({"detail": "You are not party to this transfer."}, status=403)
        if x.status == "approved": return Response(_row(x)) if action == "approve" else Response({"detail": "An approved transfer cannot be rejected."}, status=409)
        if x.status == "rejected": return Response(_row(x)) if action == "reject" else Response({"detail": "A rejected transfer must be submitted again."}, status=409)
        note = str(request.data.get("note", ""))[:2000]
        if action == "reject":
            x.status, x.decision_note, x.approved_by, x.decided_at = "rejected", note, request.user, timezone.now(); x.save(update_fields=["status", "decision_note", "approved_by", "decided_at"])
            MarkAuditLog.objects.create(school=x.source_school, user=request.user, action="teacher_transfer_rejected", details={"transfer_id": x.id, "teacher_id": x.teacher_id})
            notify_admins(x.source_school, "teacher_transfer_rejected", f"Teacher transfer rejected: {x.teacher.user.get_full_name() or x.teacher.user.username}.")
            notify_admins(x.target_school, "teacher_transfer_rejected", f"Teacher transfer rejected: {x.teacher.user.get_full_name() or x.teacher.user.username}.")
            return Response(_row(x))
        if action != "approve": return Response({"detail": "Action must be approve or reject."}, status=400)
        if not request.user.is_superuser and admin.school_id != x.target_school_id: return Response({"detail": "Only the receiving school can approve a transfer."}, status=403)
        if x.teacher.school_id != x.source_school_id: return Response({"detail": "Teacher is no longer active in the source school."}, status=409)
        x.teacher.school_id = x.target_school_id; x.teacher.save(update_fields=["school"])
        x.status, x.decision_note, x.approved_by, x.decided_at = "approved", note, request.user, timezone.now(); x.save(update_fields=["status", "decision_note", "approved_by", "decided_at"])
        MarkAuditLog.objects.create(school=x.target_school, user=request.user, action="teacher_transfer_approved", details={"transfer_id": x.id, "teacher_id": x.teacher_id, "source_school_id": x.source_school_id})
        notify_admins(x.source_school, "teacher_transfer_approved", f"Teacher transfer approved: {x.teacher.user.get_full_name() or x.teacher.user.username} moved to {x.target_school.name}.")
        notify_admins(x.target_school, "teacher_transfer_approved", f"Teacher transfer approved: {x.teacher.user.get_full_name() or x.teacher.user.username} is now active in your school.")
        notify_user(x.target_school, x.teacher.user, "teacher_transfer_approved", f"Your teacher transfer to {x.target_school.name} was approved.")
        return Response(_row(x))
