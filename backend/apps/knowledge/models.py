from django.conf import settings
from django.db import models
from pgvector.django import HnswIndex, VectorField

from apps.drugs.models import Drug


class KnowledgeDocument(models.Model):
    source = models.CharField(max_length=30)  # openfda_label | ddinter
    drug = models.ForeignKey(Drug, null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")
    title = models.CharField(max_length=250)
    source_url = models.URLField(blank=True)
    license_note = models.CharField(max_length=120, blank=True)
    fetched_at = models.DateTimeField()
    content_hash = models.CharField(max_length=64, unique=True)  # dedupe on re-ingest


class Chunk(models.Model):
    document = models.ForeignKey(KnowledgeDocument, on_delete=models.CASCADE, related_name="chunks")
    section = models.CharField(max_length=80, blank=True)
    text = models.TextField()
    context_prefix = models.TextField(blank=True)  # contextual RAG prefix, embedded with text
    # Dimension must match the embedding model (EMBEDDING_DIM). Changing it needs re-embedding.
    embedding = VectorField(dimensions=settings.EMBEDDING_DIM, null=True, blank=True)
    token_count = models.IntegerField(default=0)

    class Meta:
        indexes = [
            HnswIndex(name="chunk_embedding_hnsw", fields=["embedding"], m=16, ef_construction=64,
                      opclasses=["vector_cosine_ops"]),
        ]


class GraphEdge(models.Model):
    src_type = models.CharField(max_length=20)  # drug | chunk
    src_id = models.BigIntegerField()
    relation = models.CharField(max_length=40)  # mentions | interacts_with | contraindicated_with
    dst_type = models.CharField(max_length=20)
    dst_id = models.BigIntegerField()
    chunk = models.ForeignKey(Chunk, null=True, blank=True, on_delete=models.SET_NULL, related_name="edges")

    class Meta:
        indexes = [models.Index(fields=["src_type", "src_id"]), models.Index(fields=["dst_type", "dst_id"])]
