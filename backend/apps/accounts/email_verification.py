"""Email verification: a signed, time-limited link sent after registration.

The token is signed with the server secret and carries the user id AND the email it was issued for, so a link
stops working if the address changes. Opening it twice is harmless (it only sets a flag).
Nothing here ever raises into a request: an SMTP outage must not break registration.
"""
import logging
from urllib.parse import quote

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail

from .models import User

log = logging.getLogger(__name__)

SALT = "predictrx.email-verification"

_TEXT = {
    "en": (
        "Verify your PredictRx email",
        "Hello{name},\n\nPlease confirm your email address with this link (valid for {hours} hours):\n{link}\n\n"
        "If you did not create a PredictRx account, you can ignore this email.",
    ),
    "bn": (
        "আপনার PredictRx ইমেইল যাচাই করুন",
        "হ্যালো{name},\n\nএই লিংকে গিয়ে আপনার ইমেইল ঠিকানা নিশ্চিত করুন ({hours} ঘণ্টা পর্যন্ত কার্যকর):\n{link}\n\n"
        "আপনি PredictRx-এ অ্যাকাউন্ট না খুলে থাকলে এই ইমেইল উপেক্ষা করুন।",
    ),
}


def make_token(user: User) -> str:
    return signing.dumps({"u": user.pk, "e": user.email}, salt=SALT)


def build_link(user: User) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/verify-email?token={quote(make_token(user), safe='')}"


def send_verification_email(user: User) -> bool:
    """Email the link. Returns True if a mail was handed to the mail backend. Never raises."""
    lang = user.preferred_language if user.preferred_language in _TEXT else "en"
    subject, body = _TEXT[lang]
    name = f" {user.display_name}" if user.display_name else ""
    hours = max(1, settings.EMAIL_VERIFICATION_TIMEOUT // 3600)
    try:
        send_mail(subject, body.format(name=name, hours=hours, link=build_link(user)),
                  settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
    except Exception:  # noqa: BLE001 - the user can ask for a new link; the failure is logged
        log.exception("Could not send verification email")
        return False
    return True


def user_from_token(token: str) -> User | None:
    try:
        data = signing.loads(token, salt=SALT, max_age=settings.EMAIL_VERIFICATION_TIMEOUT)
        return User.objects.filter(pk=data["u"], email=data["e"], is_active=True).first()
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        return None


def mark_verified(user: User) -> None:
    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=["email_verified"])


def resend(email: str) -> bool:
    """Send a new link to an active, still unverified account. Returns True if a mail was sent."""
    user = User.objects.filter(email__iexact=email.strip(), is_active=True, email_verified=False).first()
    return bool(user) and send_verification_email(user)
