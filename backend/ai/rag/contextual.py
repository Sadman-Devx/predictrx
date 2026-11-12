"""Contextual RAG: every chunk gets a short prefix that says where it comes from, and the prefix is embedded
together with the chunk text, so a retrieved passage is self-explanatory ("warfarin label, DRUG INTERACTIONS ...").

Two ways to build the prefix (setting RAG_CONTEXT_MODE, or the `mode` argument):
  template  deterministic: "Source: ... Drug: ... Section: ..."            (default, free, reproducible)
  local     template + one sentence written by the local Ollama model
  cloud     template + one sentence written by the cloud model
The label text is public (openFDA), not patient data, so the cloud mode is allowed; it still costs tokens per chunk.
The deterministic template is ALWAYS the first part of the prefix, and any model failure falls back to the template
alone, so a model outage never blocks indexing. The prefix is a retrieval aid only: findings cite the chunk text,
never the prefix. Changing the mode changes retrieval: re-run the evaluation (docs/rule.md §2).
"""
import logging
import re

from django.conf import settings

from ..llm.router import cloud_complete, local_complete

logger = logging.getLogger(__name__)

VALID_MODES = ("template", "local", "cloud")
MAX_MODEL_SENTENCE_CHARS = 300
MAX_PASSAGE_WORDS = 250

_PROMPT = """You are indexing a drug label so it can be found by search.
Below is one passage from the "{section}" section of the label for {drug}.
Write one or two short sentences that say what this passage is about, so a search engine can match it.
Rules: use only information that is in the passage; no dosing advice; no opinions; plain text only; at most 50 words.

PASSAGE:
{text}
"""


def context_prefix(*, drug_name: str, section: str, source: str) -> str:
    """Deterministic prefix (also the fallback for the model-written modes)."""
    return f"Source: {source}. Drug: {drug_name}. Section: {section or 'general'}."


def embedding_text(prefix: str, text: str) -> str:
    """The exact string that gets embedded for a chunk."""
    return f"{prefix}\n\n{text}" if prefix else text


def _clean_model_sentence(raw: str) -> str:
    text = re.sub(r"\s+", " ", raw or "").strip().strip("\"'`*# ")
    return text[:MAX_MODEL_SENTENCE_CHARS].rstrip()


def generate_context_prefix(*, drug_name: str, section: str, source: str, text: str, mode: str | None = None) -> str:
    """Prefix for one chunk. Never raises for a model problem: falls back to the template."""
    base = context_prefix(drug_name=drug_name, section=section, source=source)
    mode = (mode or settings.RAG_CONTEXT_MODE or "template").strip().lower()
    if mode == "template":
        return base
    if mode not in VALID_MODES:
        logger.warning("Unknown RAG_CONTEXT_MODE %r; using the template prefix", mode)
        return base

    passage = " ".join(text.split()[:MAX_PASSAGE_WORDS])
    prompt = _PROMPT.format(section=section or "general", drug=drug_name, text=passage)
    try:
        raw = local_complete(prompt) if mode == "local" else cloud_complete(prompt, max_tokens=150)
    except Exception:  # noqa: BLE001 — optional enrichment: any model/network failure must not stop indexing
        logger.warning("Context prefix model call failed (%s mode); using the template prefix", mode, exc_info=True)
        return base
    sentence = _clean_model_sentence(raw)
    return f"{base} {sentence}" if sentence else base