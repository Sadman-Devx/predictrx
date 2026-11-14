"""Social sign-in (Google, Facebook, LinkedIn).

The frontend gets a credential from the provider and sends it here. We NEVER trust the browser's word about
who the user is: every credential is verified server-side against the provider AND checked to have been issued
for OUR app (otherwise a token minted for some other app could log an attacker in as the victim).

  google    -> {"id_token": "..."}                       (Google Identity Services "credential")
  facebook  -> {"access_token": "..."}                   (checked with /debug_token, then /me)
  linkedin  -> {"code": "...", "redirect_uri": "..."}    (authorization-code flow; we exchange it with our secret)

Only stdlib is used for HTTP, so no new dependency is needed.
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from django.conf import settings

from .models import User
from .services import LANGUAGES

log = logging.getLogger(__name__)

PROVIDERS = ("google", "facebook", "linkedin")
HTTP_TIMEOUT = 6


class SocialAuthError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


@dataclass
class Profile:
    email: str
    name: str = ""


def _http_json(url: str, *, headers: dict | None = None, form: dict | None = None) -> dict:
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310 - fixed https URLs
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:  # provider says the credential is bad
        raise SocialAuthError("invalid_credential", "The sign-in credential was rejected.", 401) from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        log.warning("Social provider unreachable: %s", exc)
        raise SocialAuthError("provider_unreachable", "Could not reach the sign-in provider. Try again.", 502) from exc


def _configured(*values: str) -> None:
    if not all(values):
        raise SocialAuthError("provider_not_configured", "This sign-in method is not enabled on the server.", 503)


def _truthy(value) -> bool:
    return value is True or str(value).lower() == "true"


def _google(data: dict) -> Profile:
    client_ids = [c.strip() for c in settings.GOOGLE_CLIENT_ID.split(",") if c.strip()]
    _configured(client_ids and client_ids[0])
    token = data.get("id_token") or ""
    info = _http_json("https://oauth2.googleapis.com/tokeninfo?" + urllib.parse.urlencode({"id_token": token}))
    if info.get("aud") not in client_ids:
        raise SocialAuthError("invalid_credential", "The sign-in credential was not issued for this app.", 401)
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise SocialAuthError("invalid_credential", "Unexpected token issuer.", 401)
    if not info.get("email") or not _truthy(info.get("email_verified")):
        raise SocialAuthError("email_not_verified", "Your Google email address is not verified.", 400)
    return Profile(email=info["email"], name=info.get("name", ""))


def _facebook(data: dict) -> Profile:
    _configured(settings.FACEBOOK_APP_ID, settings.FACEBOOK_APP_SECRET)
    token = data.get("access_token") or ""
    app_token = f"{settings.FACEBOOK_APP_ID}|{settings.FACEBOOK_APP_SECRET}"
    dbg = _http_json("https://graph.facebook.com/debug_token?" +
                     urllib.parse.urlencode({"input_token": token, "access_token": app_token})).get("data", {})
    if not dbg.get("is_valid") or str(dbg.get("app_id")) != str(settings.FACEBOOK_APP_ID):
        raise SocialAuthError("invalid_credential", "The sign-in credential was not issued for this app.", 401)
    me = _http_json("https://graph.facebook.com/me?" +
                    urllib.parse.urlencode({"fields": "id,name,email", "access_token": token}))
    if not me.get("email"):  # user declined the email permission or has no confirmed email
        raise SocialAuthError("email_not_provided", "Facebook did not share an email address.", 400)
    return Profile(email=me["email"], name=me.get("name", ""))


def _linkedin(data: dict) -> Profile:
    _configured(settings.LINKEDIN_CLIENT_ID, settings.LINKEDIN_CLIENT_SECRET)
    if not data.get("code") or not data.get("redirect_uri"):
        raise SocialAuthError("invalid_request", "LinkedIn sign-in needs 'code' and 'redirect_uri'.", 400)
    tok = _http_json("https://www.linkedin.com/oauth/v2/accessToken", form={
        "grant_type": "authorization_code", "code": data["code"], "redirect_uri": data["redirect_uri"],
        "client_id": settings.LINKEDIN_CLIENT_ID, "client_secret": settings.LINKEDIN_CLIENT_SECRET,
    })
    info = _http_json("https://api.linkedin.com/v2/userinfo",
                      headers={"Authorization": f"Bearer {tok.get('access_token', '')}"})
    if not info.get("email") or not _truthy(info.get("email_verified")):
        raise SocialAuthError("email_not_verified", "Your LinkedIn email address is not verified.", 400)
    return Profile(email=info["email"], name=info.get("name", ""))


_VERIFIERS = {"google": _google, "facebook": _facebook, "linkedin": _linkedin}


def login_with_provider(provider: str, data: dict, preferred_language: str = "bn") -> User:
    """Verify the credential and return the matching user (creating a doctor account on first sign-in)."""
    profile = _VERIFIERS[provider](data)
    email = profile.email.strip().lower()
    user = User.objects.filter(email__iexact=email).first()
    if user is not None:
        if not user.is_active:
            raise SocialAuthError("account_disabled", "This account is disabled.", 403)
        if user.role == "admin" or user.is_staff:  # privileged accounts must use a password
            raise SocialAuthError("social_not_allowed", "This account must sign in with a password.", 403)
        return user
    if not settings.SOCIAL_AUTO_CREATE:
        raise SocialAuthError("account_not_found", "No account exists for this email. Please register first.", 403)
    lang = preferred_language if preferred_language in LANGUAGES else "bn"
    return User.objects.create_user(email=email, password=None, role="doctor",  # unusable password
                                    display_name=profile.name[:150], preferred_language=lang)
