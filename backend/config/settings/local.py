from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]
# Email: base.py reads EMAIL_BACKEND from .env and defaults to the console backend (emails print in this terminal).
# Local dev without Redis for the cache: set DJANGO_LOCMEM_CACHE=1
import os  # noqa: E402

if os.environ.get("DJANGO_LOCMEM_CACHE") == "1":
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
