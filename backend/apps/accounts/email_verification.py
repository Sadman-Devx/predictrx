"""Email verification codes and legacy signed links.

Codes are stored as keyed digests, expire quickly, and are invalidated after use or too many guesses. Existing signed
links remain valid until their original timeout. A mail outage is logged and exposed to registration callers.
"""
import logging
import secrets
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import User

log = logging.getLogger(__name__)

SALT = "predictrx.email-verification"
OTP_TTL_SECONDS = 60
MAX_OTP_ATTEMPTS = 5

_TEXT = {
    "en": (
        "Your PredictRx verification code",
        "Hello{name},\n\nYour email verification code is {code}. It is valid for {seconds} seconds.\n\n"
        "If you did not create a PredictRx account, you can ignore this email.",
    ),
    "bn": (
        "আপনার PredictRx যাচাইকরণ কোড",
        "হ্যালো{name},\n\nআপনার ইমেইল যাচাইকরণ কোড: {code}। এটি {seconds} সেকেন্ড পর্যন্ত কার্যকর থাকবে।\n\n"
        "আপনি PredictRx-এ অ্যাকাউন্ট না খুলে থাকলে এই ইমেইল উপেক্ষা করুন।",
    ),
}


def make_token(user: User) -> str:
    return signing.dumps({"u": user.pk, "e": user.email}, salt=SALT)


def build_link(user: User) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/verify-email?token={quote(make_token(user), safe='')}"


def _otp_digest(user: User, code: str) -> str:
    value = f"{user.pk}:{user.email}:{code}"
    return salted_hmac(SALT, value, secret=settings.SECRET_KEY, algorithm="sha256").hexdigest()


def _clear_otp(user: User) -> None:
    user.email_otp_hash = ""
    user.email_otp_expires_at = None
    user.email_otp_attempts = 0


def send_verification_code(user: User) -> bool:
    """Email a six-digit code. Returns whether the configured mail backend accepted it."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    user.email_otp_hash = _otp_digest(user, code)
    user.email_otp_expires_at = timezone.now() + timedelta(seconds=OTP_TTL_SECONDS)
    user.email_otp_attempts = 0
    user.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_attempts"])

    lang = user.preferred_language if user.preferred_language in _TEXT else "en"
    subject, body = _TEXT[lang]
    name = f" {user.display_name}" if user.display_name else ""
    try:
        sent = send_mail(
            subject,
            body.format(name=name, code=code, seconds=OTP_TTL_SECONDS),
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    except Exception:  # noqa: BLE001 - the user can ask for a new code; the failure is logged
        log.exception("Could not send verification code")
        _clear_otp(user)
        user.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_attempts"])
        return False
    if not sent:
        log.error("Mail backend did not accept verification code for user id %s", user.pk)
        _clear_otp(user)
        user.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_attempts"])
        return False
    return True


def user_from_token(token: str) -> User | None:
    try:
        data = signing.loads(token, salt=SALT, max_age=settings.EMAIL_VERIFICATION_TIMEOUT)
        return User.objects.filter(pk=data["u"], email=data["e"], is_active=True).first()
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        return None


def mark_verified(user: User) -> None:
    user.email_verified = True
    _clear_otp(user)
    user.save(update_fields=["email_verified", "email_otp_hash", "email_otp_expires_at", "email_otp_attempts"])


def resend(email: str) -> bool:
    """Send a fresh code to an active, still unverified account."""
    user = User.objects.filter(email__iexact=email.strip(), is_active=True, email_verified=False).first()
    return bool(user) and send_verification_code(user)


def verify_code(email: str, code: str) -> User | None:
    """Consume a matching, unexpired OTP; reject after a bounded number of guesses."""
    with transaction.atomic():
        user = (
            User.objects.select_for_update()
            .filter(email__iexact=email.strip(), is_active=True, email_verified=False)
            .first()
        )
        if user is None:
            return None
        now = timezone.now()
        if not user.email_otp_hash or not user.email_otp_expires_at or now >= user.email_otp_expires_at:
            _clear_otp(user)
            user.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_attempts"])
            return None
        if user.email_otp_attempts >= MAX_OTP_ATTEMPTS:
            _clear_otp(user)
            user.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_attempts"])
            return None
        if not constant_time_compare(user.email_otp_hash, _otp_digest(user, code)):
            user.email_otp_attempts += 1
            if user.email_otp_attempts >= MAX_OTP_ATTEMPTS:
                _clear_otp(user)
            user.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_attempts"])
            return None
        user.email_verified = True
        _clear_otp(user)
        user.save(update_fields=["email_verified", "email_otp_hash", "email_otp_expires_at", "email_otp_attempts"])
        return user
