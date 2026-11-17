import re
import secrets
from urllib.parse import unquote

import pytest
from django.core import mail

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


def _token():
    m = re.search(r"verify-email\?token=(\S+)", mail.outbox[-1].body)
    assert m, mail.outbox[-1].body
    return unquote(m.group(1))


@pytest.mark.django_db
class TestVerification:
    def test_register_sends_a_link_and_starts_unverified(self, api_client):
        r = _register(api_client)
        assert r.status_code == 201 and r.json()["email_verified"] is False
        assert len(mail.outbox) == 1 and mail.outbox[0].to == ["new.doc@example.test"]
        assert "http://localhost:5173/verify-email?token=" in mail.outbox[0].body

    def test_link_verifies_the_account(self, api_client):
        _register(api_client)
        r = api_client.post(VERIFY, {"token": _token()}, format="json")
        assert r.status_code == 200
        assert User.objects.get(email="new.doc@example.test").email_verified is True

    def test_link_can_be_opened_twice(self, api_client):
        _register(api_client)
        token = _token()
        assert api_client.post(VERIFY, {"token": token}, format="json").status_code == 200
        assert api_client.post(VERIFY, {"token": token}, format="json").status_code == 200

    def test_bad_or_missing_token_is_400(self, api_client):
        assert api_client.post(VERIFY, {"token": "garbage"}, format="json").status_code == 400
        assert api_client.post(VERIFY, {}, format="json").status_code == 400

    def test_expired_link_is_rejected(self, api_client, settings):
        _register(api_client)
        token = _token()
        settings.EMAIL_VERIFICATION_TIMEOUT = -1
        assert api_client.post(VERIFY, {"token": token}, format="json").status_code == 400

    def test_link_dies_when_the_email_changes(self, api_client):
        _register(api_client)
        token = _token()
        User.objects.filter(email="new.doc@example.test").update(email="other.address@example.test")
        assert api_client.post(VERIFY, {"token": token}, format="json").status_code == 400


@pytest.mark.django_db
class TestLoginGate:
    def test_login_is_open_by_default(self, api_client):
        _register(api_client)
        assert api_client.post(LOGIN, {"email": "new.doc@example.test", "password": PW}, format="json").status_code == 200

    def test_login_is_blocked_until_verified_when_required(self, api_client, settings):
        settings.REQUIRE_EMAIL_VERIFICATION = True
        _register(api_client)
        creds = {"email": "new.doc@example.test", "password": PW}
        blocked = api_client.post(LOGIN, creds, format="json")
        assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "email_not_verified"
        api_client.post(VERIFY, {"token": _token()}, format="json")
        assert api_client.post(LOGIN, creds, format="json").status_code == 200

    def test_wrong_password_still_looks_like_a_normal_failure(self, api_client, settings):
        settings.REQUIRE_EMAIL_VERIFICATION = True
        _register(api_client)
        r = api_client.post(LOGIN, {"email": "new.doc@example.test", "password": "wrong-password-1"}, format="json")
        assert r.status_code == 401

    def test_family_and_admin_are_exempt(self, api_client, make_user, settings):
        settings.REQUIRE_EMAIL_VERIFICATION = True
        for role in ("family", "admin"):
            user = make_user(role)
            r = api_client.post(LOGIN, {"email": user.email, "password": TEST_PASSWORD}, format="json")
            assert r.status_code == 200, role

    def test_reset_link_counts_as_proof_of_the_mailbox(self, api_client, make_user, settings):
        settings.REQUIRE_EMAIL_VERIFICATION = True
        user = make_user("doctor", email="dr.reset@example.test")
        api_client.post(RESET, {"email": user.email}, format="json")
        m = re.search(r"uid=([^&\s]+)&token=([^\s]+)", mail.outbox[-1].body)
        new_pw = secrets.token_urlsafe(16)
        assert api_client.post(RESET_CONFIRM, {"uid": m.group(1), "token": m.group(2), "password": new_pw},
                               format="json").status_code == 200
        assert api_client.post(LOGIN, {"email": user.email, "password": new_pw}, format="json").status_code == 200


@pytest.mark.django_db
class TestResend:
    def test_unverified_account_gets_a_new_link(self, api_client):
        _register(api_client)
        mail.outbox.clear()
        assert api_client.post(RESEND, {"email": "NEW.doc@example.test"}, format="json").status_code == 202
        assert len(mail.outbox) == 1

    def test_unknown_and_verified_accounts_get_the_same_answer_and_no_mail(self, api_client, make_user):
        verified = make_user("doctor", email="ok@example.test", email_verified=True)
        a = api_client.post(RESEND, {"email": verified.email}, format="json")
        b = api_client.post(RESEND, {"email": "nobody@example.test"}, format="json")
        assert a.status_code == b.status_code == 202 and a.json() == b.json()
        assert mail.outbox == []

    def test_resend_is_throttled(self, api_client):
        codes = [api_client.post(RESEND, {"email": f"x{i}@example.test"}, format="json").status_code for i in range(6)]
        assert codes[:5] == [202] * 5 and codes[5] == 429
