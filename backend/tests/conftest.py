import secrets

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User

# Generated fresh on every test run: no credential literal lives in the repo (keeps secret scanners quiet,
# and nobody can mistake it for a real password). 22 random chars pass every Django password validator.
TEST_PASSWORD = secrets.token_urlsafe(16)


@pytest.fixture(autouse=True)
def _test_settings(settings):
    """Tests never need Redis, and must not pay for slow password hashing."""
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    from django.core.cache import cache

    cache.clear()  # throttle counters live in the cache; isolate every test
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def make_user(db):
    counter = {"n": 0}

    def _make(role="doctor", email=None, **extra):
        counter["n"] += 1
        return User.objects.create_user(
            email=email or f"{role}{counter['n']}@example.test", password=TEST_PASSWORD, role=role, **extra
        )

    return _make


@pytest.fixture
def auth_client(api_client):
    """auth_client(user) -> an APIClient authenticated as that user."""

    def _auth(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return _auth


@pytest.fixture
def doctor(make_user):
    return make_user("doctor")


@pytest.fixture
def other_doctor(make_user):
    return make_user("doctor")