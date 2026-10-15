from django.contrib.auth.password_validation import validate_password
from django.conf import settings
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response

from .password_throttle import PasswordRateThrottle
from .session_cleanup import end_other_sessions
from schools.models import GuardianProfile, MarkAuditLog, SchoolAdminProfile, StaffProfile, TeacherProfile


def _school_id(user):
    for model in (SchoolAdminProfile, TeacherProfile, StaffProfile, GuardianProfile):
        profile = model.objects.filter(user=user).first()
        if profile:
            return profile.school_id
    return None


@api_view(["POST"])
@throttle_classes([PasswordRateThrottle])
def change_password(request):
    """Let the logged-in user change their own password."""
    old = request.data.get("old_password") or ""
    new = request.data.get("new_password") or ""
    user = request.user
    if not user.check_password(old):
        return Response({"detail": "Current password is wrong."}, status=400)
    if new == old:
        return Response({"detail": "New password must be different."}, status=400)
    try:
        validate_password(new, user)
    except ValidationError as e:
        return Response({"detail": " ".join(e.messages)}, status=400)
    user.set_password(new)
    user.save()
    end_other_sessions(user, request.data.get("refresh")
        or request.COOKIES.get("marian_rt"))
    MarkAuditLog.objects.create(school_id=_school_id(user), user=user, action="password_changed")
    if user.email:
        send_mail(
            "Your Marian password was changed",
            "Your Marian account password was changed successfully. If you did not make this change, contact your school administrator or platform owner immediately.",
            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@marian.local"),
            [user.email], fail_silently=True,
        )
    return Response({"detail": "Password changed."})
