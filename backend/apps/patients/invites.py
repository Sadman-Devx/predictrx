"""Invitation e-mail for a newly created family account.

The mail carries NO patient information (not even a patient code): an e-mail is not a private channel. It only tells
the person that a clinician invited them and gives a one-time link to choose a password. The link has the same shape
and token rules as the password-reset link (<FRONTEND_URL>/reset-password?uid=..&token=..), so the frontend's existing
reset page completes the invite; it expires after settings.PASSWORD_RESET_TIMEOUT, after which "Forgot password" works.
"""
import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail

from apps.accounts import password_reset

logger = logging.getLogger(__name__)

_TEXT = {
    "en": (
        "You were invited to PredictRx",
        "Hello{name},\n\nA clinician has invited you to view a family summary on PredictRx. "
        "Use this link to choose your password and sign in (valid for {minutes} minutes):\n{link}\n\n"
        "If you were not expecting this, you can ignore this email.",
    ),
    "bn": (
        "PredictRx-এ আপনাকে আমন্ত্রণ জানানো হয়েছে",
        "হ্যালো{name},\n\nএকজন চিকিৎসক আপনাকে PredictRx-এ একটি পারিবারিক সারসংক্ষেপ দেখার জন্য আমন্ত্রণ জানিয়েছেন। "
        "পাসওয়ার্ড ঠিক করে সাইন ইন করতে এই লিংকে যান ({minutes} মিনিট পর্যন্ত কার্যকর):\n{link}\n\n"
        "আপনি এটি আশা না করে থাকলে এই ইমেইল উপেক্ষা করুন।",
    ),
}


def build_invite_link(user) -> str:
    base = getattr(settings, "FRONTEND_URL", "http://localhost:5173").rstrip("/")
    return f"{base}/reset-password?uid={password_reset.make_uid(user)}&token={default_token_generator.make_token(user)}"


def send_family_invite(user) -> bool:
    """E-mail the invitation. Returns True if a mail was handed to the mail backend. Never raises: an SMTP outage must
    not undo a link that was already committed (the invitee can use "Forgot password" instead)."""
    lang = user.preferred_language if user.preferred_language in _TEXT else "en"
    subject, body = _TEXT[lang]
    name = f" {user.display_name}" if user.display_name else ""
    minutes = max(1, settings.PASSWORD_RESET_TIMEOUT // 60)
    try:
        send_mail(
            subject,
            body.format(name=name, minutes=minutes, link=build_invite_link(user)),
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    except Exception:  # noqa: BLE001 - mail failure is logged (without the address) and reported as False
        logger.exception("Could not send family invitation email")
        return False
    return True