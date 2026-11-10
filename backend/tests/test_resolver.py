"""Resolver / lookup / check_interaction / API / MCP tests. All drug data below is SYNTHETIC test data
(fictional drugs, invented severities) — no real clinical claims."""
import asyncio
import json
import sys
from pathlib import Path

import pytest
from rest_framework.test import APIClient

REPO = Path(__file__).resolve().parents[2]
PIPELINE_DIR = REPO / "data" / "pipeline"
sys.path.insert(0, str(PIPELINE_DIR))
sys.path.insert(0, str(REPO / "mcp-server"))

import clean  # noqa: E402
import load  # noqa: E402
import load_brands  # noqa: E402
import load_ddinter  # noqa: E402
import parse_interactions  # noqa: E402
from common import read_seed  # noqa: E402

from apps.accounts.models import User  # noqa: E402
from apps.drugs import names, services  # noqa: E402
from apps.drugs.models import BrandMapping, Drug  # noqa: E402
from apps.knowledge.models import Chunk, KnowledgeDocument  # noqa: E402

DDINTER_FIXTURE = PIPELINE_DIR / "fixtures" / "ddinter"


def build_world():
    """Seed drugs + synthetic DDInter pairs + brand rows + one label chunk."""
    services.clear_index_cache()
    load.seed_drugs(read_seed())
    drugs, pairs, _ = parse_interactions.parse_files(sorted(DDINTER_FIXTURE.glob("ddinter_downloads_code_*.csv")))
    load_ddinter.load(drugs, pairs)
    d = lambda n: Drug.objects.get(generic_name=n)  # noqa: E731
    BrandMapping.objects.create(brand_name="Examplebrand", strength="500mg", dosage_form="tablet",
                                drug=d("acetaminophen"), source="synthetic test", verified=True, confidence=1)
    BrandMapping.objects.create(brand_name="Dualbrand", drug=d("metformin"), source="synthetic test", confidence=0.5)
    BrandMapping.objects.create(brand_name="Dualbrand", drug=d("ibuprofen"), source="synthetic test", confidence=0.5)
    BrandMapping.objects.create(brand_name="Unverbrand", drug=d("ibuprofen"), source="synthetic test", confidence=0.6)
    doc = KnowledgeDocument.objects.create(source="openfda_label", drug=d("examplol"), title="synthetic",
                                           fetched_at="2026-11-09T00:00:00Z", content_hash="x" * 64)
    Chunk.objects.create(document=doc, section="DRUG INTERACTIONS",
                         text="SYNTHETIC TEST TEXT. Use caution when examplol is combined with testadine because of a "
                              "made-up effect.")
    services.clear_index_cache()


@pytest.fixture(autouse=True)
def _fresh_index():
    services.clear_index_cache()
    yield
    services.clear_index_cache()


@pytest.fixture
def world(db):
    build_world()


# ------------------------------------------------------------------ names
def test_parse_input_splits_strength_and_form_words():
    assert names.parse_input("Napa 500mg tab") == {"text": "napa", "strength": "500mg"}
    assert names.parse_input("Napa 500") == {"text": "napa", "strength": "500"}
    assert names.parse_input("  Paracetamol   500 mg Tablet ") == {"text": "paracetamol", "strength": "500mg"}
    assert names.parse_input("diclofenac (topical)")["text"] == "diclofenac (topical)"  # parentheses are kept
    assert names.parse_input("") == {"text": "", "strength": None}


def test_backend_and_pipeline_normalisers_agree():
    for sample in ["WARFARIN SODIUM", "Metformin Hydrochloride", "valproic acid", "Lithium Carbonate", "ibuprofen"]:
        assert names.strip_salt(sample) == clean.strip_salt(sample)
        assert names.normalize_name(sample) == clean.normalize_name(sample)


# ------------------------------------------------------------------ resolve
def test_resolves_generic_alias_and_salt_form(world):
    assert services.resolve_name("acetaminophen")["method"] == "generic_name"
    r = services.resolve_name("Paracetamol 500mg tab")
    assert r["status"] == "resolved" and r["generic"] == "acetaminophen" and r["method"] == "alias"
    assert r["parsed"]["strength"] == "500mg"
    r = services.resolve_name("Metformin Hydrochloride")
    assert r["status"] == "resolved" and r["generic"] == "metformin" and r["method"] == "salt_stripped"
    assert r["confidence"] < 1


def test_resolves_brand_from_sheet_and_flags_unverified(world):
    r = services.resolve_name("Examplebrand 500mg")
    assert r["status"] == "resolved" and r["generic"] == "acetaminophen"
    assert r["method"] == "brand_mapping" and r["verified"] is True and r["notes"] == []
    u = services.resolve_name("unverbrand")
    assert u["status"] == "resolved" and u["verified"] is False and u["notes"]


def test_ambiguous_brand_is_never_guessed(world):
    r = services.resolve_name("Dualbrand")
    assert r["status"] == "unresolved" and r["reason"] == "ambiguous"
    assert {c["generic_name"] for c in r["candidates"]} == {"metformin", "ibuprofen"}


def test_typo_gives_suggestions_but_not_a_match(world):
    r = services.resolve_name("metforminn")
    assert r["status"] == "unresolved" and r["reason"] == "not_found"
    assert r["suggestions"] and r["suggestions"][0]["generic_name"] == "metformin"
    assert services.resolve_name("   ")["reason"] == "empty"
    assert services.resolve_name("zzzzqqq")["suggestions"] == []


def test_formulation_in_brackets_is_never_dropped_silently(world):
    r = services.resolve_name("ibuprofen (topical)")  # no such drug row exists -> must NOT map to plain ibuprofen
    assert r["status"] == "unresolved" and r["reason"] == "not_found"
    assert "ibuprofen" in {s["generic_name"] for s in r["suggestions"]}


def test_formulation_variants_stay_separate(world):
    assert services.resolve_name("fakemycin")["generic"] == "fakemycin"
    assert services.resolve_name("fakemycin (topical)")["generic"] == "fakemycin (topical)"


# ------------------------------------------------------------------ lookup
def test_lookup_drug_found_and_not_found(world):
    r = services.lookup_drug("salbutamol")
    assert r["status"] == "found" and r["drug"]["generic_name"] == "albuterol" and "salbutamol" in r["aliases"]
    assert r["sources"]["interaction_records"] == 1
    f = services.lookup_drug("fakemycin")
    assert f["formulation_variants"] == ["fakemycin (topical)"]
    assert services.lookup_drug("notadrugatall")["status"] == "not_found"


# ------------------------------------------------------------------ check_interaction
def test_check_interaction_found_is_order_independent_and_cites_evidence(world):
    a = services.check_interaction("examplol", "testadine")
    b = services.check_interaction("Testadine", "EXAMPLOL")
    assert a["status"] == "found" and a["severity"] == "major"
    assert a["evidence"] and a["evidence"][0]["type"] == "interaction" and a["evidence"][0]["source"] == "ddinter"
    assert a["records"][0]["mechanism"] == "" and "non-commercial" in a["records"][0]["license_note"]
    assert {x["id"] for x in a["evidence"]} == {x["id"] for x in b["evidence"]}


def test_check_interaction_uses_aliases(world):
    r = services.check_interaction("salbutamol", "examplol")  # alias of the seed drug albuterol
    assert r["status"] == "found" and r["severity"] == "minor"
    assert "albuterol" in {r["drug_a"]["generic_name"], r["drug_b"]["generic_name"]}


def test_no_record_is_not_safe(world):
    r = services.check_interaction("examplol", "metformin")
    assert r["status"] == "no_record" and r["severity"] is None and r["evidence"] == []
    assert "not mean the combination is safe" in r["note"]


def test_unknown_severity_is_flagged_not_safe(world):
    r = services.check_interaction("testadine", "fakemycin (topical)")
    assert r["status"] == "found" and r["severity"] == "unknown" and "not evidence" in r["note"]


def test_unresolved_and_same_drug_inputs(world):
    r = services.check_interaction("examplol", "testadinee")
    assert r["status"] == "unresolved_input" and r["unresolved"][0]["suggestions"]
    assert services.check_interaction("examplol", "Examplol")["status"] == "invalid"


def test_label_mentions_give_snippet_with_chunk_evidence(world):
    r = services.check_interaction("examplol", "testadine")
    m = r["label_mentions"]
    assert m and "testadine" in m[0]["snippet"].lower()
    assert m[0]["evidence"]["type"] == "chunk" and m[0]["evidence"]["source"] == "openfda_label"
    assert services.check_interaction("examplol", "testadine", include_labels=False).get("label_mentions") is None


def test_check_interactions_for_a_medication_list(world):
    r = services.check_interactions(["examplol", "testadine", "fakemycin (topical)", "nonsensedrug", "Testadine"])
    assert [d["generic_name"] for d in r["drugs"]] == ["examplol", "testadine", "fakemycin (topical)"]  # dedup kept order
    assert len(r["unresolved"]) == 1 and r["unresolved"][0]["input"] == "nonsensedrug"
    assert len(r["pairs"]) == 3
    assert r["summary"] == {"major": 1, "moderate": 0, "minor": 0, "unknown": 1, "no_record": 1}


# ------------------------------------------------------------------ brand sheet loader
def test_brand_loader_validates_strictly_and_is_idempotent(world, tmp_path):
    f = tmp_path / "brands.csv"
    f.write_text(
        "brand_name,strength,dosage_form,generic_name,source,verified,confidence\n"
        "Goodbrand,250mg,tablet,metformin,synthetic test,false,0.8\n"
        "Nosource,,,metformin,,false,0.8\n"
        "Badgeneric,,,notadrug,synthetic test,false,0.8\n"
        "Badconf,,,metformin,synthetic test,false,2\n"
        "Badflag,,,metformin,synthetic test,maybe,0.5\n", encoding="utf-8")
    parsed = load_brands.load_rows(f)
    assert len(parsed["ok"]) == 1 and len(parsed["errors"]) == 4
    assert any("missing source" in e[2] for e in parsed["errors"])
    assert load_brands.save(parsed) == {"created": 1, "updated": 0}
    assert load_brands.save(load_brands.load_rows(f)) == {"created": 0, "updated": 1}
    assert BrandMapping.objects.get(brand_name="Goodbrand").verified is False


# ------------------------------------------------------------------ REST API
def _client():
    user = User.objects.create_user(email="doc@example.com", password="x", role="doctor")
    c = APIClient()
    c.force_authenticate(user)
    return c


def test_api_requires_login(world):
    assert APIClient().post("/api/medications/resolve/", {"items": ["x"]}, format="json").status_code == 401


def test_api_resolve_search_and_check(world):
    c = _client()
    r = c.post("/api/medications/resolve/", {"items": ["Examplebrand 500mg", "metforminn"]}, format="json")
    assert r.status_code == 200
    res = r.json()["results"]
    assert res[0]["status"] == "resolved" and res[1]["status"] == "unresolved"

    s = c.get("/api/drugs/search/", {"q": "examp"}).json()["results"]
    assert {"examplol", "examplebrand"} <= {x["text"].lower() for x in s}
    assert c.get("/api/drugs/search/", {"q": "e"}).json()["results"] == []  # too short to search

    k = c.post("/api/interactions/check/", {"drugs": ["examplol", "testadine"]}, format="json")
    assert k.status_code == 200 and k.json()["pairs"][0]["severity"] == "major"
    bad = c.post("/api/interactions/check/", {"drugs": ["only-one"]}, format="json")
    assert bad.status_code == 400 and "error" in bad.json()


# ------------------------------------------------------------------ MCP tools (async, real DB)
def _call(server, tool, args):
    res = asyncio.run(server.mcp.call_tool(tool, args))
    if isinstance(res, tuple):
        res = res[0]
    return json.loads(res[0].text)


@pytest.mark.django_db(transaction=True)
def test_mcp_tools_answer_from_the_database():
    build_world()
    import server  # mcp-server/server.py

    assert _call(server, "resolve_brand", {"brand": "Examplebrand 500mg"})["generic"] == "acetaminophen"
    assert _call(server, "lookup_drug", {"generic_name": "salbutamol"})["drug"]["generic_name"] == "albuterol"
    found = _call(server, "check_interaction", {"drug_a": "examplol", "drug_b": "testadine"})
    assert found["status"] == "found" and found["severity"] == "major"
    assert _call(server, "check_interaction", {"drug_a": "examplol", "drug_b": "metformin"})["status"] == "no_record"
    many = _call(server, "check_interactions", {"drugs": ["examplol", "testadine"]})
    assert many["summary"]["major"] == 1