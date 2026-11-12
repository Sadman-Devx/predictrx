"""Index chunks for retrieval: contextual prefix -> embedding -> saved on the Chunk row.

Idempotent: by default only chunks WITHOUT an embedding are processed, so it is safe to re-run after every data
load. Each batch is saved on its own, so if Ollama stops half-way the finished batches are kept and a re-run
continues where it stopped. If embeddings cannot be produced the error is raised (fail fast), not swallowed.

Chunking happens earlier (data/pipeline/load.py); graph edges are built by `ai.rag.graph.rebuild_edges`.
"""
import logging
from dataclasses import dataclass
from typing import Callable

from django.conf import settings
from django.db import transaction

from apps.knowledge.models import Chunk

from .contextual import embedding_text, generate_context_prefix
from .embeddings import embed_texts

logger = logging.getLogger(__name__)

DEFAULT_BATCH = 16


@dataclass
class IndexStats:
    pending_before: int = 0
    chunks_embedded: int = 0
    prefixes_generated: int = 0


def pending_queryset(*, reembed: bool = False, drug: str | None = None):
    qs = Chunk.objects.all()
    if not reembed:
        qs = qs.filter(embedding__isnull=True)
    if drug:
        qs = qs.filter(document__drug__generic_name=drug.strip().lower())
    return qs.order_by("id")


def index_pending(
    *,
    batch_size: int = DEFAULT_BATCH,
    limit: int | None = None,
    reembed: bool = False,
    drug: str | None = None,
    context_mode: str | None = None,
    progress: Callable[[IndexStats], None] | None = None,
) -> IndexStats:
    """Embed chunks that have no embedding yet (or all, with reembed=True).

    context_mode: template | local | cloud (default: settings.RAG_CONTEXT_MODE). In template mode an existing
    prefix is kept; in local/cloud mode the prefix is regenerated for every chunk being processed.
    """
    id_query = pending_queryset(reembed=reembed, drug=drug).values_list("id", flat=True)
    ids = list(id_query[:limit]) if limit else list(id_query)
    stats = IndexStats(pending_before=len(ids))

    mode =(context_mode or settings.RAG_CONTEXT_MODE or "template").strip().lower()
    batch_size = max(1, batch_size)

    for start in range(0, len(ids), batch_size):
        batch_ids = ids[start:start + batch_size]
        chunks = list(Chunk.objects.filter(id__in=batch_ids).select_related("document", "document__drug")
                      .order_by("id"))
        for chunk in chunks:
            if mode == "template" and chunk.context_prefix:
                continue  # keep the prefix the loader (or an earlier run) already wrote
            chunk.context_prefix = generate_context_prefix(
                drug_name=chunk.document.drug.generic_name if chunk.document.drug_id else "",
                section=chunk.section, source=chunk.document.source, text=chunk.text, mode=mode,
            )
            stats.prefixes_generated += 1

        vectors = embed_texts([embedding_text(c.context_prefix, c.text) for c in chunks])  # EmbeddingError propagates
        with transaction.atomic():
            for chunk, vector in zip(chunks, vectors):
                Chunk.objects.filter(pk=chunk.pk).update(embedding=vector, context_prefix=chunk.context_prefix)
        stats.chunks_embedded += len(chunks)
        if progress:
            progress(stats)
    return stats