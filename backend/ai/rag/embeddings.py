"""Embedding client. Embeddings are computed by the local Ollama server (`/api/embed`), so label text and drug
names used as queries never leave the machine.

Settings (no model names in code, docs/rule.md §2):
  EMBEDDING_MODEL       Ollama model name (must be pulled: `ollama pull <name>`)
  EMBEDDING_DIM         output size of that model; must equal Chunk.embedding dimensions
  EMBEDDING_BATCH_SIZE  texts per request
  EMBEDDING_TIMEOUT     seconds per request

Changing the model or its dimension needs a migration for Chunk.embedding AND re-embedding every chunk
(`manage.py index_knowledge --reembed`), then a new evaluation run.
"""
import logging
import time
from typing import Sequence

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

_RETRIES = 3


class EmbeddingError(RuntimeError):
    """Embeddings could not be produced (server down, model missing, bad response)."""


class EmbeddingNotConfigured(EmbeddingError):
    pass


class EmbeddingDimensionError(EmbeddingError):
    pass


def is_configured() -> bool:
    return bool(settings.EMBEDDING_MODEL)


def _post(batch: list[str]) -> dict:
    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/embed"
    payload = {"model": settings.EMBEDDING_MODEL, "input": batch}
    last: Exception | None = None
    for attempt in range(_RETRIES):
        try:
            response = httpx.post(url, json=payload, timeout=settings.EMBEDDING_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            last = exc
            if exc.response.status_code < 500:  # model missing / bad request: retrying will not help
                detail = exc.response.text[:200]
                raise EmbeddingError(f"Ollama rejected the embedding request ({exc.response.status_code}): {detail}") from exc
        except httpx.TransportError as exc:  # server not reachable, timeout
            last = exc
        time.sleep(0.5 * 2 ** attempt)
    raise EmbeddingError(f"Ollama embedding request failed after {_RETRIES} tries: {last}") from last


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Embed texts in batches. Returns one vector per text, in order. Raises EmbeddingError on any problem."""
    if not settings.EMBEDDING_MODEL:
        raise EmbeddingNotConfigured("Set EMBEDDING_MODEL in .env (and `ollama pull` it)")
    items = list(texts)
    if any(not t or not t.strip() for t in items):
        raise ValueError("blank text cannot be embedded")

    size = max(1, settings.EMBEDDING_BATCH_SIZE)
    vectors: list[list[float]] = []
    for start in range(0, len(items), size):
        batch = items[start:start + size]
        data = _post(batch)
        got = data.get("embeddings")
        if not isinstance(got, list) or len(got) != len(batch):
            raise EmbeddingError("Ollama returned an unexpected number of embeddings")
        for vec in got:
            if len(vec) != settings.EMBEDDING_DIM:
                raise EmbeddingDimensionError(
                    f"Model {settings.EMBEDDING_MODEL!r} returns {len(vec)} numbers but EMBEDDING_DIM="
                    f"{settings.EMBEDDING_DIM}. Use a model with matching size, or change EMBEDDING_DIM "
                    f"(needs a migration and a full re-embed)."
                )
        vectors.extend(got)
    return vectors


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]