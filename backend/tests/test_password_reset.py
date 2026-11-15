import re
import secrets

import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.accounts.models import User
from tests.conftest import TEST_PASSWORD

REQUEST = "/api/auth/password-reset/"
CONFIRM = "/api/auth/password-reset/confirm/"
LOGIN = "/api/auth/login/"


def _link_parts():
    body = mail.outbox[-1].body
    m = re.search(r"uid=([^&\s]+)&token=([^\s]+)", body)
    assert m, body
    return m.group(1), m.group(2)


@pytest.mark.django_db
class TestPasswordResetRequest:
    def test_existing_account_gets_an_email_with_a_link(self, api_client, make_user):
        make_user(email="dr.a@example.test")
        r = api_client.post(REQUEST, {"email": "dr.a@example.test"}, format="json")
        assert r.status_code == 202
        assert len(mail.outbox) == 1 and mail.outbox[0].to == ["dr.a@example.test"]
        _link_parts()

    def test_email_match_is_case_insensitive(self, api_client, make_user):
        make_user(email="dr.a@example.test")
        assert api_client.post(REQUEST, {"email": "DR.A@Example.test"}, format="json").status_code == 202
        assert len(mail.outbox) == 1

    def test_unknown_email_gets_same_answer_and_no_mail(self, api_client, make_user):
        known = make_user(email="dr.a@example.test")
        a = api_client.post(REQUEST, {"email": known.email}, format="json")
        b = api_client.post(REQUEST, {"email": "nobody@example.test"}, format="json")
        assert a.status_code == b.status_code == 202 and a.json() == b.json()
        assert len(mail.outbox) == 1  # only the real account

    def test_inactive_account_gets_no_mail(self, api_client, make_user):
        make_user(email="off@example.test", is_active=False)
        assert api_client.post(REQUEST, {"email": "off@example.test"}, format="json").status_code == 202
        assert mail.outbox == []

    def test_invalid_email_is_400(self, api_client):
        assert api_client.post(REQUEST, {"email": "not-an-email"}, format="json").status_code == 400

    def test_request_is_throttled(self, api_client):
        codes = [api_client.post(REQUEST, {"email": f"x{i}@example.test"}, format="json").status_code for i in range(6)]
        assert codes[:5] == [202] * 5 and codes[5] == 429


@pytest.mark.django_db
class TestPasswordResetConfirm:
    def _start(self, api_client, make_user):
        user = make_user(email="dr.a@example.test")
        api_client.post(REQUEST, {"email": user.email}, format="json")
        uid, token = _link_parts()
        return user, uid, token

    def test_full_journey_changes_the_password(self, api_client, make_user):
        user, uid, token = self._start(api_client, make_user)
        new_pw = secrets.token_urlsafe(16)
        r = api_client.post(CONFIRM, {"uid": uid, "token": token, "password": new_pw}, format="json")
        assert r.status_code == 200
        assert api_client.post(LOGIN, {"email": user.email, "password": new_pw}, format="json").status_code == 200
        assert api_client.post(LOGIN, {"email": user.email, "password": TEST_PASSWORD}, format="json").status_code == 401

    def test_link_works_only_once(self, api_client, make_user):
        _, uid, token = self._start(api_client, make_user)
        assert api_client.post(CONFIRM, {"uid": uid, "token": token, "password": secrets.token_urlsafe(16)},
                               format="json").status_code == 200
        again = api_client.post(CONFIRM, {"uid": uid, "token": token, "password": secrets.token_urlsafe(16)},
                                format="json")
        assert again.status_code == 400 and "token" in again.json()["error"]["details"]

    def test_wrong_token_and_bad_uid_are_rejected(self, api_client, make_user):
        _, uid, token = self._start(api_client, make_user)
        pw = secrets.token_urlsafe(16)
        assert api_client.post(CONFIRM, {"uid": uid, "token": token[:-3] + "xxx", "password": pw}, format="json").status_code == 400
        assert api_client.post(CONFIRM, {"uid": "!!!", "token": token, "password": pw}, format="json").status_code == 400
        assert api_client.post(CONFIRM, {"uid": "MTAwMDA", "token": token, "password": pw}, format="json").status_code == 400

    def test_weak_password_is_rejected_and_link_stays_valid(self, api_client, make_user):
        user, uid, token = self._start(api_client, make_user)
        weak = "".join(str(d) for d in range(1, 9))
        r = api_client.post(CONFIRM, {"uid": uid, "token": token, "password": weak}, format="json")
        assert r.status_code == 400 and "password" in r.json()["error"]["details"]
        user.refresh_from_db()
        assert user.check_password(TEST_PASSWORD)  # untouched
        ok = api_client.post(CONFIRM, {"uid": uid, "token": token, "password": secrets.token_urlsafe(16)}, format="json")
        assert ok.status_code == 200

    def test_reset_blacklists_existing_refresh_tokens(self, api_client, make_user):
        user, uid, token = self._start(api_client, make_user)
        login = api_client.post(LOGIN, {"email": user.email, "password": TEST_PASSWORD}, format="json").json()
        api_client.post(CONFIRM, {"uid": uid, "token": token, "password": secrets.token_urlsafe(16)}, format="json")
        r = APIClient().post("/api/auth/token/refresh/", {"refresh": login["refresh"]}, format="json")
        assert r.status_code == 401

    def test_expired_link_is_rejected(self, api_client, make_user, settings):
        _, uid, token = self._start(api_client, make_user)
        settings.PASSWORD_RESET_TIMEOUT = -1
        r = api_client.post(CONFIRM, {"uid": uid, "token": token, "password": secrets.token_urlsafe(16)}, format="json")
        assert r.status_code == 400

    def test_missing_fields_are_400(self, api_client):
        assert api_client.post(CONFIRM, {}, format="json").status_code == 400
