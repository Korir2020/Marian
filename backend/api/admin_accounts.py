from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response

from schools.models import MarkAuditLog, SchoolAdminProfile
from .admin_throttle import AdminAccountThrottle
from .session_cleanup import end_other_sessions

User = get_user_model()
NO = "You are not allowed to do that."


def _row(p):
    return {"id": p.id, "username": p.user.username, "school": p.school.name,
            "is_deputy": p.is_deputy, "is_active": p.user.is_active}


def _active_admins(school_id):
    return SchoolAdminProfile.objects.filter(school_id=school_id, user__is_active=True)


def _data(request):
    return request.data if hasattr(request.data, "get") else {}


def _scope(request):
    """(is_root, caller_profile, denied_response). Deputies and non-admins are denied."""
    if request.user.is_superuser:
        return True, None, None
    me = SchoolAdminProfile.objects.filter(user=request.user).first()
    if me is None or me.is_deputy:
        return False, me, Response({"detail": NO}, status=403)
    return False, me, None


def _target(root, me, pk):
    """Other schools' accounts do not exist for a school admin (404)."""
    qs = SchoolAdminProfile.objects.select_related("user", "school")
    if not root:
        qs = qs.filter(school_id=me.school_id)
    return qs.filter(pk=pk).first()


def _privileged(target):
    return target.user.is_superuser or target.user.is_staff


@api_view(["GET"])
def admin_account_list(request):
    if not request.user.is_superuser:
        return Response({"detail": "Only a superuser can list administrators."}, status=403)
    rows = SchoolAdminProfile.objects.select_related("user", "school").order_by("school__name", "id")
    return Response({"results": [_row(p) for p in rows]})


@api_view(["POST"])
@throttle_classes([AdminAccountThrottle])
def admin_reset_password(request, pk):
    root, me, denied = _scope(request)
    if denied:
        return denied
    t = _target(root, me, pk)
    if t is None:
        return Response({"detail": "Not found."}, status=404)
    if not root and (not t.is_deputy or _privileged(t)):
        return Response({"detail": NO}, status=403)
    pw = str(_data(request).get("password", ""))
    try:
        validate_password(pw, t.user)
    except ValidationError as e:
        return Response({"detail": " ".join(e.messages)}, status=400)
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=t.user_id)
        user.set_password(pw)
        user.save(update_fields=["password"])
        end_other_sessions(user)
        MarkAuditLog.objects.create(
            school_id=t.school_id, user=request.user, action="admin_password_reset",
            details={"account": user.username})
    return Response({"detail": "Password reset."})


@api_view(["PATCH"])
@throttle_classes([AdminAccountThrottle])
def admin_status(request, pk):
    root, me, denied = _scope(request)
    if denied:
        return denied
    target = _target(root, me, pk)
    if target is None:
        return Response({"detail": "Not found."}, status=404)
    if not root:
        if target.user_id == request.user.id:
            return Response({"detail": "You cannot deactivate your own administrator account."}, status=400)
        if not target.is_deputy or _privileged(target):
            return Response({"detail": "Only deputy administrator accounts can be managed by a school administrator."}, status=403)
    flag = _data(request).get("is_active")
    if not isinstance(flag, bool):
        return Response({"detail": "is_active must be true or false."}, status=400)
    if not flag and target.user_id == request.user.id:
        return Response({"detail": "You cannot deactivate your own administrator account."}, status=400)
    with transaction.atomic():
        # Lock the school's admin rows first (same order every time) so two
        # simultaneous deactivations cannot both pass the last-admin check.
        list(SchoolAdminProfile.objects.select_for_update()
             .filter(school_id=target.school_id).order_by("pk").values_list("pk", flat=True))
        user = User.objects.select_for_update().get(pk=target.user_id)
        if not flag and user.is_active:
            others = _active_admins(target.school_id).exclude(pk=target.pk)
            if not target.is_deputy:
                others = others.filter(is_deputy=False)
            if not others.exists():
                return Response({"detail": "The last active school administrator cannot be deactivated."}, status=409)
        user.is_active = flag
        user.save(update_fields=["is_active"])
        if not flag:
            end_other_sessions(user)
        MarkAuditLog.objects.create(
            school_id=target.school_id, user=request.user,
            action="admin_activated" if flag else "admin_deactivated",
            details={"account": user.username})
    target.user = user
    return Response(_row(target))
