from .base import *  # noqa: F401,F403
import environ

DEBUG = False
SECURE_SSL_REDIRECT = False  # TLS is terminated by the tunnel / proxy
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

_env = environ.Env()

# Fail fast on an unsafe deploy instead of running with the dev key.
if SECRET_KEY == "dev-only-change-me":  # noqa: F405
    raise RuntimeError("Set DJANGO_SECRET_KEY in the environment before running with config.settings.production")
if EMAIL_BACKEND.endswith("console.EmailBackend"):  # noqa: F405
    import logging

    logging.getLogger(__name__).warning(
        "EMAIL_BACKEND is the console backend: password-reset and invite emails are printed, not sent."
    )

# Session cookie: https only, and the refresh token is kept out of JSON responses.
AUTH_REFRESH_COOKIE_SECURE = _env.bool("AUTH_REFRESH_COOKIE_SECURE", default=True)
AUTH_REFRESH_IN_BODY = _env.bool("AUTH_REFRESH_IN_BODY", default=False)

# Behind the Cloudflare Tunnel there is exactly one proxy. Without this every visitor shares the tunnel's IP, so the
# 5/min login throttle would be one bucket for the whole internet. Set NUM_PROXIES=0 if you run without a proxy.
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": _env.int("NUM_PROXIES", default=1)}  # noqa: F405

_sentry = _env("SENTRY_DSN", default="")
if _sentry:
    import sentry_sdk

    sentry_sdk.init(dsn=_sentry, traces_sample_rate=0.1, send_default_pii=False)