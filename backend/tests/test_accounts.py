import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from tests.conftest import TEST_PASSWORD

REGISTER = "/api/auth/register/"
LOGIN = "/api/auth/login/"
ME = "/api/auth/me/"


def payload(**over):
    base = {"email": "dr.new@example.test", "password": TEST_PASSWORD, "display_name": "Dr New"}
    base.update(over)
    return base


@pytest.mark.django_db
class TestRegister:
    def test_register_creates_doctor_and_never_returns_password(self, api_client):
        r = api_client.post(REGISTER, payload(), format="json")
        assert r.status_code == 201
        body = r.json()
        assert body["email"] == "dr.new@example.test"
        assert body["role"] == "doctor"
        assert body["preferred_language"] == "bn"
        assert "password" not in body
        user = User.objects.get(email="dr.new@example.test")
        assert user.check_password(TEST_PASSWORD) and user.password != TEST_PASSWORD

    def test_pharmacist_can_register(self, api_client):
        r = api_client.post(REGISTER, payload(role="pharmacist"), format="json")
        assert r.status_code == 201 and r.json()["role"] == "pharmacist"

    @pytest.mark.parametrize("role", ["admin", "family", "superuser", ""])
    def test_cannot_self_register_privileged_or_unknown_role(self, api_client, role):
        r = api_client.post(REGISTER, payload(role=role), format="json")
        assert r.status_code == 400
        assert not User.objects.filter(email="dr.new@example.test").exists()

    def test_cannot_set_staff_or_superuser_flags(self, api_client):
        r = api_client.post(REGISTER, payload(is_staff=True, is_superuser=True), format="json")
        assert r.status_code == 201
        user = User.objects.get(email="dr.new@example.test")
        assert not user.is_staff and not user.is_superuser

    def test_email_is_lowercased(self, api_client):
        api_client.post(REGISTER, payload(email="Dr.Mixed@Example.TEST"), format="json")
        assert User.objects.filter(email="dr.mixed@example.test").exists()

    def test_duplicate_email_is_rejected_case_insensitively(self, api_client):
        assert api_client.post(REGISTER, payload(), format="json").status_code == 201
        r = api_client.post(REGISTER, payload(email="DR.NEW@example.test"), format="json")
        assert r.status_code == 400
        assert User.objects.filter(email__iexact="dr.new@example.test").count() == 1

    def test_weak_password_is_rejected_with_error_shape(self, api_client):
        r = api_client.post(REGISTER, payload(password="12345678"), format="json")
        assert r.status_code == 400
        body = r.json()
        assert set(body) == {"error"} and {"code", "message"} <= set(body["error"])

    def test_password_too_similar_to_email_is_rejected(self, api_client):
        # 11 chars, so it passes the length rule: only the similarity validator can reject it.
        r = api_client.post(REGISTER, payload(email="clinicadmin@example.test", password="clinicadmin"), format="json")
        assert r.status_code == 400
        assert "similar" in str(r.json()).lower()

    def test_missing_fields_are_rejected(self, api_client):
        assert api_client.post(REGISTER, {}, format="json").status_code == 400

    def test_invalid_token_header_does_not_break_public_registration(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        assert api_client.post(REGISTER, payload(), format="json").status_code == 201

    def test_registration_is_throttled(self, api_client):
        codes = [api_client.post(REGISTER, payload(email=f"u{i}@example.test"), format="json").status_code
                 for i in range(11)]
        assert codes[:10] == [201] * 10 and codes[10] == 429


@pytest.mark.django_db
class TestLoginAndMe:
    def test_register_login_me_journey(self, api_client):
        api_client.post(REGISTER, payload(), format="json")
        r = api_client.post(LOGIN, {"email": "dr.new@example.test", "password": TEST_PASSWORD}, format="json")
        assert r.status_code == 200 and {"access", "refresh"} <= set(r.json())
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
        me = client.get(ME)
        assert me.status_code == 200 and me.json()["email"] == "dr.new@example.test"

    def test_login_is_case_insensitive_on_email(self, api_client):
        api_client.post(REGISTER, payload(), format="json")
        r = api_client.post(LOGIN, {"email": "  Dr.New@Example.test ", "password": TEST_PASSWORD}, format="json")
        assert r.status_code == 200

    def test_wrong_password_is_401(self, api_client):
        api_client.post(REGISTER, payload(), format="json")
        r = api_client.post(LOGIN, {"email": "dr.new@example.test", "password": "wrong"}, format="json")
        assert r.status_code == 401
        assert "error" in r.json()

    def test_me_requires_authentication(self, api_client):
        assert api_client.get(ME).status_code == 401

    def test_me_patch_updates_profile_but_not_role_or_email(self, doctor, auth_client):
        client = auth_client(doctor)
        r = client.patch(ME, {"display_name": "Dr Rahman", "preferred_language": "en", "role": "admin",
                              "email": "hacker@example.test"}, format="json")
        assert r.status_code == 200
        doctor.refresh_from_db()
        assert doctor.display_name == "Dr Rahman" and doctor.preferred_language == "en"
        assert doctor.role == "doctor" and doctor.email != "hacker@example.test"

    def test_me_rejects_unsupported_language(self, doctor, auth_client):
        assert auth_client(doctor).patch(ME, {"preferred_language": "xx"}, format="json").status_code == 400

    def test_me_put_not_allowed(self, doctor, auth_client):
        assert auth_client(doctor).put(ME, {"display_name": "x", "preferred_language": "bn"},
                                       format="json").status_code == 405