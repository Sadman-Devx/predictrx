from .base import *  # noqa: F401,F403
import environ

DEBUG = False
SECURE_SSL_REDIRECT = False  # TLS is terminated by the tunnel / proxy
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

_env = environ.Env()
_sentry = _env("SENTRY_DSN", default="")
if _sentry:
    import sentry_sdk

    sentry_sdk.init(dsn=_sentry, traces_sample_rate=0.1, send_default_pii=False)
