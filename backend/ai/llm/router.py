"""LLM router: cloud model for vision/reasoning, local Ollama for sensitive text.

Rules (docs/rule.md):
  * no keys or model names in code: everything comes from settings / environment;
  * sensitive free text NEVER goes to the cloud: `complete(..., sensitive=True)` is local-only and raises
    LLMNotConfigured when Ollama is not set up (it does not fall back to the cloud);
  * everything that does go to the cloud is PII-redacted here again, at the door, whatever the caller did;
  * a non-sensitive call may fall back to the local model when the cloud model is not configured
    (LLM_FALLBACK_TO_LOCAL, default true). Local is always acceptable for privacy; it is just slower/weaker.

Settings / env (all optional except the model names you actually use):
    ANTHROPIC_API_KEY, CLOUD_LLM_MODEL      cloud model
    OLLAMA_BASE_URL, LOCAL_LLM_MODEL        local model (`ollama pull <model>` first)
    LOCAL_LLM_TIMEOUT / CLOUD_LLM_TIMEOUT   seconds (defaults 120 / 60)
    LLM_FALLBACK_TO_LOCAL                   true (default) | false
    SCAN_VISION_LOCAL                       true -> prescription images go to the LOCAL vision model only (never the cloud)
"""
import base64
import logging
from typing import NamedTuple

from django.conf import settings

from ..config import setting
from ..guardrails.pii import redact

logger = logging.getLogger(__name__)


class LLMNotConfigured(RuntimeError):
    pass


def is_cloud_configured() -> bool:
    return bool(getattr(settings, "ANTHROPIC_API_KEY", "") and getattr(settings, "CLOUD_LLM_MODEL", ""))


def is_local_configured() -> bool:
    return bool(getattr(settings, "LOCAL_LLM_MODEL", ""))


def llm_status() -> dict:
    """What is configured, without any key or model name (safe to log or show in a health check)."""
    return {"cloud_configured": is_cloud_configured(), "local_configured": is_local_configured(),
            "fallback_to_local": bool(setting("LLM_FALLBACK_TO_LOCAL", True))}


def cloud_complete(prompt: str, *, system: str = "", max_tokens: int = 1000) -> str:
    if not is_cloud_configured():
        raise LLMNotConfigured("Set ANTHROPIC_API_KEY and CLOUD_LLM_MODEL in .env")
    import anthropic

    safe_prompt = redact(prompt)
    safe_system = redact(system or "You are a careful clinical decision-support assistant. Cite sources. Never give dosing.")
    if safe_prompt.counts:
        logger.info("PII redacted before the cloud call: %s", safe_prompt.counts)  # label -> count only, never text

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=float(setting("CLOUD_LLM_TIMEOUT", 60.0)))
    msg = client.messages.create(
        model=settings.CLOUD_LLM_MODEL,
        max_tokens=max_tokens,
        system=safe_system.text,
        messages=[{"role": "user", "content": safe_prompt.text}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def local_complete(prompt: str, *, system: str = "", max_tokens: int | None = None) -> str:
    """Ollama on this machine/network. Temperature 0: the same input gives (nearly) the same output."""
    if not is_local_configured():
        raise LLMNotConfigured("Set LOCAL_LLM_MODEL in .env (and `ollama pull` it)")
    import httpx

    options: dict = {"temperature": 0}
    if max_tokens:
        options["num_predict"] = int(max_tokens)
    r = httpx.post(
        f"{str(settings.OLLAMA_BASE_URL).rstrip('/')}/api/generate",
        json={"model": settings.LOCAL_LLM_MODEL, "prompt": prompt, "system": system, "stream": False,
              "options": options},
        timeout=float(setting("LOCAL_LLM_TIMEOUT", 120.0)),
    )
    r.raise_for_status()
    return r.json().get("response", "")


class VisionReply(NamedTuple):
    text: str
    provider: str  # "cloud" | "local"
    model: str  # model name taken from settings (never hard-coded), kept for the "AI tools used" documentation


def _cloud_vision(prompt: str, image: bytes, media_type: str, system: str, max_tokens: int) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=float(setting("CLOUD_LLM_TIMEOUT", 60.0)))
    msg = client.messages.create(
        model=settings.CLOUD_LLM_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                             "data": base64.b64encode(image).decode("ascii")}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def _local_vision(prompt: str, image: bytes, system: str, max_tokens: int) -> str:
    """Ollama vision model (e.g. a llava / qwen-vl class model). LOCAL_LLM_MODEL must be a vision-capable model."""
    import httpx

    r = httpx.post(
        f"{str(settings.OLLAMA_BASE_URL).rstrip('/')}/api/generate",
        json={"model": settings.LOCAL_LLM_MODEL, "prompt": prompt, "system": system, "stream": False,
              "think": False,  # thinking models would spend the whole token budget before writing the JSON
              "images": [base64.b64encode(image).decode("ascii")],
              "options": {"temperature": 0, "num_predict": int(max_tokens)}},
        timeout=float(setting("LOCAL_LLM_TIMEOUT", 120.0)),
    )
    r.raise_for_status()
    return r.json().get("response", "")

def _gemini_vision(prompt: str, image: bytes, media_type: str, system: str, max_tokens: int) -> str:
    """Google AI Studio (Gemini API). Key and model come from env (GEMINI_API_KEY, GEMINI_MODEL)."""
    import time

    import httpx

    model = setting("GEMINI_MODEL", "")
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": media_type, "data": base64.b64encode(image).decode("ascii")}},
            {"text": prompt},
        ]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": int(max_tokens)},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"x-goog-api-key": setting("GEMINI_API_KEY", "")}  # header, not URL: keeps the key out of error logs

    delays = (3, 8, 15)  # seconds to wait before retry 1, 2, 3 (well inside the task's 200 s soft limit)
    for attempt in range(len(delays) + 1):
        try:
            r = httpx.post(url, headers=headers, json=body, timeout=float(setting("CLOUD_LLM_TIMEOUT", 60.0)))
            if r.status_code in (429, 500, 503, 504) and attempt < len(delays):
                logger.warning("gemini returned %s, retrying in %ss", r.status_code, delays[attempt])
                time.sleep(delays[attempt])
                continue
            r.raise_for_status()
            break
        except httpx.TransportError:  # timeout / connection reset: also worth a retry
            if attempt >= len(delays):
                raise
            time.sleep(delays[attempt])

    parts = (r.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def vision_complete(prompt: str, *, image: bytes, media_type: str, system: str = "", max_tokens: int = 1500) -> VisionReply:
    """Read an image. The prompt must be static text (no patient data): the image itself cannot be redacted, which is why
    the API only starts a scan after the patient's `analysis` consent (apps/clinical/services.py).

    SCAN_VISION_LOCAL=true keeps the image on this network (local Ollama only, no cloud fallback).
    Otherwise: cloud model if configured, else the local model when LLM_FALLBACK_TO_LOCAL allows it.
    """
    if setting("SCAN_VISION_LOCAL", False):
        if not is_local_configured():
            raise LLMNotConfigured("SCAN_VISION_LOCAL is on but LOCAL_LLM_MODEL is not set")
        return VisionReply(_local_vision(prompt, image, system, max_tokens), "local", settings.LOCAL_LLM_MODEL)

    if setting("GEMINI_API_KEY", "") and setting("GEMINI_MODEL", ""):
        return VisionReply(_gemini_vision(prompt, image, media_type, system, max_tokens), "cloud", setting("GEMINI_MODEL", ""))
    
    if is_cloud_configured():
        return VisionReply(_cloud_vision(prompt, image, media_type, system, max_tokens), "cloud", settings.CLOUD_LLM_MODEL)
    if setting("LLM_FALLBACK_TO_LOCAL", True) and is_local_configured():
        logger.info("cloud vision model not configured; using the local model")
        return VisionReply(_local_vision(prompt, image, system, max_tokens), "local", settings.LOCAL_LLM_MODEL)
    raise LLMNotConfigured("No vision model configured: set CLOUD_LLM_MODEL + ANTHROPIC_API_KEY, or a vision LOCAL_LLM_MODEL")


def complete(prompt: str, *, sensitive: bool, **kw) -> str:
    """Sensitive free text stays local; everything else may use the cloud model (after PII redaction)."""
    if sensitive:
        return local_complete(prompt, **kw)  # never falls back to the cloud
    if is_cloud_configured():
        return cloud_complete(prompt, **kw)
    if setting("LLM_FALLBACK_TO_LOCAL", True) and is_local_configured():
        logger.info("cloud model not configured; using the local model")
        return local_complete(prompt, **kw)
    raise LLMNotConfigured("No model configured: set CLOUD_LLM_MODEL + ANTHROPIC_API_KEY, or LOCAL_LLM_MODEL")