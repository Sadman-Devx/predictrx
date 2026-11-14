"""Forgot-password flow: request a reset link by email, then set a new password with the link's uid + token.

Security notes
- The request endpoint never reveals whether an email has an account (always the same 202 answer).
- Tokens come from Django's default_token_generator: signed, one-time (they stop working as soon as the
  password changes) and they expire after settings.PASSWORD_RESET_TIMEOUT seconds.
- After a successful reset every outstanding JWT refresh token of the user is blacklisted, so a stolen
  session cannot outlive the password change.
"""
import logging

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import User

log = logging.getLogger(__name__)

_EMAIL_TEXT = {
    "en": (
        "PredictRx password reset",
        "Hello{name},\n\nUse this link to choose a new password (valid for {minutes} minutes):\n{link}\n\n"
        "If you did not ask for this, you can ignore this email. Your password will not change.",
    ),
    "bn": (
        "PredictRx পাসওয়ার্ড রিসেট",
        "হ্যালো{name},\n\nনতুন পাসওয়ার্ড দিতে এই লিংকে যান ({minutes} মিনিট পর্যন্ত কার্যকর):\n{link}\n\n"
        "আপনি এটি চেয়ে না থাকলে এই ইমেইল উপেক্ষা করুন। আপনার পাসওয়ার্ড বদলাবে না।",
    ),
}


def make_uid(user: User) -> str:
    return urlsafe_base64_encode(force_bytes(user.pk))


def build_reset_link(user: User) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/reset-password?uid={make_uid(user)}&token={default_token_generator.make_token(user)}"


def send_reset_email(email: str) -> bool:
    """Email a reset link if an active account exists. Returns True if a mail was sent. Never raises."""
    user = User.objects.filter(email__iexact=email.strip(), is_active=True).first()
    if user is None:
        return False
    lang = user.preferred_language if user.preferred_language in _EMAIL_TEXT else "en"
    subject, body = _EMAIL_TEXT[lang]
    name = f" {user.display_name}" if user.display_name else ""
    minutes = max(1, settings.PASSWORD_RESET_TIMEOUT // 60)
    try:
        send_mail(subject, body.format(name=name, minutes=minutes, link=build_reset_link(user)),
                  settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
    except Exception:  # noqa: BLE001 - SMTP down must not change the (anti-enumeration) response
        log.exception("Could not send password reset email")
        return False
    return True


def user_from_uid(uidb64: str) -> User | None:
    try:
        pk = force_str(urlsafe_base64_decode(uidb64))
        return User.objects.get(pk=pk, is_active=True)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist, UnicodeDecodeError):
        return None


def check_reset_token(uidb64: str, token: str) -> User | None:
    user = user_from_uid(uidb64)
    if user is not None and default_token_generator.check_token(user, token):
        return user
    return None


def validate_new_password(user: User, password: str) -> list[str]:
    """Django's password validators (length, common, numeric, similarity to the user's own attributes)."""
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        return list(exc.messages)
    return []


def set_new_password(user: User, password: str) -> None:
    user.set_password(password)
    user.save(update_fields=["password"])
    for outstanding in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=outstanding)
