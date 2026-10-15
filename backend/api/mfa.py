import secrets

from django.contrib.auth.hashers import make_password
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse

from schools.models import MarkAuditLog, SuperadminSecurity
from .totp import new_secret, otpauth_uri, verify


def _guard(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return Response({"detail": "Only a system Superadmin may manage MFA."}, status=403)
    return None


@api_view(["GET"])
@extend_schema(responses={200: OpenApiResponse(description="TOTP setup secret or enabled state."), 403: OpenApiResponse(description="Superadmin authentication required.")})
def mfa_setup(request):
    denied = _guard(request)
    if denied:
        return denied
    security, _ = SuperadminSecurity.objects.get_or_create(user=request.user)
    if security.mfa_enabled:
        return Response({"enabled": True})
    if not security.totp_secret:
        security.totp_secret = new_secret()
        security.save(update_fields=["totp_secret"])
    return Response({"enabled": False, "secret": security.totp_secret,
                     "otpauth_uri": otpauth_uri(security.totp_secret, request.user.username)})


@api_view(["POST"])
@extend_schema(responses={200: OpenApiResponse(description="MFA enabled with one-time recovery codes."), 400: OpenApiResponse(description="Invalid authenticator code.")})
def mfa_confirm(request):
    denied = _guard(request)
    if denied:
        return denied
    code = str(request.data.get("code", ""))
    security, _ = SuperadminSecurity.objects.get_or_create(user=request.user)
    if not security.totp_secret or not verify(security.totp_secret, code):
        return Response({"detail": "Invalid authenticator code."}, status=400)
    recovery_codes = [f"{secrets.token_urlsafe(9)}" for _ in range(8)]
    security.mfa_enabled = True
    security.confirmed_at = timezone.now()
    security.recovery_code_hashes = [make_password(c) for c in recovery_codes]
    security.save(update_fields=["mfa_enabled", "confirmed_at", "recovery_code_hashes"])
    MarkAuditLog.objects.create(school=None, user=request.user, action="mfa_enabled")
    return Response({"enabled": True, "recovery_codes": recovery_codes})


@api_view(["POST"])
@extend_schema(responses={200: OpenApiResponse(description="MFA disabled after valid TOTP verification."), 400: OpenApiResponse(description="Valid authenticator code required."), 409: OpenApiResponse(description="Last active Superadmin must retain MFA.")})
def mfa_disable(request):
    denied = _guard(request)
    if denied:
        return denied
    security = SuperadminSecurity.objects.filter(user=request.user, mfa_enabled=True).first()
    if not security or not verify(security.totp_secret, str(request.data.get("code", ""))):
        return Response({"detail": "Valid authenticator code required."}, status=400)
    if request.user.is_active and request.user.__class__.objects.filter(is_superuser=True, is_active=True).count() <= 1:
        return Response({"detail": "The last active Superadmin must keep MFA enabled."}, status=409)
    security.mfa_enabled = False
    security.recovery_code_hashes = []
    security.save(update_fields=["mfa_enabled", "recovery_code_hashes"])
    MarkAuditLog.objects.create(school=None, user=request.user, action="mfa_disabled")
    return Response({"enabled": False})
