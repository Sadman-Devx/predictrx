"""Stage 4 — STORE: load drugs, knowledge documents and text chunks into PostgreSQL.

Idempotent: running it again does not duplicate anything (documents are keyed by content_hash).
Embeddings are NOT created here (Day 5, RAG) — Chunk.embedding stays NULL.

Run:  python data/pipeline/load.py
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from common import PROCESSED_DIR, django_setup, read_jsonl, read_seed

SOURCE = "openfda_label"


def _parse_dt(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def seed_drugs(seed: list[dict]) -> int:
    """Make sure every seed drug exists (so autocomplete/resolver have targets even without a label)."""
    from apps.drugs.models import Drug

    created = 0
    for item in seed:
        drug, was_created = Drug.objects.get_or_create(generic_name=item["name"])
        merged = sorted(set(drug.aliases or []) | set(item["aliases"]))
        if merged != (drug.aliases or []):
            drug.aliases = merged
            drug.save(update_fields=["aliases"])
        created += was_created
    return created


def load_docs(docs: list[dict]) -> dict:
    from django.db import transaction

    from ai.rag.chunking import chunk_section
    from ai.rag.contextual import context_prefix
    from apps.drugs.models import Drug
    from apps.knowledge.models import Chunk, KnowledgeDocument

    stats = {"documents_new": 0, "documents_existing": 0, "chunks_new": 0}
    for doc in docs:
        drug, _ = Drug.objects.get_or_create(generic_name=doc["drug_name"])
        with transaction.atomic():
            kdoc, created = KnowledgeDocument.objects.get_or_create(
                content_hash=doc["content_hash"],
                defaults={
                    "source": SOURCE,
                    "drug": drug,
                    "title": f"{doc['drug_name']} label (set {doc.get('set_id', '')[:8]}, v{doc.get('version', '')})",
                    "source_url": doc.get("source_url", ""),
                    "license_note": doc.get("license_note", ""),
                    "fetched_at": _parse_dt(doc.get("fetched_at")),
                },
            )
            if not created:
                stats["documents_existing"] += 1
                continue
            stats["documents_new"] += 1
            chunks = []
            for title, text in doc["sections"].items():
                prefix = context_prefix(drug_name=doc["drug_name"], section=title, source=SOURCE)
                for piece in chunk_section(text):
                    chunks.append(Chunk(document=kdoc, section=title, text=piece, context_prefix=prefix,
                                        token_count=len(piece.split())))
            Chunk.objects.bulk_create(chunks)
            stats["chunks_new"] += len(chunks)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inp", type=Path, default=PROCESSED_DIR / "openfda_clean.jsonl")
    args = ap.parse_args()

    django_setup()
    created = seed_drugs(read_seed())
    stats = load_docs(read_jsonl(args.inp))
    print(f"drugs created: {created}")
    print(f"documents: +{stats['documents_new']} new, {stats['documents_existing']} already present")
    print(f"chunks: +{stats['chunks_new']} (embeddings are added later, on the RAG day)")


if __name__ == "__main__":
    main()