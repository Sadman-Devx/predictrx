"""Retrieval: vector search (pgvector) + graph hop, returning chunk IDs that become `evidence` on findings.

Main entry point for the Drug Interaction agent:

    result = retrieve_for_pair("warfarin", "aspirin")
    for chunk in result.evidence_chunks:            # passages that really name BOTH drugs
        finding["evidence"].append(chunk.as_evidence())   # {"type": "chunk", "id": ..., "source": ...}

How a pair is retrieved:
  1. Vector search for "drug interaction between A and B", limited to the labels of A and B.
  2. Graph hop (`chunks_linking`): passages of A's label that name B and passages of B's label that name A.
  3. Merge, mark which passages really name the other drug (`supports_pair`), rank, cut to k.

`supports_pair` is the honest part: a passage from A's label that never names B is context, not evidence of an
A+B interaction. Only `supports_pair` chunks should be cited. If vector search is unavailable (Ollama down, model
not configured, nothing embedded yet) the graph part still works and `mode` says so; the agent should put the
mode and warnings in the trace. No usable chunk at all is a valid outcome: the finding stays "insufficient evidence".
"""
import logging
from dataclasses import dataclass, field

from django.db.models import QuerySet
from pgvector.django import CosineDistance

from apps.drugs.models import Drug
from apps.knowledge.models import Chunk

from .embeddings import EmbeddingError, embed_query
from .graph import chunks_linking, mentions_drug, section_rank

logger = logging.getLogger(__name__)

DEFAULT_K = 5


# ----------------------------------------------------------------------------------------------------------
# Plain vector search
# ----------------------------------------------------------------------------------------------------------
def search(query_embedding: list[float], k: int = DEFAULT_K, *, drug_ids: list[int] | None = None,
           sections: list[str] | None = None) -> QuerySet:
    """Nearest chunks by cosine distance (annotated as `.distance`). Optionally limited to some drugs' labels."""
    qs = Chunk.objects.exclude(embedding__isnull=True)
    if drug_ids:
        qs = qs.filter(document__drug_id__in=drug_ids)
    if sections:
        qs = qs.filter(section__in=sections)
    return (
        qs.annotate(distance=CosineDistance("embedding", query_embedding))
        .order_by("distance")
        .select_related("document", "document__drug")[:k]
    )


def retrieve(query: str, k: int = DEFAULT_K, *, drug_ids: list[int] | None = None) -> list[Chunk]:
    """Embed free text and return the nearest chunks. Raises EmbeddingError if embeddings are unavailable."""
    return list(search(embed_query(query), k, drug_ids=drug_ids))


# ----------------------------------------------------------------------------------------------------------
# Pair retrieval
# ----------------------------------------------------------------------------------------------------------
@dataclass
class RetrievedChunk:
    chunk_id: int
    document_id: int
    drug: str  # generic name of the drug whose label this passage comes from
    section: str
    text: str
    source: str  # KnowledgeDocument.source, e.g. openfda_label
    source_url: str
    license_note: str
    distance: float | None  # cosine distance; None when found only through the graph
    via: list[str] = field(default_factory=list)  # "vector" and/or "graph"
    supports_pair: bool = False  # this label passage names the OTHER drug of the pair

    def as_evidence(self) -> dict:
        """Entry for RiskFinding.evidence (backend-design §2.5)."""
        return {"type": "chunk", "id": self.chunk_id, "source": self.source}

    def as_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id, "document_id": self.document_id, "drug": self.drug, "section": self.section,
            "text": self.text, "source": self.source, "source_url": self.source_url,
            "license_note": self.license_note, "distance": self.distance, "via": list(self.via),
            "supports_pair": self.supports_pair,
        }


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    mode: str  # hybrid | graph_only | none
    warnings: list[str] = field(default_factory=list)

    @property
    def evidence_chunks(self) -> list[RetrievedChunk]:
        """Only passages that name both drugs: the ones that may be cited."""
        return [c for c in self.chunks if c.supports_pair]


def resolve_drug(ref) -> Drug | None:
    """Drug instance, primary key, or generic name / alias (exact, case-insensitive). No fuzzy guessing."""
    if isinstance(ref, Drug):
        return ref
    if isinstance(ref, int):
        return Drug.objects.filter(pk=ref).first()
    name = (ref or "").strip().lower()
    if not name:
        return None
    return Drug.objects.filter(generic_name=name).first() or Drug.objects.filter(aliases__contains=[name]).first()


def _to_retrieved(chunk: Chunk, drug_a: Drug, drug_b: Drug, via: str, distance: float | None) -> RetrievedChunk:
    owner_id = chunk.document.drug_id
    if owner_id == drug_a.id:
        supports = mentions_drug(chunk.text, drug_b)
    elif owner_id == drug_b.id:
        supports = mentions_drug(chunk.text, drug_a)
    else:
        supports = False
    return RetrievedChunk(
        chunk_id=chunk.id, document_id=chunk.document_id,
        drug=chunk.document.drug.generic_name if chunk.document.drug_id else "",
        section=chunk.section, text=chunk.text, source=chunk.document.source,
        source_url=chunk.document.source_url, license_note=chunk.document.license_note,
        distance=distance, via=[via], supports_pair=supports,
    )


def retrieve_for_pair(drug_a, drug_b, *, k: int = DEFAULT_K) -> RetrievalResult:
    """Label passages about a drug pair. `drug_a` / `drug_b`: generic name, alias, Drug or id."""
    a, b = resolve_drug(drug_a), resolve_drug(drug_b)
    if a is None or b is None or a.id == b.id:
        return RetrievalResult([], "none", ["both drugs must be known and different"])

    warnings: list[str] = []
    merged: dict[int, RetrievedChunk] = {}

    def add(chunk: Chunk, via: str, distance: float | None = None) -> None:
        item = _to_retrieved(chunk, a, b, via, distance)
        known = merged.get(chunk.id)
        if known is None:
            merged[chunk.id] = item
            return
        if via not in known.via:
            known.via.append(via)
        if distance is not None and (known.distance is None or distance < known.distance):
            known.distance = distance

    vector_ok = False
    try:
        query = embed_query(f"drug interaction between {a.generic_name} and {b.generic_name}")
        hits = list(search(query, max(k * 2, 10), drug_ids=[a.id, b.id]))
        vector_ok = True
        if not hits:
            warnings.append("no embedded chunks for these drugs (run: manage.py index_knowledge)")
        for chunk in hits:
            add(chunk, "vector", float(chunk.distance))
    except EmbeddingError as exc:
        warnings.append(f"vector search unavailable, using graph only: {exc}")
        logger.warning("Vector search unavailable for pair %s/%s: %s", a.generic_name, b.generic_name, exc)

    for chunk in chunks_linking(a.id, b.id, limit=max(k * 2, 10)):
        add(chunk, "graph")

    ranked = sorted(
        merged.values(),
        key=lambda c: (
            not c.supports_pair,  # real evidence first
            section_rank(c.section),
            -len(c.via),  # found by both vector and graph first
            c.distance if c.distance is not None else 1.0,
            c.chunk_id,
        ),
    )[:k]

    if not ranked:
        return RetrievalResult([], "none", warnings)
    return RetrievalResult(ranked, "hybrid" if vector_ok else "graph_only", warnings)