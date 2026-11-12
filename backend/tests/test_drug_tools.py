"""resolve_brand / lookup_drug / check_interaction / search — the deterministic tools (Day 4)."""
from datetime import datetime, timezone

import pytest

from apps.drugs import services
from apps.drugs.models import BrandMapping, Drug, Interaction
from apps.knowledge.models import KnowledgeDocument

pytestmark = pytest.mark.django_db


@pytest.fixture
def catalog():
    para = Drug.objects.create(generic_name="acetaminophen", aliases=["paracetamol"])
    omep = Drug.objects.create(generic_name="omeprazole")
    esom = Drug.objects.create(generic_name="esomeprazole")
    warf = Drug.objects.create(generic_name="warfarin")
    asp = Drug.objects.create(generic_name="aspirin", aliases=["acetylsalicylic acid"])
    BrandMapping.objects.create(brand_name="Napa", strength="500 mg", drug=para, source="sample", confidence="0.95")
    BrandMapping.objects.create(brand_name="Napa", strength="120 mg", drug=para, source="sample", confidence="0.90")
    BrandMapping.objects.create(brand_name="Seclo", strength="20 mg", drug=omep, source="sample",
                                confidence="0.95", verified=True)
    BrandMapping.objects.create(brand_name="Losectil", drug=omep, source="sample", confidence="0.95",
                                verified=True)
    BrandMapping.objects.create(brand_name="Ciprocina", drug=esom, source="sample", confidence="0.95")
    BrandMapping.objects.create(brand_name="Ciprocinb", drug=omep, source="sample", confidence="0.95")  # rival
    BrandMapping.objects.create(brand_name="Vitamin B12", drug=asp, source="sample", confidence="0.80")
    BrandMapping.objects.create(brand_name="Dup", drug=omep, source="sample", confidence="0.9")
    BrandMapping.objects.create(brand_name="Dup", drug=esom, source="sample", confidence="0.9")
    BrandMapping.objects.create(brand_name="Weakx", drug=omep, source="sample", confidence="0.40")
    services.invalidate_cache()
    return {"para": para, "omep": omep, "esom": esom, "warf": warf, "asp": asp}


class TestResolveBrand:
    def test_napa_resolves_with_basis(self, catalog):
        r = services.resolve_brand("Napa")
        assert r["status"] == "resolved" and r["generic"] == "acetaminophen"
        assert r["confidence"] == 0.95 and r["match_type"] == "exact"
        assert r["source"] == "sample" and r["verified"] is False
        assert "paracetamol" in r["aliases"]

    @pytest.mark.parametrize("text", ["napa 500", "NAPA 500mg", "Tab. Napa 500 mg", "Napa-500", "napa500", "Napa 500 tablet"])
    def test_common_prescription_spellings(self, catalog, text):
        r = services.resolve_brand(text)
        assert r["generic"] == "acetaminophen" and r["strength_matched"] is True, r

    def test_unlisted_strength_still_resolves_but_is_flagged(self, catalog):
        r = services.resolve_brand("Napa 650")
        assert r["status"] == "resolved" and r["strength_matched"] is False

    def test_strength_unit_conversion(self, catalog):
        assert services.resolve_brand("Napa", "0.5 g")["strength_matched"] is True

    def test_verified_flag_comes_from_the_row(self, catalog):
        assert services.resolve_brand("Seclo 20")["verified"] is True

    def test_digits_inside_a_brand_name_are_kept(self, catalog):
        assert services.resolve_brand("Vitamin B12")["generic"] == "aspirin"

    def test_generic_and_alias_resolve_as_generic_match(self, catalog):
        for name in ("paracetamol", "Acetaminophen"):
            r = services.resolve_brand(name)
            assert r["generic"] == "acetaminophen" and r["match_type"] == "generic"

    def test_unknown_is_unresolved_never_guessed(self, catalog):
        r = services.resolve_brand("Zzqxyw 10")
        assert r == {"status": "unresolved", "input": "Zzqxyw 10", "reason": "no_match"}

    def test_typo_is_fuzzy_and_never_verified(self, catalog):
        r = services.resolve_brand("Losectl")  # Losectil is verified=True, a typo-match must not inherit that
        assert r["status"] == "resolved" and r["match_type"] == "fuzzy" and r["verified"] is False
        assert r["confidence"] <= services.FUZZY_CONFIDENCE_CAP and r["matched_name"] == "Losectil"

    def test_one_typo_in_a_five_letter_name_is_too_risky_to_guess(self, catalog):
        assert services.resolve_brand("Seclu")["status"] == "unresolved"

    def test_short_names_are_never_fuzzy_matched(self, catalog):
        assert services.resolve_brand("Nap")["status"] == "unresolved"

    def test_near_tie_between_two_drugs_is_ambiguous(self, catalog):
        r = services.resolve_brand("Ciprocinx")  # equally close to two brands that map to different drugs
        assert r["status"] == "unresolved" and r["reason"] == "ambiguous"
        assert set(r["candidates"]) == {"esomeprazole", "omeprazole"}

    def test_same_brand_two_drugs_is_ambiguous(self, catalog):
        r = services.resolve_brand("Dup")
        assert r["status"] == "unresolved" and r["reason"] == "ambiguous"

    def test_low_confidence_row_is_unresolved(self, catalog):
        r = services.resolve_brand("Weakx")
        assert r["status"] == "unresolved" and r["reason"] == "low_confidence"

    @pytest.mark.parametrize("bad", ["", "   ", None])
    def test_empty_input(self, catalog, bad):
        assert services.resolve_brand(bad)["reason"] == "empty_input"

    def test_overlong_input(self, catalog):
        assert services.resolve_brand("a" * 500)["reason"] == "input_too_long"

    def test_cache_is_invalidated_when_data_changes(self, catalog):
        assert services.resolve_brand("Newbrand")["status"] == "unresolved"
        BrandMapping.objects.create(brand_name="Newbrand", drug=catalog["omep"], source="sample", confidence="0.9")
        assert services.resolve_brand("Newbrand")["generic"] == "omeprazole"  # signal bumped the version


class TestLookupDrug:
    def test_found_with_sources_and_brands(self, catalog):
        KnowledgeDocument.objects.create(source="openfda_label", drug=catalog["para"], title="label", source_url="u",
                                         license_note="CC0", fetched_at=datetime.now(timezone.utc), content_hash="h1")
        r = services.lookup_drug("Paracetamol")  # alias, any case
        assert r["status"] == "found" and r["generic_name"] == "acetaminophen"
        assert r["brand_names"] == ["Napa"] and r["document_count"] == 1
        assert r["sources"][0]["source"] == "openfda_label"

    def test_known_drug_without_documents_is_still_found_with_empty_sources(self, catalog):
        r = services.lookup_drug("warfarin")
        assert r["status"] == "found" and r["sources"] == []

    def test_brand_names_are_not_generics(self, catalog):
        assert services.lookup_drug("Napa") == {"status": "not_found", "input": "Napa"}


class TestCheckInteraction:
    def _ix(self, a, b, severity="major", source="ddinter"):
        x, y = Interaction.canonical(a.id, b.id)
        return Interaction.objects.create(drug_a_id=x, drug_b_id=y, severity=severity, mechanism="m",
                                          management="g", source=source, source_ref="r", license_note="NC")

    def test_found_in_either_order(self, catalog):
        self._ix(catalog["warf"], catalog["asp"])
        ab = services.check_interaction("warfarin", "aspirin")
        ba = services.check_interaction("Acetylsalicylic acid", "WARFARIN")
        assert ab["status"] == ba["status"] == "found" and ab["severity"] == "major"
        assert (ab["drug_a"], ab["drug_b"]) == ("warfarin", "aspirin")
        assert (ba["drug_a"], ba["drug_b"]) == ("aspirin", "warfarin")  # oriented to the caller, even from cache

    def test_no_record_never_claims_safe(self, catalog):
        r = services.check_interaction("warfarin", "omeprazole")
        assert r["status"] == "no_record" and r["reason"] == "no_interaction_record"
        assert "does not mean the combination is safe" in r["note"]
        assert "safe" not in {v for v in r.values() if isinstance(v, str) and v == "safe"}

    def test_unknown_drug_is_no_record_with_reason(self, catalog):
        r = services.check_interaction("warfarin", "notadrug")
        assert r["status"] == "no_record" and r["reason"] == "drug_not_found" and r["unknown_drugs"] == ["notadrug"]

    def test_same_drug_and_bad_input(self, catalog):
        assert services.check_interaction("warfarin", "warfarin")["reason"] == "same_drug"
        assert services.check_interaction("", "warfarin")["reason"] == "invalid_input"

    def test_multiple_sources_keep_the_conflict_visible(self, catalog):
        self._ix(catalog["warf"], catalog["asp"], "moderate", "ddinter")
        self._ix(catalog["warf"], catalog["asp"], "major", "other")
        r = services.check_interaction("warfarin", "aspirin")
        assert r["severity"] == "major" and r["severity_conflict"] is True
        assert r["other_records"][0]["severity"] == "moderate"

    def test_brand_names_are_not_accepted(self, catalog):
        assert services.check_interaction("Napa", "warfarin")["reason"] == "drug_not_found"


class TestSearch:
    def test_ranking_and_types(self, catalog):
        res = services.search_drugs("na")
        assert res[0]["name"] == "Napa" and res[0]["type"] == "brand"

    def test_generic_alias_found(self, catalog):
        names = [r["name"] for r in services.search_drugs("parac")]
        assert "paracetamol" in names

    def test_too_short_returns_nothing_and_limit_applies(self, catalog):
        assert services.search_drugs("n") == []
        assert len(services.search_drugs("pr", limit=2)) <= 2
