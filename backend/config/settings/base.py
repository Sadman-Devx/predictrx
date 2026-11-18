from datetime import timedelta
from pathlib import Path

import environ
from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BASE_DIR.parent

env = environ.Env()
# .env lives at the repo root (copy .env.example -> .env)
environ.Env.read_env(REPO_ROOT / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-only-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# Admin reskin (django-unfold). If the package is not installed the project falls back to the plain Django admin
# (roadmap cut order: "Admin reskin -> use plain Django admin"); core/admin_base.py handles both cases.
try:
    import unfold  # noqa: F401

    UNFOLD_AVAILABLE = True
except ImportError:
    UNFOLD_AVAILABLE = False

INSTALLED_APPS = [
    *(["unfold"] if UNFOLD_AVAILABLE else []),  # must be listed before django.contrib.admin
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "django_filters",
    "corsheaders",
    # project apps
    "apps.accounts",
    "apps.patients",
    "apps.clinical",
    "apps.drugs",
    "apps.knowledge",
    "apps.analysis",
    "apps.notifications",
    "apps.followups",
    "apps.twin",
    "apps.evaluation",
    "apps.audit",
    "apps.vitals",  # ESP32 ingest — roadmap module
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://predictrx:predictrx@localhost:5432/predictrx",
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "bn"
TIME_ZONE = "Asia/Dhaka"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Prescription images: private storage, never served from a public URL.
MEDIA_ROOT = BASE_DIR / "media"

# ---------- DRF ----------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
    # Two layers: a named scope per sensitive endpoint (ScopedRateThrottle) + a generous per-user/per-IP ceiling
    # (UserRateThrottle: logged-in users are counted by user id, anonymous callers by IP).
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "600/min",  # global ceiling per user / IP
        "login": "5/min",
        "register": "10/hour",
        "password_reset": "5/hour",
        "password_reset_confirm": "10/hour",
        "email_verify": "20/hour",  # submit an emailed verification code
        "email_verify_resend": "5/hour",  # ask for a new verification code
        "password_change": "5/hour",  # logged-in change of password
        "analysis_list": "120/min",  # list of past runs (read only, no LLM)
        "social": "20/min",
        "scan": "20/hour",  # prescription upload (starts a paid vision call)
        "scan_poll": "120/min",  # scan status + image reads (the UI polls)
        "analysis": "30/hour",
        "twin": "60/hour",  # what-if simulation (database only, no LLM)
        "twin_read": "120/min",  # scenario detail + history reads
        "drug_lookup": "120/min",  # resolve + autocomplete (no LLM, cheap)
    },
    # How many reverse proxies sit in front of Django (Cloudflare Tunnel = 1). Needed so throttles and the audit log see
    # the real client IP instead of the proxy's. 0 = trust REMOTE_ADDR only. Never set it higher than the truth:
    # clients could then spoof X-Forwarded-For to dodge the login throttle.
    "NUM_PROXIES": env.int("NUM_PROXIES", default=0),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "PredictRx API",
    "DESCRIPTION": "Decision-support API. Not a diagnosis tool.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# ---------- CORS ----------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:5173"])
CORS_ALLOW_CREDENTIALS = True  # the browser must be allowed to send the refresh cookie
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["http://localhost:5173"])

# ---------- Celery / Redis ----------
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_BEAT_SCHEDULE = {
    "purge-expired-prescription-images": {
        "task": "apps.clinical.tasks.purge_expired_scans",
        "schedule": 60 * 60,  # hourly
    },
    "fail-stuck-prescription-scans": {
        "task": "apps.clinical.tasks.fail_stuck_scans",
        "schedule": 5 * 60,  # every 5 minutes
    },
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# ---------- PredictRx / AI ----------
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
CLOUD_LLM_MODEL = env("CLOUD_LLM_MODEL", default="")
OLLAMA_BASE_URL = env("OLLAMA_BASE_URL", default="http://localhost:11434")
LOCAL_LLM_MODEL = env("LOCAL_LLM_MODEL", default="")
EMBEDDING_DIM = env.int("EMBEDDING_DIM", default=1024)
# Embeddings run on the local Ollama server. The model's output size MUST equal EMBEDDING_DIM.
EMBEDDING_MODEL = env("EMBEDDING_MODEL", default="")
EMBEDDING_BATCH_SIZE = env.int("EMBEDDING_BATCH_SIZE", default=16)
EMBEDDING_TIMEOUT = env.int("EMBEDDING_TIMEOUT", default=120)
# How the contextual-RAG prefix of a chunk is produced: template (deterministic) | local (Ollama) | cloud
RAG_CONTEXT_MODE = env("RAG_CONTEXT_MODE", default="template")
MCP_SERVER_URL = env("MCP_SERVER_URL", default="http://localhost:8001/sse")
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:5173")

# ---------- Email (password reset + family invite) ----------
# Default = print the email in the runserver terminal (no SMTP needed for local work).
# Real sending: set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend and the EMAIL_* values in .env
# (Gmail: smtp.gmail.com / 587 / TLS + a 16-character App Password, see .env.example).
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)  # port 465 instead of TLS/587
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)  # never hang a request on a dead SMTP server
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="PredictRx <no-reply@predictrx.local>")
# How long a reset / invite link works, in seconds (Django's own default would be 3 days).
PASSWORD_RESET_TIMEOUT = env.int("PASSWORD_RESET_TIMEOUT", default=3600)

# ---------- Email verification ----------
# Registration sends a 60-second OTP; True = a doctor/pharmacist cannot log in until verified.
# Admin and invited family accounts are exempt.
REQUIRE_EMAIL_VERIFICATION = env.bool("REQUIRE_EMAIL_VERIFICATION", default=True)
EMAIL_VERIFICATION_TIMEOUT = env.int("EMAIL_VERIFICATION_TIMEOUT", default=48 * 3600)  # legacy signed-link timeout

# ---------- Session cookie ----------
# The refresh token lives in an httpOnly cookie (JavaScript cannot read it), so a page reload keeps the user signed in
# without putting any token in localStorage. The access token (30 min) stays in memory only.
AUTH_REFRESH_COOKIE = env("AUTH_REFRESH_COOKIE", default="predictrx_refresh")
AUTH_REFRESH_COOKIE_SECURE = env.bool("AUTH_REFRESH_COOKIE_SECURE", default=False)  # production.py: True
# Lax is right when the web app and the API share one site (Vite proxy, or one domain). If they are on different
# sites (e.g. two different trycloudflare.com hosts) use None, which REQUIRES the Secure flag (https).
AUTH_REFRESH_COOKIE_SAMESITE = env("AUTH_REFRESH_COOKIE_SAMESITE", default="Lax")
# True = login/refresh also return the refresh token in the JSON body (older API clients, tests).
# production.py turns it off so the token is only ever in the httpOnly cookie.
AUTH_REFRESH_IN_BODY = env.bool("AUTH_REFRESH_IN_BODY", default=True)

# ---------- Social sign-in (empty = that provider is off; the endpoint answers 503 "not enabled") ----------
GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID", default="")
FACEBOOK_APP_ID = env("FACEBOOK_APP_ID", default="")
FACEBOOK_APP_SECRET = env("FACEBOOK_APP_SECRET", default="")
LINKEDIN_CLIENT_ID = env("LINKEDIN_CLIENT_ID", default="")
LINKEDIN_CLIENT_SECRET = env("LINKEDIN_CLIENT_SECRET", default="")
SOCIAL_AUTO_CREATE = env.bool("SOCIAL_AUTO_CREATE", default=True)
OPENFDA_API_KEY = env("OPENFDA_API_KEY", default="")
# Prescription images: deleted at `retain_until`. Short by default; longer only with an active `retain_images` consent.
PRESCRIPTION_IMAGE_RETENTION_DAYS = env.int("PRESCRIPTION_IMAGE_RETENTION_DAYS", default=7)
PRESCRIPTION_IMAGE_RETAINED_DAYS = env.int("PRESCRIPTION_IMAGE_RETAINED_DAYS", default=90)
SCAN_MAX_UPLOAD_BYTES = env.int("SCAN_MAX_UPLOAD_BYTES", default=8 * 1024 * 1024)  # 8 MB per image
SCAN_DEDUPE_WINDOW_SECONDS = env.int("SCAN_DEDUPE_WINDOW_SECONDS", default=600)  # same image twice = one scan
SCAN_STUCK_MINUTES = env.int("SCAN_STUCK_MINUTES", default=10)  # queued/processing longer than this -> failed
DISCLAIMER_VERSION = "v1"

# ---------- Admin skin (django-unfold) ----------
# Palette = design.md primary (#0F5C63). Only read when "unfold" is installed.
UNFOLD = {
    "SITE_TITLE": "PredictRx Admin",
    "SITE_HEADER": "PredictRx",
    "SITE_SUBHEADER": "Decision support - not a diagnosis tool",
    "SITE_SYMBOL": "medication",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "COLORS": {
        "primary": {
            "50": "#EAF6F7", "100": "#D0EBED", "200": "#A5D7DB", "300": "#6FBCC2", "400": "#3C9AA2",
            "500": "#1F7C85", "600": "#0F5C63", "700": "#0D4C52", "800": "#0C3E43", "900": "#0A3236",
            "950": "#051F22",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": "Review",
                "separator": True,
                "items": [
                    {"title": "Brand mappings", "icon": "medication", "link": reverse_lazy("admin:drugs_brandmapping_changelist")},
                    {"title": "Eval cases", "icon": "fact_check", "link": reverse_lazy("admin:evaluation_evalcase_changelist")},
                    {"title": "Eval runs", "icon": "analytics", "link": reverse_lazy("admin:evaluation_evalrun_changelist")},
                ],
            },
            {
                "title": "Patients and consent",
                "separator": True,
                "items": [
                    {"title": "Patients", "icon": "personal_injury", "link": reverse_lazy("admin:patients_patient_changelist")},
                    {"title": "Consents", "icon": "verified_user", "link": reverse_lazy("admin:patients_consent_changelist")},
                    {"title": "Family links", "icon": "family_restroom", "link": reverse_lazy("admin:patients_familylink_changelist")},
                ],
            },
            {
                "title": "Clinical and analysis",
                "separator": True,
                "items": [
                    {"title": "Prescription scans", "icon": "document_scanner", "link": reverse_lazy("admin:clinical_prescriptionscan_changelist")},
                    {"title": "Medications", "icon": "pill", "link": reverse_lazy("admin:clinical_medication_changelist")},
                    {"title": "Analysis runs", "icon": "troubleshoot", "link": reverse_lazy("admin:analysis_analysisrun_changelist")},
                    {"title": "Findings", "icon": "warning", "link": reverse_lazy("admin:analysis_riskfinding_changelist")},
                ],
            },
            {
                "title": "Accounts and audit",
                "separator": True,
                "items": [
                    {"title": "Users", "icon": "person", "link": reverse_lazy("admin:accounts_user_changelist")},
                    {"title": "Audit log", "icon": "history", "link": reverse_lazy("admin:audit_auditlog_changelist")},
                ],
            },
        ],
    },
}