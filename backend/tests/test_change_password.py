import secrets

import pytest
from rest_framework.test import APIClient

from tests.conftest import TEST_PASSWORD

URL = "/api/auth/change-password/"
LOGIN = "/api/auth/login/"


@pytest.mark.django_db
class TestChangePassword:
    def test_requires_login(self, api_client):
        r = api_client.post(URL, {"current_password": "x", "new_password": "y"}, format="json")
        assert r.status_code == 401

    def test_changes_the_password(self, api_client, auth_client, doctor):
        new_pw = secrets.token_urlsafe(16)
        r = auth_client(doctor).post(URL, {"current_password": TEST_PASSWORD, "new_password": new_pw}, format="json")
        assert r.status_code == 200
        assert api_client.post(LOGIN, {"email": doctor.email, "password": new_pw}, format="json").status_code == 200
        assert api_client.post(LOGIN, {"email": doctor.email, "password": TEST_PASSWORD}, format="json").status_code == 401

    def test_wrong_current_password_is_rejected(self, auth_client, doctor):
        r = auth_client(doctor).post(
            URL, {"current_password": "not-the-password", "new_password": secrets.token_urlsafe(16)}, format="json"
        )
        assert r.status_code == 400 and "current_password" in r.json()["error"]["details"]
        doctor.refresh_from_db()
        assert doctor.check_password(TEST_PASSWORD)

    def test_weak_password_is_rejected(self, auth_client, doctor):
        weak = "".join(str(d) for d in range(1, 9))
        r = auth_client(doctor).post(URL, {"current_password": TEST_PASSWORD, "new_password": weak}, format="json")
        assert r.status_code == 400 and "new_password" in r.json()["error"]["details"]

    def test_same_password_is_rejected(self, auth_client, doctor):
        r = auth_client(doctor).post(
            URL, {"current_password": TEST_PASSWORD, "new_password": TEST_PASSWORD}, format="json"
        )
        assert r.status_code == 400

    def test_refresh_tokens_are_blacklisted(self, api_client, doctor):
        tokens = api_client.post(LOGIN, {"email": doctor.email, "password": TEST_PASSWORD}, format="json").json()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        r = client.post(URL, {"current_password": TEST_PASSWORD, "new_password": secrets.token_urlsafe(16)}, format="json")
        assert r.status_code == 200
        again = APIClient().post("/api/auth/token/refresh/", {"refresh": tokens["refresh"]}, format="json")
        assert again.status_code == 401
