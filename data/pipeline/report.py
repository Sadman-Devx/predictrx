"""Stage 5 — ANALYTICS: coverage report of what is in the database.

Run:  python data/pipeline/report.py
"""
from common import django_setup


def build_report() -> dict:
    from django.db.models import Count

    from apps.drugs.models import Drug, Interaction
    from apps.knowledge.models import Chunk, KnowledgeDocument

    drugs_total = Drug.objects.count()
    with_docs = Drug.objects.filter(documents__isnull=False).distinct().count()
    with_ix_section = (
        Drug.objects.filter(documents__chunks__section="DRUG INTERACTIONS").distinct().count()
    )
    return {
        "drugs_total": drugs_total,
        "drugs_with_documents": with_docs,
        "drugs_without_documents": sorted(
            Drug.objects.filter(documents__isnull=True).values_list("generic_name", flat=True)
        ),
        "drugs_with_interactions_section": with_ix_section,
        "documents_by_source": dict(
            KnowledgeDocument.objects.values_list("source").annotate(n=Count("id")).order_by("source")
        ),
        "chunks_total": Chunk.objects.count(),
        "chunks_without_embedding": Chunk.objects.filter(embedding__isnull=True).count(),
        "chunks_by_section": dict(
            Chunk.objects.values_list("section").annotate(n=Count("id")).order_by("-n")
        ),
        "interactions_by_source_severity": [
            {"source": s, "severity": sev, "count": n}
            for s, sev, n in Interaction.objects.values_list("source", "severity")
            .annotate(n=Count("id")).order_by("source", "severity")
        ],
        "interactions_total": Interaction.objects.count(),
    }


def main() -> None:
    django_setup()
    r = build_report()
    print("=== PredictRx data coverage ===")
    print(f"drugs: {r['drugs_total']}  (with a label document: {r['drugs_with_documents']}, "
          f"with a DRUG INTERACTIONS section: {r['drugs_with_interactions_section']})")
    print(f"documents by source: {r['documents_by_source'] or 'none'}")
    print(f"chunks: {r['chunks_total']}  (without embedding: {r['chunks_without_embedding']})")
    for section, n in r["chunks_by_section"].items():
        print(f"  {section or '(no section)'}: {n}")
    print(f"interaction records: {r['interactions_total']}")
    for row in r["interactions_by_source_severity"]:
        print(f"  {row['source']} / {row['severity']}: {row['count']}")
    if not r["interactions_total"]:
        print("  (none yet — DDInter not loaded)")
    missing = r["drugs_without_documents"]
    if missing:
        print(f"drugs without any label document ({len(missing)}): {', '.join(missing)}")


if __name__ == "__main__":
    main()