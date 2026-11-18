import re
import secrets
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import unquote

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts import email_verification
from apps.accounts.models import User
from tests.conftest import TEST_PASSWORD

REGISTER = "/api/auth/register/"
VERIFY = "/api/auth/verify-email/"
RESEND = "/api/auth/resend-verification/"
LOGIN = "/api/auth/login/"
RESET = "/api/auth/password-reset/"
RESET_CONFIRM = "/api/auth/password-reset/confirm/"
PW = secrets.token_urlsafe(16)


def _register(client, email="new.doc@example.test"):
    return client.post(REGISTER, {"email": email, "password": PW, "display_name": "Dr New"}, format="json")


def _code(message=None):
    body = message.body if message is not None else mail.outbox[-1].body
    codes = re.findall(r"\b\d{6}\b", body)
    assert len(codes) == 1, body
    return codes[0]


def _verify(client, email="new.doc@example.test", code=None):
    return client.post(VERIFY, {"email": email, "code": code or _code()}, format="json")


@pytest.mark.django_db
class TestVerification:
    def test_register_sends_an_otp_and_starts_unverified(self, api_client):
        response = _register(api_client)
        assert response.status_code == 201
        assert response.json()["email_verified"] is False
        assert response.json()["verification_email_sent"] is True
        assert len(mail.outbox) == 1 and mail.outbox[0].to == ["new.doc@example.test"]
        assert "60" in mail.outbox[0].body

    def test_otp_verifies_the_account_once(self, api_client):
        _register(api_client)
        code = _code()
        assert _verify(api_client, code=code).status_code == 200
        assert User.objects.get(email="new.doc@example.test").email_verified is True
        assert _verify(api_client, code=code).status_code == 400

    def test_bad_or_missing_code_is_rejected(self, api_client):
        assert api_client.post(VERIFY, {"email": "new.doc@example.test", "code": "000000"},
                               format="json").status_code == 400
        assert api_client.post(VERIFY, {}, format="json").status_code == 400
        assert api_client.post(VERIFY, {"email": "new.doc@example.test", "code": "12x"},
                               format="json").status_code == 400

    def test_expired_code_is_rejected(self, api_client):
        _register(api_client)
        user = User.objects.get(email="new.doc@example.test")
        user.email_otp_expires_at = timezone.now() - timedelta(seconds=1)
        user.save(update_fields=["email_otp_expires_at"])
        assert _verify(api_client).status_code == 400

    def test_code_expires_at_the_60_second_boundary(self, api_client, monkeypatch):
        issued_at = timezone.now()
        monkeypatch.setattr(email_verification, "timezone", SimpleNamespace(now=lambda: issued_at))
        _register(api_client)
        user = User.objects.get(email="new.doc@example.test")
        expires_at = issued_at + timedelta(seconds=60)
        assert user.email_otp_expires_at == expires_at
        monkeypatch.setattr(email_verification, "timezone", SimpleNamespace(now=lambda: expires_at))
        assert _verify(api_client).status_code == 400

    def test_too_many_guesses_invalidate_the_code(self, api_client):
        _register(api_client)
        valid_code = _code()
        invalid_code = "000000" if valid_code != "000000" else "000001"
        for _ in range(email_verification.MAX_OTP_ATTEMPTS):
            assert _verify(api_client, code=invalid_code).status_code == 400
        assert _verify(api_client, code=valid_code).status_code == 400

    def test_resend_invalidates_the_previous_code(self, api_client):
        _register(api_client)
        first_code = _code()
        mail.outbox.clear()
        assert api_client.post(RESEND, {"email": "new.doc@example.test"}, format="json").status_code == 202
        second_code = _code()
        assert first_code != second_code
        assert _verify(api_client, code=first_code).status_code == 400
        assert _verify(api_client, code=second_code).status_code == 200

    def test_legacy_signed_link_still_verifies(self, api_client):
        _register(api_client)
        user = User.objects.get(email="new.doc@example.test")
        token = email_verification.make_token(user)
        assert api_client.post(VERIFY, {"token": token}, format="json").status_code == 200

    def test_expired_legacy_link_is_rejected(self, api_client, settings):
        _register(api_client)
        user = User.objects.get(email="new.doc@example.test")
        token = email_verification.make_token(user)
        settings.EMAIL_VERIFICATION_TIMEOUT = -1
        assert api_client.post(VERIFY, {"token": token}, format="json").status_code == 400

    def test_legacy_link_dies_when_the_email_changes(self, api_client):
        _register(api_client)
        user = User.objects.get(email="new.doc@example.test")
        token = email_verification.make_token(user)
        User.objects.filter(pk=user.pk).update(email="other.address@example.test")
        assert api_client.post(VERIFY, {"token": token}, format="json").status_code == 400


@pytest.mark.django_db
class TestLoginGate:
    def test_login_is_blocked_until_verified_when_required(self, api_client, settings):
        settings.REQUIRE_EMAIL_VERIFICATION = True
        _register(api_client)
        credentials = {"email": "new.doc@example.test", "password": PW}
        blocked = api_client.post(LOGIN, credentials, format="json")
        assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "email_not_verified"
        _verify(api_client)
        assert api_client.post(LOGIN, credentials, format="json").status_code == 200

    def test_wrong_password_still_looks_like_a_normal_failure(self, api_client, settings):
        settings.REQUIRE_EMAIL_VERIFICATION = True
        _register(api_client)
        response = api_client.post(
            LOGIN, {"email": "new.doc@example.test", "password": "wrong-password-1"}, format="json"
        )
        assert response.status_code == 401

    def test_family_and_admin_are_exempt(self, api_client, make_user, settings):
        settings.REQUIRE_EMAIL_VERIFICATION = True
        for role in ("family", "admin"):
            user = make_user(role)
            response = api_client.post(
                LOGIN, {"email": user.email, "password": TEST_PASSWORD}, format="json"
            )
            assert response.status_code == 200, role

    def test_reset_link_counts_as_proof_of_the_mailbox(self, api_client, make_user, settings):
        settings.REQUIRE_EMAIL_VERIFICATION = True
        user = make_user("doctor", email="dr.reset@example.test")
        api_client.post(RESET, {"email": user.email}, format="json")
        match = re.search(r"uid=([^&\s]+)&token=([^\s]+)", mail.outbox[-1].body)
        new_password = secrets.token_urlsafe(16)
        response = api_client.post(
            RESET_CONFIRM,
            {"uid": match.group(1), "token": match.group(2), "password": new_password},
            format="json",
        )
        assert response.status_code == 200
        assert api_client.post(
            LOGIN, {"email": user.email, "password": new_password}, format="json"
        ).status_code == 200


@pytest.mark.django_db
class TestResend:
    def test_unverified_account_gets_a_new_code(self, api_client):
        _register(api_client)
        mail.outbox.clear()
        response = api_client.post(RESEND, {"email": "NEW.doc@example.test"}, format="json")
        assert response.status_code == 202
        assert len(mail.outbox) == 1 and mail.outbox[0].to == ["new.doc@example.test"]
        assert len(_code()) == 6

    def test_unknown_and_verified_accounts_get_the_same_answer_and_no_mail(self, api_client, make_user):
        verified = make_user("doctor", email="ok@example.test", email_verified=True)
        first = api_client.post(RESEND, {"email": verified.email}, format="json")
        second = api_client.post(RESEND, {"email": "nobody@example.test"}, format="json")
        assert first.status_code == second.status_code == 202 and first.json() == second.json()
        assert mail.outbox == []

    def test_resend_is_throttled(self, api_client):
        codes = [
            api_client.post(RESEND, {"email": f"x{i}@example.test"}, format="json").status_code
            for i in range(6)
        ]
        assert codes[:5] == [202] * 5 and codes[5] == 429
