import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.drugs.models import BrandMapping, Drug

RESOLVE_URL = "/api/medications/resolve/"
SEARCH_URL = "/api/drugs/search/"


@pytest.fixture
def client(db):
    cache.clear()
    user = get_user_model().objects.create_user(
        username="doc1", email="doc1@example.com", password="pass12345", role="doctor"
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
        source="test", verified=True, confidence=0.98,
    )
    BrandMapping.objects.create(
        brand_name="Ciprocin", strength="500 mg", drug=cipro,
        source="test", verified=False, confidence=0.90,
    )


def _resolve(client, *names):
    res = client.post(RESOLVE_URL, {"items": list(names)}, format="json")
    assert res.status_code == 200
    return res.json()["results"]


def test_requires_auth(db):
    assert APIClient().post(RESOLVE_URL, {"items": ["Napa"]}, format="json").status_code == 401
    assert APIClient().get(SEARCH_URL, {"q": "nap"}).status_code == 401


def test_exact_brand_with_strength(client, brands):
    (r,) = _resolve(client, "Tab. Napa 500mg")
    assert r["status"] == "resolved"
    assert r["match_type"] == "exact"
    assert r["generic"]["name"] == "paracetamol"
    assert r["verified"] is True


def test_generic_input_resolves(client, brands):
    (r,) = _resolve(client, "Paracetamol")
    assert r["status"] == "resolved"
    assert r["match_type"] == "generic"


def test_unknown_is_unresolved_never_guessed(client, brands):
    (r,) = _resolve(client, "Xyzabc")
    assert r["status"] == "unresolved"
    assert r["generic"] is None
    assert r["reason"] == "not_found"


def test_fuzzy_accepts_close_unambiguous_typo(client, brands):
    (r,) = _resolve(client, "Ciprocinn")
    assert r["status"] == "resolved"
    assert r["match_type"] == "fuzzy"
    assert r["generic"]["name"] == "ciprofloxacin"


def test_near_miss_returns_suggestions_not_a_guess(client, brands):
    (r,) = _resolve(client, "Napaa")
    assert r["status"] == "unresolved"
    assert r["reason"] == "low_confidence"
    assert r["suggestions"][0]["brand_name"] == "Napa"


def test_validation_empty_list(client, brands):
    res = client.post(RESOLVE_URL, {"items": []}, format="json")
    assert res.status_code == 400


def test_search_prefix_and_generic(client, brands):
    res = client.get(SEARCH_URL, {"q": "nap"})
    labels = [i["label"] for i in res.json()["results"]]
    assert labels[0].startswith("Napa")
    res = client.get(SEARCH_URL, {"q": "parace"})
    assert res.json()["results"][0]["type"] == "generic"


def test_search_short_query_returns_empty(client, brands):
    assert client.get(SEARCH_URL, {"q": "n"}).json()["results"] == []