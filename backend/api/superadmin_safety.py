from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse

from schools.models import MarkAuditLog, SuperadminSecurity
from .admin_throttle import AdminAccountThrottle
from .totp import verify

User = get_user_model()
NO = "Only a system Superadmin may manage Superadmin accounts."


def _guard(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return Response({"detail": NO}, status=403)
    return None


@api_view(["GET"])
@extend_schema(responses={200: OpenApiResponse(description="Superadmin account list."), 403: OpenApiResponse(description="Superadmin authentication required.")})
def superadmin_list(request):
    denied = _guard(request)
    if denied:
        return denied
    return Response({"results": [
        {"id": u.id, "username": u.username, "email": u.email, "is_active": u.is_active}
        for u in User.objects.filter(is_superuser=True).order_by("username")
    ]})


@api_view(["PATCH"])
@throttle_classes([AdminAccountThrottle])
@extend_schema(responses={200: OpenApiResponse(description="Superadmin status changed."), 403: OpenApiResponse(description="MFA or Superadmin authorization required."), 409: OpenApiResponse(description="Last active Superadmin cannot be disabled.")})
def superadmin_status(request, pk):
    denied = _guard(request)
    if denied:
        return denied
    security = SuperadminSecurity.objects.filter(user=request.user, mfa_enabled=True).first()
    if not security or not verify(security.totp_secret, str(request.data.get("mfa_code", ""))):
        return Response({"detail": "Enroll MFA and provide a valid authenticator code before changing Superadmin accounts."}, status=403)
    target = User.objects.filter(pk=pk, is_superuser=True).first()
    if target is None:
        return Response({"detail": "Superadmin not found."}, status=404)
    flag = request.data.get("is_active")
    if not isinstance(flag, bool):
        return Response({"detail": "is_active must be true or false."}, status=400)
    if not flag and target.pk == request.user.pk:
        return Response({"detail": "You cannot deactivate your own Superadmin account."}, status=400)
    with transaction.atomic():
        list(User.objects.select_for_update().filter(is_superuser=True).order_by("pk").values_list("pk", flat=True))
        if not flag and target.is_active and User.objects.filter(is_superuser=True, is_active=True).count() <= 1:
            return Response({"detail": "The last active Superadmin cannot be deactivated."}, status=409)
        target.is_active = flag
        target.save(update_fields=["is_active"])
        MarkAuditLog.objects.create(
            school=None, user=request.user,
            action="superadmin_activated" if flag else "superadmin_deactivated",
            details={"target_user_id": target.pk, "target_username": target.username},
        )
    return Response({"id": target.id, "username": target.username, "is_active": target.is_active})
