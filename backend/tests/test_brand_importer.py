"""Tests for provenance validation and non-destructive brand-mapping imports."""
import sys
from pathlib import Path

import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[2] / "data" / "pipeline"
sys.path.insert(0, str(PIPELINE_DIR))

import load_brands  # noqa: E402
from apps.drugs.models import BrandMapping, Drug  # noqa: E402


@pytest.mark.django_db
def test_import_rejects_self_verified_rows_and_preserves_unchanged_review(tmp_path):
    drug = Drug.objects.create(generic_name="metformin")
    file = tmp_path / "brands.csv"
    file.write_text(
        "brand_name,strength,dosage_form,generic_name,source,source_ref,source_accessed,verified,confidence\n"
        "Goodbrand,500mg,tablet,metformin,official label,https://example.test/record,2026-11-12,false,0.80\n"
        "Claimed,500mg,tablet,metformin,official label,https://example.test/record,2026-11-12,true,0.80\n",
        encoding="utf-8",
    )

    parsed = load_brands.load_rows(file)
    assert len(parsed["ok"]) == 1
    assert len(parsed["errors"]) == 1
    assert "only be set after review" in parsed["errors"][0][2]
    assert load_brands.save(parsed) == {"created": 1, "updated": 0}

    mapping = BrandMapping.objects.get(brand_name="Goodbrand", drug=drug)
    assert mapping.verified is False
    mapping.verified = True
    mapping.save(update_fields=["verified"])

    assert load_brands.save(load_brands.load_rows(file)) == {"created": 0, "updated": 0}
    mapping.refresh_from_db()
    assert mapping.verified is True

    file.write_text(file.read_text(encoding="utf-8").replace(
        "https://example.test/record", "https://example.test/updated-record", 1
    ), encoding="utf-8")
    assert load_brands.save(load_brands.load_rows(file)) == {"created": 0, "updated": 1}
    mapping.refresh_from_db()
    assert mapping.verified is False
