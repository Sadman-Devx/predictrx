"""The refresh token travels in an httpOnly cookie, scoped to /api/auth/ (the browser sends it to no other endpoint)."""
from django.conf import settings
from rest_framework_simplejwt.settings import api_settings

COOKIE_PATH = "/api/auth/"


def set_refresh_cookie(response, refresh: str) -> None:
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE,
        refresh,
        max_age=int(api_settings.REFRESH_TOKEN_LIFETIME.total_seconds()),
        httponly=True,
        secure=settings.AUTH_REFRESH_COOKIE_SECURE,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
        path=COOKIE_PATH,
    )


def clear_refresh_cookie(response) -> None:
    response.delete_cookie(settings.AUTH_REFRESH_COOKIE, path=COOKIE_PATH, samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE)


def attach_refresh(response, refresh: str | None) -> None:
    """Put the refresh token in the cookie; keep it out of the JSON body unless AUTH_REFRESH_IN_BODY is on."""
    if refresh:
        set_refresh_cookie(response, refresh)
    if not settings.AUTH_REFRESH_IN_BODY and isinstance(response.data, dict):
        response.data.pop("refresh", None)
