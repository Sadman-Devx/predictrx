"""LLM router: cloud model for vision/reasoning, local Ollama for sensitive text.

Rules: no keys or model names in code (read from settings/env); never send un-redacted patient notes to the cloud.
"""
from django.conf import settings


class LLMNotConfigured(RuntimeError):
    pass


def cloud_complete(prompt: str, *, system: str = "", max_tokens: int = 1000) -> str:
    if not settings.ANTHROPIC_API_KEY or not settings.CLOUD_LLM_MODEL:
        raise LLMNotConfigured("Set ANTHROPIC_API_KEY and CLOUD_LLM_MODEL in .env")
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=settings.CLOUD_LLM_MODEL,
        max_tokens=max_tokens,
        system=system or "You are a careful clinical decision-support assistant. Cite sources. Never give dosing.",
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def local_complete(prompt: str, *, system: str = "") -> str:
    if not settings.LOCAL_LLM_MODEL:
        raise LLMNotConfigured("Set LOCAL_LLM_MODEL in .env (and `ollama pull` it)")
    import httpx

    r = httpx.post(
        f"{settings.OLLAMA_BASE_URL}/api/generate",
        json={"model": settings.LOCAL_LLM_MODEL, "prompt": prompt, "system": system, "stream": False},
        timeout=120,
    )
    r.raise_for_status()
    return r.json().get("response", "")


def complete(prompt: str, *, sensitive: bool, **kw) -> str:
    """Sensitive free text stays local; everything else may use the cloud model (after PII redaction)."""
    return local_complete(prompt, **kw) if sensitive else cloud_complete(prompt, **kw)
