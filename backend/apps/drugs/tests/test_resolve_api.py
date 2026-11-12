import sys
from datetime import date
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.drugs import services
from apps.drugs.models import BrandMapping, Drug, Interaction

PIPELINE_DIR = Path(__file__).resolve().parents[4] / "data" / "pipeline"
sys.path.insert(0, str(PIPELINE_DIR))
import load_brands as brand_loader  # noqa: E402

RESOLVE_URL = "/api/medications/resolve/"
SEARCH_URL = "/api/drugs/search/"
DRUGS_URL = "/api/drugs/"
INTERACTIONS_URL = "/api/interactions/"


@pytest.fixture
def client(db):
    cache.clear()
    user = get_user_model().objects.create_user(
        email="doc1@example.com", password="pass12345", role="doctor"
    )
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def brands(db):
    para = Drug.objects.create(generic_name="paracetamol")
    cipro = Drug.objects.create(generic_name="ciprofloxacin")
    BrandMapping.objects.create(
        brand_name="Napa", strength="500 mg", drug=para,
        source="test", source_ref="https://example.test/napa", source_accessed=date(2026, 11, 12),
        verified=True, confidence=0.98,
    )
    BrandMapping.objects.create(
        brand_name="Ciprocin", strength="500 mg", drug=cipro,
        source="test", verified=False, confidence=0.90,
    )
    ibuprofen = Drug.objects.create(generic_name="ibuprofen")
    BrandMapping.objects.create(
        brand_name="Lowbrand", drug=ibuprofen, source="test", verified=False, confidence=0.50,
    )


def _resolve(client, *names):
    res = client.post(RESOLVE_URL, {"items": [{"name": name} for name in names]}, format="json")
    assert res.status_code == 200
    return res.json()["results"]


def test_requires_auth(db):
    assert APIClient().post(RESOLVE_URL, {"items": ["Napa"]}, format="json").status_code == 401
    assert APIClient().get(SEARCH_URL, {"q": "nap"}).status_code == 401
    assert APIClient().get(DRUGS_URL).status_code == 401
    assert APIClient().get(INTERACTIONS_URL).status_code == 401


def test_exact_brand_with_strength(client, brands):
    (r,) = _resolve(client, "Tab. Napa 500mg")
    assert r["status"] == "resolved"
    assert r["match_type"] == "exact"
    assert r["generic"] == "paracetamol"
    assert r["verified"] is True
    assert r["source_ref"] == "https://example.test/napa"
    assert r["source_accessed"] == "2026-11-12"


def test_generic_input_resolves(client, brands):
    (r,) = _resolve(client, "Paracetamol")
    assert r["status"] == "resolved"
    assert r["match_type"] == "generic"


def test_unknown_is_unresolved_never_guessed(client, brands):
    (r,) = _resolve(client, "Xyzabc")
    assert r["status"] == "unresolved"
    assert r.get("generic") is None
    assert r["reason"] == "no_match"


def test_fuzzy_accepts_close_unambiguous_typo(client, brands):
    (r,) = _resolve(client, "Ciprocinn")
    assert r["status"] == "resolved"
    assert r["match_type"] == "fuzzy"
    assert r["generic"] == "ciprofloxacin"


def test_low_confidence_fuzzy_match_returns_candidates_not_a_guess(client, brands):
    (r,) = _resolve(client, "Lowbrandd")
    assert r["status"] == "unresolved"
    assert r["reason"] == "low_confidence"
    assert r["candidates"] == ["ibuprofen"]


def test_validation_empty_list(client, brands):
    res = client.post(RESOLVE_URL, {"items": []}, format="json")
    assert res.status_code == 400


def test_search_prefix_and_generic(client, brands):
    res = client.get(SEARCH_URL, {"q": "nap"})
    labels = [i["name"] for i in res.json()["results"]]
    assert labels[0].startswith("Napa")
    assert res.json()["results"][0]["source_ref"] == "https://example.test/napa"
    assert res.json()["results"][0]["source_accessed"] == "2026-11-12"
    res = client.get(SEARCH_URL, {"q": "parace"})
    assert res.json()["results"][0]["type"] == "generic"


def test_brand_loader_requires_and_persists_traceable_sources(db, tmp_path):
    Drug.objects.create(generic_name="paracetamol")
    csv_path = tmp_path / "brands.csv"
    csv_path.write_text(
        "brand_name,generic_name,source,source_ref,source_accessed,verified,confidence\n"
        "Napa,paracetamol,manufacturer-label,https://example.test/napa,2026-11-12,false,0.8\n"
        "Uncited,paracetamol,draft,,2026-11-12,false,0.5\n",
        encoding="utf-8",
    )

    parsed = brand_loader.load_rows(csv_path)
    assert len(parsed["ok"]) == 1
    assert any("missing source_ref" in error[2] for error in parsed["errors"])
    assert brand_loader.save(parsed) == {"created": 1, "updated": 0}
    mapping = BrandMapping.objects.get(brand_name="Napa")
    assert mapping.source_ref == "https://example.test/napa"
    assert mapping.source_accessed == date(2026, 11, 12)
    assert services.resolve_brand("Napa")["source_accessed"] == "2026-11-12"


def test_read_only_drug_and_interaction_routes(client, brands):
    drug = Drug.objects.get(generic_name="paracetamol")
    drug_response = client.get(DRUGS_URL)
    assert drug_response.status_code == 200
    assert drug_response.json()["results"][0]["generic_name"] == "ciprofloxacin"
    assert client.get(f"{DRUGS_URL}{drug.pk}/").json()["generic_name"] == "paracetamol"

    other = Drug.objects.get(generic_name="ciprofloxacin")
    interaction = Interaction.objects.create(
        drug_a=drug,
        drug_b=other,
        severity="major",
        source="test",
        source_ref="test-record",
        license_note="synthetic test data",
    )
    interaction_response = client.get(INTERACTIONS_URL)
    assert interaction_response.status_code == 200
    assert interaction_response.json()["results"][0]["source_ref"] == "test-record"
    detail = client.get(f"{INTERACTIONS_URL}{interaction.pk}/")
    assert detail.status_code == 200
    assert detail.json()["severity"] == "major"


def test_search_short_query_is_rejected(client, brands):
    assert client.get(SEARCH_URL, {"q": "n"}).status_code == 400