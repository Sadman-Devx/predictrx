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
"""
import logging

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