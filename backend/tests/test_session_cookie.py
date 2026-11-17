"""The refresh token lives in an httpOnly cookie: a page reload can restore the session without any token in JS."""
import pytest
from rest_framework.test import APIClient

from tests.conftest import TEST_PASSWORD

LOGIN = "/api/auth/login/"
REFRESH = "/api/auth/token/refresh/"
LOGOUT = "/api/auth/logout/"


def _login(client, user):
    return client.post(LOGIN, {"email": user.email, "password": TEST_PASSWORD}, format="json")


@pytest.mark.django_db
class TestSessionCookie:
    def test_login_sets_an_httponly_cookie(self, api_client, doctor, settings):
        r = _login(api_client, doctor)
        assert r.status_code == 200
        morsel = r.cookies[settings.AUTH_REFRESH_COOKIE]
        assert morsel.value and morsel["httponly"] and morsel["path"] == "/api/auth/"

    def test_refresh_works_from_the_cookie_alone(self, api_client, doctor):
        _login(api_client, doctor)
        r = api_client.post(REFRESH, {}, format="json")
        assert r.status_code == 200 and r.json()["access"]

    def test_refresh_rotates_the_cookie_and_kills_the_old_token(self, api_client, doctor, settings):
        _login(api_client, doctor)
        name = settings.AUTH_REFRESH_COOKIE
        old = api_client.cookies[name].value
        assert api_client.post(REFRESH, {}, format="json").status_code == 200
        assert api_client.cookies[name].value != old
        stale = APIClient()
        stale.cookies[name] = old
        assert stale.post(REFRESH, {}, format="json").status_code == 401

    def test_refresh_without_any_token_is_401(self, api_client):
        r = api_client.post(REFRESH, {}, format="json")
        assert r.status_code == 401 and r.json()["error"]["code"] == "token_not_valid"

    def test_refresh_token_can_be_kept_out_of_the_body(self, api_client, doctor, settings):
        settings.AUTH_REFRESH_IN_BODY = False
        r = _login(api_client, doctor)
        assert "refresh" not in r.json() and "access" in r.json()
        assert settings.AUTH_REFRESH_COOKIE in r.cookies
        assert "refresh" not in api_client.post(REFRESH, {}, format="json").json()

    def test_logout_blacklists_the_token_and_clears_the_cookie(self, api_client, doctor, settings):
        _login(api_client, doctor)
        name = settings.AUTH_REFRESH_COOKIE
        old = api_client.cookies[name].value
        r = api_client.post(LOGOUT, {}, format="json")
        assert r.status_code == 204 and r.cookies[name].value == ""
        stale = APIClient()
        stale.cookies[name] = old
        assert stale.post(REFRESH, {}, format="json").status_code == 401

    def test_logout_without_a_token_is_400_but_still_clears_the_cookie(self, api_client, settings):
        r = api_client.post(LOGOUT, {}, format="json")
        assert r.status_code == 400 and r.cookies[settings.AUTH_REFRESH_COOKIE].value == ""
