"""Graph RAG over `GraphEdge`: link drugs to the label passages that name them.

Edges built here (every edge carries `chunk` = the passage that justifies it, so every edge can be cited):

    chunk --mentions-->            drug   a passage of some label names this other drug (any section)
    drug  --interacts_with-->      drug   the label of the src drug names dst inside its DRUG INTERACTIONS section
    drug  --contraindicated_with--> drug  ... inside its CONTRAINDICATIONS section

An edge means "this label passage names that drug". It is a CANDIDATE evidence link for retrieval and for the
Verifier to check, not a claim that the pair interacts: severity only ever comes from the Interaction table.

Limits (be honest in the pitch): mentions are found by exact name/alias match (whole words, case-insensitive).
Drug classes ("NSAIDs", "anticoagulants"), brand names and misspellings are not detected; a class-level statement
can still be found by vector search but will not have a graph edge.
"""
import re
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Q

from apps.drugs.models import Drug
from apps.knowledge.models import Chunk, GraphEdge, KnowledgeDocument

REL_MENTIONS = "mentions"
REL_INTERACTS = "interacts_with"
REL_CONTRAINDICATED = "contraindicated_with"

# Label section -> drug-level relation (other sections only get the chunk-level `mentions` edge)
SECTION_RELATION = {"DRUG INTERACTIONS": REL_INTERACTS, "CONTRAINDICATIONS": REL_CONTRAINDICATED}
# Lower = more relevant for an interaction question
SECTION_PRIORITY = {
    "DRUG INTERACTIONS": 0,
    "CONTRAINDICATIONS": 1,
    "BOXED WARNING": 2,
    "WARNINGS AND CAUTIONS": 3,
    "WARNINGS": 3,
    "PRECAUTIONS": 4,
}
DEFAULT_SECTION_PRIORITY = 9
MIN_NAME_LEN = 4  # shorter names are too ambiguous to match in running text
MAX_NAME_WORDS = 4

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def section_rank(section: str) -> int:
    return SECTION_PRIORITY.get((section or "").strip().upper(), DEFAULT_SECTION_PRIORITY)


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def normalize_name(name: str) -> str:
    """'Warfarin-Sodium (oral)' -> 'warfarin sodium oral' (the form names are compared in)."""
    return " ".join(_tokens(name))


# ----------------------------------------------------------------------------------------------------------
# Finding drug names inside text
# ----------------------------------------------------------------------------------------------------------
@dataclass
class NameIndex:
    names: dict[str, int]  # normalized name or alias -> drug id (ambiguous names are left out)
    max_words: int


def build_name_index() -> NameIndex:
    owners: dict[str, set[int]] = {}
    for drug in Drug.objects.only("id", "generic_name", "aliases").iterator():
        for raw in [drug.generic_name, *(drug.aliases or [])]:
            if not isinstance(raw, str):
                continue
            name = normalize_name(raw)
            if len(name) >= MIN_NAME_LEN and len(name.split()) <= MAX_NAME_WORDS:
                owners.setdefault(name, set()).add(drug.id)
    names = {n: next(iter(ids)) for n, ids in owners.items() if len(ids) == 1}  # same name, two drugs: skip
    return NameIndex(names=names, max_words=max((len(n.split()) for n in names), default=1))


def find_mentions(text: str, index: NameIndex) -> set[int]:
    """Ids of every drug in `index` whose name or alias appears in `text` as whole words."""
    tokens = _tokens(text)
    found: set[int] = set()
    for n in range(1, index.max_words + 1):
        for i in range(len(tokens) - n + 1):
            drug_id = index.names.get(" ".join(tokens[i:i + n]))
            if drug_id is not None:
                found.add(drug_id)
    return found


def mentions_drug(text: str, drug: Drug) -> bool:
    """True when `text` names this drug (generic name or alias) as whole words."""
    haystack = f" {' '.join(_tokens(text))} "
    for raw in [drug.generic_name, *(drug.aliases or [])]:
        if not isinstance(raw, str):
            continue
        name = normalize_name(raw)
        if len(name) >= MIN_NAME_LEN and f" {name} " in haystack:
            return True
    return False


# ----------------------------------------------------------------------------------------------------------
# Building the graph
# ----------------------------------------------------------------------------------------------------------
def edges_for_document(document: KnowledgeDocument, index: NameIndex) -> list[GraphEdge]:
    """Unsaved GraphEdge objects for one document. Its own drug is never a target (a label names itself constantly)."""
    owner_id = document.drug_id
    edges: list[GraphEdge] = []
    for chunk in document.chunks.all():
        targets = find_mentions(chunk.text, index) - {owner_id}
        relation = SECTION_RELATION.get((chunk.section or "").strip().upper())
        for target in sorted(targets):
            edges.append(GraphEdge(src_type="chunk", src_id=chunk.id, relation=REL_MENTIONS,
                                   dst_type="drug", dst_id=target, chunk=chunk))
            if relation and owner_id:
                edges.append(GraphEdge(src_type="drug", src_id=owner_id, relation=relation,
                                       dst_type="drug", dst_id=target, chunk=chunk))
    return edges


def rebuild_edges(*, document_ids: list[int] | None = None) -> dict:
    """(Re)build graph edges. Idempotent: each document's old edges are deleted and rebuilt in one transaction."""
    index = build_name_index()
    documents = KnowledgeDocument.objects.select_related("drug").prefetch_related("chunks").order_by("id")
    if document_ids:
        documents = documents.filter(id__in=document_ids)
    else:
        # chunk edges whose chunk was deleted (SET_NULL) are orphans: drop them on a full rebuild
        GraphEdge.objects.filter(src_type="chunk", chunk__isnull=True).delete()

    stats = {"documents": 0, "chunks": 0, "mention_edges": 0, "pair_edges": 0, "known_names": len(index.names)}
    for document in documents:
        edges = edges_for_document(document, index)
        with transaction.atomic():
            GraphEdge.objects.filter(chunk__document=document).delete()
            GraphEdge.objects.bulk_create(edges, batch_size=1000)
        stats["documents"] += 1
        stats["chunks"] += len(document.chunks.all())
        stats["mention_edges"] += sum(1 for e in edges if e.relation == REL_MENTIONS)
        stats["pair_edges"] += sum(1 for e in edges if e.relation != REL_MENTIONS)
    return stats


# ----------------------------------------------------------------------------------------------------------
# Using the graph
# ----------------------------------------------------------------------------------------------------------
def neighbors(src_type: str, src_id: int, relation: str | None = None):
    qs = GraphEdge.objects.filter(src_type=src_type, src_id=src_id)
    return qs.filter(relation=relation) if relation else qs


def chunks_linking(drug_a_id: int, drug_b_id: int, *, limit: int = 10) -> list[Chunk]:
    """Graph hop for a drug pair: passages of A's label that name B, plus passages of B's label that name A.
    Most relevant sections first (DRUG INTERACTIONS, CONTRAINDICATIONS, warnings ...)."""
    mention_edges = GraphEdge.objects.filter(src_type="chunk", relation=REL_MENTIONS, dst_type="drug")
    linked = mention_edges.filter(
        Q(dst_id=drug_b_id, chunk__document__drug_id=drug_a_id)
        | Q(dst_id=drug_a_id, chunk__document__drug_id=drug_b_id)
    )
    chunk_ids = list(linked.values_list("chunk_id", flat=True).distinct())
    chunks = list(Chunk.objects.filter(id__in=chunk_ids).select_related("document", "document__drug"))
    chunks.sort(key=lambda c: (section_rank(c.section), c.id))
    return chunks[:limit]