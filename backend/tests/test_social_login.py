import pytest

from apps.accounts import social
from apps.accounts.models import User

GOOGLE = "/api/auth/social/google/"
FACEBOOK = "/api/auth/social/facebook/"
LINKEDIN = "/api/auth/social/linkedin/"


@pytest.fixture(autouse=True)
def _providers(settings):
    settings.GOOGLE_CLIENT_ID = "google-client"
    settings.FACEBOOK_APP_ID = "fb-app"
    settings.FACEBOOK_APP_SECRET = "fb-secret"
    settings.LINKEDIN_CLIENT_ID = "li-client"
    settings.LINKEDIN_CLIENT_SECRET = "li-secret"
    settings.SOCIAL_AUTO_CREATE = True


def fake_http(monkeypatch, responses):
    """responses: {url_prefix: dict | SocialAuthError}. Records the calls made."""
    calls = []

    def _fake(url, *, headers=None, form=None):
        calls.append(url)
        for prefix, value in responses.items():
            if url.startswith(prefix):
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(social, "_http_json", _fake)
    return calls


def google_info(**over):
    base = {"aud": "google-client", "iss": "https://accounts.google.com", "email": "New.Doc@Example.test",
            "email_verified": "true", "name": "New Doc"}
    base.update(over)
    return {"https://oauth2.googleapis.com/tokeninfo": base}


@pytest.mark.django_db
class TestGoogle:
    def test_first_sign_in_creates_a_doctor_and_returns_tokens(self, api_client, monkeypatch):
        fake_http(monkeypatch, google_info())
        r = api_client.post(GOOGLE, {"id_token": "abc", "preferred_language": "en"}, format="json")
        assert r.status_code == 200 and {"access", "refresh"} <= set(r.json())
        user = User.objects.get(email="new.doc@example.test")
        assert user.role == "doctor" and user.display_name == "New Doc" and user.preferred_language == "en"
        assert not user.has_usable_password()

    def test_access_token_works_on_me(self, api_client, monkeypatch):
        fake_http(monkeypatch, google_info())
        tokens = api_client.post(GOOGLE, {"id_token": "abc"}, format="json").json()
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        assert api_client.get("/api/auth/me/").json()["email"] == "new.doc@example.test"

    def test_existing_account_is_reused_not_duplicated(self, api_client, make_user, monkeypatch):
        make_user(email="new.doc@example.test", role="pharmacist")
        fake_http(monkeypatch, google_info())
        assert api_client.post(GOOGLE, {"id_token": "abc"}, format="json").status_code == 200
        assert User.objects.filter(email__iexact="new.doc@example.test").count() == 1
        assert User.objects.get(email="new.doc@example.test").role == "pharmacist"

    def test_token_for_another_app_is_rejected(self, api_client, monkeypatch):
        fake_http(monkeypatch, google_info(aud="someone-elses-app"))
        r = api_client.post(GOOGLE, {"id_token": "abc"}, format="json")
        assert r.status_code == 401 and not User.objects.exists()

    def test_unverified_email_is_rejected(self, api_client, monkeypatch):
        fake_http(monkeypatch, google_info(email_verified="false"))
        r = api_client.post(GOOGLE, {"id_token": "abc"}, format="json")
        assert r.status_code == 400 and r.json()["error"]["code"] == "email_not_verified"
        assert not User.objects.exists()

    def test_provider_rejecting_the_token_is_401(self, api_client, monkeypatch):
        fake_http(monkeypatch, {"https://oauth2.googleapis.com/tokeninfo":
                                social.SocialAuthError("invalid_credential", "bad", 401)})
        assert api_client.post(GOOGLE, {"id_token": "abc"}, format="json").status_code == 401

    def test_provider_down_is_502(self, api_client, monkeypatch):
        fake_http(monkeypatch, {"https://oauth2.googleapis.com/tokeninfo":
                                social.SocialAuthError("provider_unreachable", "down", 502)})
        assert api_client.post(GOOGLE, {"id_token": "abc"}, format="json").status_code == 502

    def test_not_configured_is_503(self, api_client, settings):
        settings.GOOGLE_CLIENT_ID = ""
        r = api_client.post(GOOGLE, {"id_token": "abc"}, format="json")
        assert r.status_code == 503 and r.json()["error"]["code"] == "provider_not_configured"

    def test_auto_create_can_be_switched_off(self, api_client, settings, monkeypatch):
        settings.SOCIAL_AUTO_CREATE = False
        fake_http(monkeypatch, google_info())
        r = api_client.post(GOOGLE, {"id_token": "abc"}, format="json")
        assert r.status_code == 403 and not User.objects.exists()

    def test_admin_and_disabled_accounts_cannot_use_social(self, api_client, make_user, monkeypatch):
        fake_http(monkeypatch, google_info())
        admin = make_user(role="admin", email="new.doc@example.test")
        assert api_client.post(GOOGLE, {"id_token": "abc"}, format="json").status_code == 403
        admin.role, admin.is_active = "doctor", False
        admin.save()
        assert api_client.post(GOOGLE, {"id_token": "abc"}, format="json").status_code == 403

    def test_unknown_provider_is_404(self, api_client):
        assert api_client.post("/api/auth/social/twitter/", {}, format="json").status_code == 404


@pytest.mark.django_db
class TestFacebook:
    def _ok(self, **me):
        return {
            "https://graph.facebook.com/debug_token": {"data": {"is_valid": True, "app_id": "fb-app"}},
            "https://graph.facebook.com/me": {"id": "1", "name": "Fb Doc", "email": "fb.doc@example.test", **me},
        }

    def test_valid_token_signs_in(self, api_client, monkeypatch):
        fake_http(monkeypatch, self._ok())
        r = api_client.post(FACEBOOK, {"access_token": "t"}, format="json")
        assert r.status_code == 200 and User.objects.filter(email="fb.doc@example.test").exists()

    def test_token_from_another_app_is_rejected(self, api_client, monkeypatch):
        responses = self._ok()
        responses["https://graph.facebook.com/debug_token"] = {"data": {"is_valid": True, "app_id": "other"}}
        fake_http(monkeypatch, responses)
        assert api_client.post(FACEBOOK, {"access_token": "t"}, format="json").status_code == 401

    def test_missing_email_is_rejected(self, api_client, monkeypatch):
        responses = self._ok()
        responses["https://graph.facebook.com/me"] = {"id": "1", "name": "No Mail"}
        fake_http(monkeypatch, responses)
        r = api_client.post(FACEBOOK, {"access_token": "t"}, format="json")
        assert r.status_code == 400 and r.json()["error"]["code"] == "email_not_provided"


@pytest.mark.django_db
class TestLinkedIn:
    def _ok(self, **info):
        return {
            "https://www.linkedin.com/oauth/v2/accessToken": {"access_token": "li-token"},
            "https://api.linkedin.com/v2/userinfo": {"email": "li.doc@example.test", "email_verified": True,
                                                    "name": "Li Doc", **info},
        }

    def test_code_flow_signs_in(self, api_client, monkeypatch):
        fake_http(monkeypatch, self._ok())
        r = api_client.post(LINKEDIN, {"code": "c", "redirect_uri": "http://localhost:5173/auth/linkedin"}, format="json")
        assert r.status_code == 200 and User.objects.filter(email="li.doc@example.test").exists()

    def test_needs_code_and_redirect_uri(self, api_client, monkeypatch):
        fake_http(monkeypatch, self._ok())
        assert api_client.post(LINKEDIN, {"code": "c"}, format="json").status_code == 400

    def test_unverified_email_is_rejected(self, api_client, monkeypatch):
        fake_http(monkeypatch, self._ok(email_verified=False))
        r = api_client.post(LINKEDIN, {"code": "c", "redirect_uri": "http://localhost:5173/x"}, format="json")
        assert r.status_code == 400 and not User.objects.exists()
