"""Vector retrieval over pgvector. Returns chunk objects whose IDs become `evidence` entries on findings.

TODO (lead): embed the query (same model as ingest), add graph expansion via GraphEdge, add reranking if time allows.
"""
from pgvector.django import CosineDistance

from apps.knowledge.models import Chunk


def search(query_embedding: list[float], k: int = 5):
    return (
        Chunk.objects.exclude(embedding__isnull=True)
        .annotate(distance=CosineDistance("embedding", query_embedding))
        .order_by("distance")
        .select_related("document")[:k]
    )
