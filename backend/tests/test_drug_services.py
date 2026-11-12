"""Loader + name-matching tests (synthetic data only)."""
import pytest

from apps.drugs import services
from apps.drugs.models import BrandMapping, Drug, Interaction

from .factories import DrugFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def drugs():
    return {
        "alpha": DrugFactory(generic_name="alphadrug", aliases=["alpha-alias", "Alpha Intl"]),
        "beta": DrugFactory(generic_name="betadrug", aliases=["shared-alias"]),
        "gamma": DrugFactory(generic_name="gammadrug", aliases=["shared-alias"]),
    }


def row(a="alphadrug", b="betadrug", severity="Moderate", **extra):
    return {"drug_a_name": a, "drug_b_name": b, "severity": severity, "source": "ddinter", "source_ref": "test-ref", **extra}


# ---------- name matching ----------


def test_normalize_name():
    assert services.normalize_name("  Alpha   DRUG ") == "alpha drug"
    assert services.normalize_name(None) == ""


def test_name_index_generic_alias_and_ambiguity(drugs):
    index = services.build_name_index()
    assert index["alphadrug"] == drugs["alpha"].id
    assert index["alpha-alias"] == drugs["alpha"].id
    assert index["alpha intl"] == drugs["alpha"].id  # alias is normalized
    assert index["shared-alias"] is None  # claimed by two drugs: never guessed
    assert services.resolve_drug_id("shared-alias", index) == (None, "ambiguous_drug_name")
    assert services.resolve_drug_id("nope", index) == (None, "unknown_drug")
    assert services.resolve_drug_id("  ", index) == (None, "missing_drug_name")


def test_generic_name_beats_an_alias_with_the_same_text():
    first = DrugFactory(generic_name="onedrug")
    DrugFactory(generic_name="twodrug", aliases=["onedrug"])
    assert services.build_name_index()["onedrug"] == first.id


# ---------- interactions ----------


def test_pair_is_stored_in_canonical_order_whichever_way_it_arrives(drugs):
    stats = services.import_interactions([row(a="betadrug", b="alphadrug")])
    assert stats.created == 1
    ix = Interaction.objects.get()
    assert ix.drug_a_id < ix.drug_b_id
    assert {ix.drug_a_id, ix.drug_b_id} == {drugs["alpha"].id, drugs["beta"].id}


def test_load_is_idempotent(drugs):
    rows = [row(), row(a="alphadrug", b="gammadrug", severity="Major")]
    first = services.import_interactions(rows)
    second = services.import_interactions(rows)
    assert (first.created, first.updated) == (2, 0)
    assert (second.created, second.updated) == (0, 2)
    assert Interaction.objects.count() == 2


def test_reload_refreshes_changed_values_without_duplicating(drugs):
    services.import_interactions([row(severity="Minor")])
    services.import_interactions([row(severity="Major", mechanism="synthetic mechanism")])
    ix = Interaction.objects.get()
    assert ix.severity == "major" and ix.mechanism == "synthetic mechanism"


def test_a_b_and_b_a_collapse_and_the_more_severe_level_wins(drugs):
    stats = services.import_interactions([row(severity="Minor"), row(a="betadrug", b="alphadrug", severity="Major")])
    assert Interaction.objects.count() == 1
    assert Interaction.objects.get().severity == "major"
    assert stats.notes["severity_conflict_resolved"] == 1


def test_identical_duplicate_rows_are_counted_not_doubled(drugs):
    stats = services.import_interactions([row(), row(a="betadrug", b="alphadrug")])
    assert Interaction.objects.count() == 1
    assert stats.notes["duplicate_in_input"] == 1


def test_bad_rows_are_skipped_and_counted_never_invented(drugs):
    before = Drug.objects.count()
    rows = [
        row(a="alphadrug", b="not-a-known-drug"),
        row(a="shared-alias", b="alphadrug"),
        row(a="alphadrug", b="alpha-alias"),  # same drug twice
        {**row(), "source": ""},
        {**row(), "source": "othersource"},  # unknown source and no license_note
        row(a="", b="betadrug"),
    ]
    stats = services.import_interactions(rows)
    assert stats.created == 0 and Interaction.objects.count() == 0
    assert dict(stats.skipped) == {
        "unknown_drug": 1,
        "ambiguous_drug_name": 1,
        "self_interaction": 1,
        "missing_source": 1,
        "missing_license_note": 1,
        "missing_drug_name": 1,
    }
    assert Drug.objects.count() == before  # nothing was auto-created


def test_unexpected_severity_becomes_unknown_never_upgraded(drugs):
    stats = services.import_interactions([row(severity="catastrophic")])
    assert Interaction.objects.get().severity == "unknown"
    assert stats.notes["severity_normalized_to_unknown"] == 1


def test_every_row_keeps_source_and_license(drugs):
    services.import_interactions([row()])  # no license_note in the row -> ddinter default
    ix = Interaction.objects.get()
    assert ix.source == "ddinter" and ix.source_ref == "test-ref"
    assert "CC BY-NC-SA" in ix.license_note


def test_over_long_fields_are_rejected_not_truncated(drugs):
    stats = services.import_interactions([row(license_note="x" * 500)])
    assert stats.skipped["field_too_long"] == 1 and Interaction.objects.count() == 0


def test_dry_run_reports_but_writes_nothing(drugs):
    stats = services.import_interactions([row()], dry_run=True)
    assert stats.created == 1 and stats.dry_run
    assert Interaction.objects.count() == 0


def test_small_batches_give_the_same_result(drugs):
    stats = services.import_interactions(
        [row(), row(a="alphadrug", b="gammadrug"), row(a="betadrug", b="gammadrug")], batch_size=1
    )
    assert stats.created == 3 and Interaction.objects.count() == 3


# ---------- brand mappings ----------


def brand(**extra):
    return {"brand_name": "Testbrand", "strength": "500 mg", "dosage_form": "tablet", "generic_name": "alphadrug",
            "source": "team-sheet", "confidence": "0.9", **extra}


def test_brand_rows_are_always_unverified_even_if_the_file_says_otherwise(drugs):
    stats = services.import_brand_mappings([brand(verified="true")])
    bm = BrandMapping.objects.get()
    assert stats.created == 1 and bm.verified is False
    assert bm.drug_id == drugs["alpha"].id and str(bm.confidence) == "0.90"


def test_brand_load_is_idempotent_and_never_unverifies_a_reviewed_row(drugs):
    services.import_brand_mappings([brand()])
    BrandMapping.objects.update(verified=True)  # pharmacist review in admin
    second = services.import_brand_mappings([brand()])
    assert second.created == 0 and second.notes["existing_left_unchanged"] == 1
    assert BrandMapping.objects.get().verified is True


def test_brand_rows_without_source_or_unknown_generic_are_skipped(drugs):
    stats = services.import_brand_mappings(
        [brand(source=""), brand(generic_name="nodrug"), brand(brand_name=""), brand(confidence="7"), brand(confidence="abc")]
    )
    assert stats.created == 0 and BrandMapping.objects.count() == 0
    assert dict(stats.skipped) == {
        "missing_source": 1, "unknown_drug": 1, "missing_brand_name": 1, "bad_confidence": 2,
    }


def test_same_brand_pointing_at_two_generics_is_loaded_but_flagged(drugs):
    stats = services.import_brand_mappings([brand(), brand(generic_name="betadrug")])
    assert BrandMapping.objects.count() == 2
    assert stats.notes["same_brand_multiple_generics"] == 1


def test_brand_dry_run_writes_nothing(drugs):
    stats = services.import_brand_mappings([brand()], dry_run=True)
    assert stats.created == 1 and BrandMapping.objects.count() == 0


# ---------- readers ----------


def test_ddinter_csv_reader_maps_header_case_insensitively(tmp_path):
    f = tmp_path / "ddinter_downloads_code_X.csv"
    f.write_text("DDInterID_A,Drug_A,DDInterID_B,Drug_B,Level\nD1,AlphaDrug,D2,BetaDrug,Major\n", encoding="utf-8")
    [r] = list(services.iter_rows(f, "ddinter-csv"))
    assert r == {"drug_a_name": "AlphaDrug", "drug_b_name": "BetaDrug", "severity": "Major",
                 "source": "ddinter", "source_ref": "DDInter 2.0 file: ddinter_downloads_code_X.csv"}


def test_ddinter_csv_with_unexpected_header_fails_loudly(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="header not recognised"):
        list(services.iter_rows(f, "ddinter-csv"))


def test_directory_input_reads_every_matching_file_sorted(tmp_path):
    (tmp_path / "b.jsonl").write_text('{"n": 2}\n', encoding="utf-8")
    (tmp_path / "a.jsonl").write_text('{"n": 1}\n\n', encoding="utf-8")
    assert [r["n"] for r in services.iter_rows(tmp_path, "jsonl")] == [1, 2]


def test_invalid_json_line_names_the_file_and_line(tmp_path):
    f = tmp_path / "x.jsonl"
    f.write_text('{"ok": 1}\nnot json\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"x\.jsonl:2"):
        list(services.iter_rows(f, "jsonl"))


# ---------- coverage report (data/pipeline/report.py) ----------


def test_coverage_report_lists_license_notes_and_flags_missing_ones(drugs):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data" / "pipeline"))
    import report

    services.import_interactions([row()])
    r = report.build_report()
    assert r["interactions_total"] == 1 and r["interactions_missing_license"] == 0
    assert {(x["table"], x["source"]) for x in r["license_notes_by_source"]} == {("interaction", "ddinter")}
    assert "CC BY-NC-SA" in r["license_notes_by_source"][0]["license_note"]