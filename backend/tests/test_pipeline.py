"""Tests for data/pipeline using a hand-made fixture (synthetic text, NOT real label content)."""
import json
import sys
from pathlib import Path

import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[2] / "data" / "pipeline"
sys.path.insert(0, str(PIPELINE_DIR))

import clean  # noqa: E402
import parse_labels  # noqa: E402
from common import read_seed  # noqa: E402

FIXTURE = PIPELINE_DIR / "fixtures" / "openfda_sample_warfarin.json"


def parsed_docs():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [
        parse_labels.parse_result(r, query_name=payload["query_name"], aliases=payload["aliases"],
                                  fetched_at=payload["fetched_at"])
        for r in payload["results"]
    ]


def test_seed_file_parses_and_has_aliases():
    seed = {d["name"]: d["aliases"] for d in read_seed()}
    assert "acetaminophen" in seed and "paracetamol" in seed["acetaminophen"]
    assert all(n == n.lower() for n in seed)


def test_parse_keeps_named_sections_and_skips_missing_fields():
    docs = parsed_docs()
    assert set(docs[0]["sections"]) == {"DRUG INTERACTIONS", "WARNINGS", "CONTRAINDICATIONS"}
    assert docs[3]["sections"] == {}  # label with no usable field
    assert docs[0]["source_url"].endswith('"00000000-aaaa-bbbb-cccc-000000000001"')


def test_salt_stripping_and_single_ingredient_rule():
    assert clean.strip_salt("WARFARIN SODIUM") == "warfarin"
    assert clean.is_single_ingredient_for("warfarin", [], ["WARFARIN SODIUM"])
    assert not clean.is_single_ingredient_for("warfarin", [], ["WARFARIN SODIUM", "SOMETHING ELSE"])
    assert clean.is_single_ingredient_for("acetaminophen", ["paracetamol"], ["PARACETAMOL"])
    assert not clean.is_single_ingredient_for("warfarin", [], [])


def test_clean_drops_combo_empty_and_duplicate_and_adds_licence():
    cleaned, dropped = clean.clean_docs(parsed_docs())
    assert len(cleaned) == 1
    assert dropped["not_single_ingredient_for_seed"] == 1
    assert dropped["no_usable_sections"] == 1
    assert dropped["duplicate"] == 1
    assert "CC0" in cleaned[0]["license_note"]
    assert len(cleaned[0]["content_hash"]) == 64


@pytest.mark.django_db
def test_load_is_idempotent_and_chunks_have_no_embedding():
    import load
    from apps.drugs.models import Drug
    from apps.knowledge.models import Chunk, KnowledgeDocument

    cleaned, _ = clean.clean_docs(parsed_docs())
    first = load.load_docs(cleaned)
    assert first["documents_new"] == 1 and first["chunks_new"] >= 3  # long section is split into several chunks
    second = load.load_docs(cleaned)
    assert second["documents_new"] == 0 and second["documents_existing"] == 1 and second["chunks_new"] == 0

    assert Drug.objects.filter(generic_name="warfarin").count() == 1
    doc = KnowledgeDocument.objects.get()
    assert doc.source == "openfda_label" and "CC0" in doc.license_note
    assert Chunk.objects.filter(embedding__isnull=False).count() == 0
    assert Chunk.objects.filter(section="DRUG INTERACTIONS").count() >= 2


@pytest.mark.django_db
def test_seed_and_report_counts():
    import load
    import report

    created = load.seed_drugs(read_seed())
    assert created == len(read_seed())
    assert load.seed_drugs(read_seed()) == 0  # second call creates nothing
    r = report.build_report()
    assert r["drugs_total"] == len(read_seed())
    assert r["drugs_with_documents"] == 0 and r["interactions_total"] == 0


# ---------------------------------------------------------------- DDInter (synthetic fixture)
DDINTER_FIXTURE = PIPELINE_DIR / "fixtures" / "ddinter"


def ddinter_parsed():
    import parse_interactions

    files = sorted(DDINTER_FIXTURE.glob("ddinter_downloads_code_*.csv"))
    return parse_interactions.parse_files(files)


def test_ddinter_parse_collapses_duplicates_and_drops_bad_rows():
    drugs, pairs, stats = ddinter_parsed()
    assert stats["rows"] == 6
    assert stats["duplicate_rows_collapsed"] == 1      # Examplol/Testadine appears in both files (reversed)
    assert stats["dropped_bad_level"] == 1             # "Bogus"
    assert len(pairs) == 4 and len(drugs) == 5
    ex_test = next(p for p in pairs if {p["id_a"], p["id_b"]} == {"DDInter9001", "DDInter9002"})
    assert ex_test["level"] == "major" and sorted(ex_test["files"]) == ["A", "B"]
    assert all(p["id_a"] < p["id_b"] for p in pairs)   # unordered pair stored in one canonical order


@pytest.mark.django_db
def test_ddinter_load_merges_aliases_keeps_variants_and_is_idempotent():
    import load
    import load_ddinter
    from apps.drugs.models import Drug, Interaction

    load.seed_drugs(read_seed())  # creates 'albuterol' with alias 'salbutamol'
    drugs, pairs, _ = ddinter_parsed()
    first = load_ddinter.load(drugs, pairs)
    assert first["interactions_added"] == 4

    albuterol = Drug.objects.get(generic_name="albuterol")      # "Salbutamol" merged into the seed drug
    assert "salbutamol" in albuterol.aliases and albuterol.external_ids["ddinter"] == ["DDInter9003"]
    assert not Drug.objects.filter(generic_name="salbutamol").exists()
    assert Drug.objects.filter(generic_name="fakemycin").exists()
    assert Drug.objects.filter(generic_name="fakemycin (topical)").exists()   # formulation stays separate

    for ix in Interaction.objects.filter(source="ddinter"):
        assert ix.drug_a_id < ix.drug_b_id and ix.mechanism == "" and "non-commercial" in ix.license_note
    assert Interaction.objects.filter(severity="unknown").count() == 1

    again = load_ddinter.load(drugs, pairs)
    assert again["interactions_added"] == 0 and Interaction.objects.count() == 4
    replaced = load_ddinter.load(drugs, pairs, replace=True)
    assert replaced["interactions_after"] == 4