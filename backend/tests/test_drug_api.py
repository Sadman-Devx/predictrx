import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.knowledge.models import KnowledgeDocument

from .factories import DrugFactory, make_interaction

pytestmark = pytest.mark.django_db


def count_queries(client, url):
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
    assert response.status_code == 200
    return len(ctx)


@pytest.fixture
def client(auth_client, doctor):
    return auth_client(doctor)


@pytest.fixture
def pair():
    a, b = DrugFactory(generic_name="alphadrug", aliases=["alpha-alias"]), DrugFactory(generic_name="betadrug")
    return a, b


# ---------- access ----------


@pytest.mark.parametrize("url", ["/api/drugs/", "/api/drugs/1/", "/api/interactions/", "/api/interactions/1/"])
def test_anonymous_gets_401_in_the_standard_error_shape(api_client, url):
    response = api_client.get(url)
    assert response.status_code == 401
    assert set(response.json()["error"]) >= {"code", "message"}


def test_family_users_are_not_allowed(auth_client, make_user, pair):
    assert auth_client(make_user("family")).get("/api/drugs/").status_code == 403
    assert auth_client(make_user("family")).get("/api/interactions/").status_code == 403


def test_pharmacist_is_allowed(auth_client, make_user):
    assert auth_client(make_user("pharmacist")).get("/api/drugs/").status_code == 200


def test_api_is_read_only(client, pair):
    assert client.post("/api/drugs/", {"generic_name": "x"}).status_code == 405
    assert client.delete(f"/api/drugs/{pair[0].id}/").status_code == 405
    assert client.post("/api/interactions/", {}).status_code == 405


# ---------- drugs ----------


def test_drug_list_is_paginated_sorted_and_searchable(client, pair):
    data = client.get("/api/drugs/").json()
    assert data["count"] == 2
    assert [d["generic_name"] for d in data["results"]] == ["alphadrug", "betadrug"]
    assert data["results"][0]["aliases"] == ["alpha-alias"]
    found = client.get("/api/drugs/?search=BETA").json()
    assert [d["generic_name"] for d in found["results"]] == ["betadrug"]


def test_drug_detail_lists_knowledge_sources(client, pair):
    KnowledgeDocument.objects.create(source="openfda_label", drug=pair[0], title="t", fetched_at=timezone.now(), content_hash="h" * 64)
    body = client.get(f"/api/drugs/{pair[0].id}/").json()
    assert body["sources"] == ["openfda_label"] and body["generic_name"] == "alphadrug"
    assert client.get(f"/api/drugs/{pair[1].id}/").json()["sources"] == []


def test_unknown_drug_is_404_and_search_path_is_not_swallowed_as_an_id(client):
    assert client.get("/api/drugs/999999/").status_code == 404
    assert client.get("/api/drugs/search/").status_code == 404  # reserved for the Day 4 route


# ---------- interactions ----------


def test_interaction_exposes_source_and_license_with_nested_drugs(client, pair):
    ix = make_interaction(*pair, severity="major", mechanism="synthetic", source="ddinter")
    body = client.get(f"/api/interactions/{ix.id}/").json()
    assert body["severity"] == "major" and body["source"] == "ddinter"
    assert body["source_ref"] == "synthetic" and body["license_note"] == "synthetic test data"
    assert {body["drug_a"]["generic_name"], body["drug_b"]["generic_name"]} == {"alphadrug", "betadrug"}
    assert set(body["drug_a"]) == {"id", "generic_name"}


def test_interaction_filters(client, pair):
    c = DrugFactory(generic_name="gammadrug")
    make_interaction(pair[0], pair[1], severity="major", source="ddinter")
    make_interaction(pair[0], c, severity="minor", source="other")
    make_interaction(pair[1], c, severity="minor", source="ddinter")

    def total(query):
        return client.get(f"/api/interactions/?{query}").json()["count"]

    assert total("severity=major") == 1
    assert total("source=DDINTER") == 2
    assert total(f"drug={pair[0].id}") == 2
    assert total(f"drug={c.id}") == 2  # matches whichever side the drug is stored on
    assert total(f"drug={c.id}&severity=minor&source=ddinter") == 1


def test_bad_filter_values_are_400_in_the_error_shape(client):
    for query in ("severity=catastrophic", "drug=abc"):
        response = client.get(f"/api/interactions/?{query}")
        assert response.status_code == 400 and "error" in response.json()


def test_list_query_count_does_not_grow_with_rows(client):
    drugs = [DrugFactory() for _ in range(8)]
    for i in range(4):
        make_interaction(drugs[i], drugs[i + 1])
    few = count_queries(client, "/api/interactions/?page_size=100")
    for i in range(4):
        make_interaction(drugs[i], drugs[i + 3 if i + 3 < 8 else 7], source="second")
    many = count_queries(client, "/api/interactions/?page_size=100")
    assert few == many


def test_drug_detail_query_count_is_constant(client):
    a, b = DrugFactory(), DrugFactory()
    for drug, n in ((a, 1), (b, 6)):
        for i in range(n):
            KnowledgeDocument.objects.create(source="openfda_label", drug=drug, title="t", fetched_at=timezone.now(), content_hash=f"{drug.id}-{i}".ljust(64, "0"))
    assert count_queries(client, f"/api/drugs/{a.id}/") == count_queries(client, f"/api/drugs/{b.id}/")