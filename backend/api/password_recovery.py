import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .password_throttle import PasswordRateThrottle
from .session_cleanup import end_other_sessions
from schools.models import GuardianProfile, MarkAuditLog, SchoolAdminProfile, StaffProfile, TeacherProfile

User = get_user_model()
log = logging.getLogger(__name__)
BAD = "This recovery link is invalid or expired."


def _school_id(user):
    for model in (SchoolAdminProfile, TeacherProfile, StaffProfile, GuardianProfile):
        profile = model.objects.filter(user=user).first()
        if profile:
            return profile.school_id
    return None


def _audit(user, action):
    MarkAuditLog.objects.create(school_id=_school_id(user), user=user, action=action)


def _notify_password_changed(user):
    if user.email:
        send_mail(
            "Your Marian password was changed",
            "Your Marian account password was changed successfully. If you did not make this change, contact your school administrator or platform owner immediately.",
            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@marian.local"),
            [user.email], fail_silently=True,
        )


def _generic():
    return Response({"detail": "If an eligible account exists, recovery instructions may be sent to its verified email address."})


def _data(request):
    return request.data if hasattr(request.data, "get") else {}


def _find_user(identifier):
    """Exactly one active match, or None. Shared emails are never guessed."""
    if "@" in identifier:
        users = list(User.objects.filter(email__iexact=identifier, is_active=True)[:2])
        if len(users) > 1:
            return None
        if users:
            return users[0]
    users = list(User.objects.filter(username__iexact=identifier, is_active=True)[:2])
    return users[0] if len(users) == 1 else None


def _deliverable(user):
    try:
        validate_email(user.email or "")
        return True
    except ValidationError:
        return False


def _cooling_down(user):
    seconds = getattr(settings, "PASSWORD_RESET_COOLDOWN_SECONDS", 60)
    if seconds <= 0:
        return False
    return not cache.add(f"pwreset-cooldown:{user.pk}", 1, seconds)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PasswordRateThrottle])
def password_reset_request(request):
    identifier = str(_data(request).get("identifier", "")).strip()[:254]
    if not identifier:
        return _generic()
    user = _find_user(identifier)
    if user is None or not _deliverable(user) or _cooling_down(user):
        return _generic()
    _audit(user, "password_recovery_requested")
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    base = getattr(settings, "FRONTEND_URL", "http://localhost:5173").rstrip("/")
    link = f"{base}/?recovery=1&uid={uid}&token={token}"
    try:
        send_mail(
            "Marian account recovery",
            f"Use this secure link to set a new Marian password:\n\n{link}\n\nIf you did not request this, ignore this message.",
            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@marian.local"),
            [user.email], fail_silently=False,
        )
    except Exception as exc:
        log.warning("Recovery email failed for user id %s (%s)", user.pk, type(exc).__name__)
    return _generic()


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PasswordRateThrottle])
def password_reset_confirm(request):
    data = _data(request)
    uid_value, token, new_password = str(data.get("uid", "")), str(data.get("token", "")), str(data.get("new_password", ""))
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid_value)), is_active=True)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response({"detail": BAD}, status=400)
    if not token or not default_token_generator.check_token(user, token):
        return Response({"detail": BAD}, status=400)
    try:
        validate_password(new_password, user)
    except ValidationError as e:
        return Response({"detail": " ".join(e.messages)}, status=400)
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        if not locked.is_active or not default_token_generator.check_token(locked, token):
            return Response({"detail": BAD}, status=400)
        locked.set_password(new_password)
        locked.save(update_fields=["password"])
        end_other_sessions(locked)
        _audit(locked, "password_recovery_completed")
        _notify_password_changed(locked)
    return Response({"detail": "Password reset successfully. You can now sign in."})
