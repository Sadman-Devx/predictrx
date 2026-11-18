import httpx
import pytest

from ai.llm import router


PRIMARY_MODEL = "gemini-3.8-flash"
FALLBACK_MODEL = "gemini-3.6-flash"


def _response(status_code=200):
    return httpx.Response(
        status_code,
        json={"candidates": [{"content": {"parts": [{"text": "scan result"}]}}]},
        request=httpx.Request("POST", "https://generativelanguage.googleapis.com"),
    )


def _configure(monkeypatch, fallback=FALLBACK_MODEL):
    values = {
        "SCAN_VISION_LOCAL": False,
        "GEMINI_API_KEY": "test-key",
        "GEMINI_MODEL": PRIMARY_MODEL,
        "GEMINI_FALLBACK_MODEL": fallback,
    }
    monkeypatch.setattr(router, "setting", lambda name, default=None: values.get(name, default))


@pytest.mark.parametrize("status_code", [404, 429, 503])
def test_gemini_switches_to_fallback_on_unavailable_or_busy_primary(monkeypatch, status_code):
    _configure(monkeypatch)
    urls = []
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    def post(url, **_kwargs):
        urls.append(url)
        return _response(status_code if len(urls) == 1 else 200)

    monkeypatch.setattr(httpx, "post", post)

    result = router.vision_complete("prompt", image=b"image", media_type="image/jpeg")

    assert result.text == "scan result"
    assert result.model == FALLBACK_MODEL
    assert f"/models/{PRIMARY_MODEL}:generateContent" in urls[0]
    assert f"/models/{FALLBACK_MODEL}:generateContent" in urls[1]


def test_gemini_switches_to_fallback_on_transport_error(monkeypatch):
    _configure(monkeypatch)
    urls = []

    def post(url, **_kwargs):
        urls.append(url)
        if len(urls) == 1:
            raise httpx.ConnectError("connection unavailable", request=httpx.Request("POST", url))
        return _response()

    monkeypatch.setattr(httpx, "post", post)

    result = router.vision_complete("prompt", image=b"image", media_type="image/jpeg")

    assert result.model == FALLBACK_MODEL
    assert len(urls) == 2


def test_gemini_does_not_hide_authentication_errors_with_fallback(monkeypatch):
    _configure(monkeypatch)
    calls = []

    def post(url, **_kwargs):
        calls.append(url)
        return _response(403)

    monkeypatch.setattr(httpx, "post", post)

    with pytest.raises(httpx.HTTPStatusError):
        router.vision_complete("prompt", image=b"image", media_type="image/jpeg")

    assert len(calls) == 1


def test_gemini_surfaces_fallback_failure(monkeypatch):
    _configure(monkeypatch)
    urls = []

    def post(url, **_kwargs):
        urls.append(url)
        return _response(429)

    monkeypatch.setattr(httpx, "post", post)

    with pytest.raises(httpx.HTTPStatusError):
        router.vision_complete("prompt", image=b"image", media_type="image/jpeg")

    assert len(urls) == 2
    assert f"/models/{FALLBACK_MODEL}:generateContent" in urls[-1]


def test_gemini_keeps_retrying_primary_when_no_fallback_is_configured(monkeypatch):
    _configure(monkeypatch, fallback="")
    urls = []
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    def post(url, **_kwargs):
        urls.append(url)
        return _response(429 if len(urls) == 1 else 200)

    monkeypatch.setattr(httpx, "post", post)

    result = router.vision_complete("prompt", image=b"image", media_type="image/jpeg")

    assert result.model == PRIMARY_MODEL
    assert len(urls) == 2


def test_gemini_rejects_same_primary_and_fallback_model(monkeypatch):
    _configure(monkeypatch, fallback=PRIMARY_MODEL)

    with pytest.raises(router.LLMNotConfigured, match="must differ"):
        router.vision_complete("prompt", image=b"image", media_type="image/jpeg")
