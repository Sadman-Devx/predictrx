import pytest

from apps.drugs import services
from apps.drugs.models import BrandMapping, Drug

pytestmark = pytest.mark.django_db
RESOLVE, SEARCH = "/api/medications/resolve/", "/api/drugs/search/"


@pytest.fixture
def seeded():
    d = Drug.objects.create(generic_name="acetaminophen", aliases=["paracetamol"])
    BrandMapping.objects.create(brand_name="Napa", strength="500 mg", drug=d, source="sample", confidence="0.95")
    services.invalidate_cache()


def test_requires_auth(api_client):
    assert api_client.post(RESOLVE, {"items": [{"name": "Napa"}]}, format="json").status_code == 401
    assert api_client.get(SEARCH, {"q": "na"}).status_code == 401


def test_typing_napa_returns_a_generic_with_confidence(seeded, doctor, auth_client):
    r = auth_client(doctor).post(RESOLVE, {"items": [{"name": "Napa 500"}, {"name": "Unknownbrand"}]}, format="json")
    assert r.status_code == 200
    first, second = r.json()["results"]
    assert first["generic"] == "acetaminophen" and first["confidence"] == 0.95 and first["verified"] is False
    assert first["match_type"] == "exact" and first["source"] == "sample"
    assert second["status"] == "unresolved" and second["reason"] == "no_match"


@pytest.mark.parametrize("body", [{}, {"items": []}, {"items": [{"name": ""}]}, {"items": [{"name": "x"}] * 31}])
def test_resolve_validation(doctor, auth_client, body):
    r = auth_client(doctor).post(RESOLVE, body, format="json")
    assert r.status_code == 400 and "error" in r.json()


def test_search(seeded, doctor, auth_client):
    c = auth_client(doctor)
    assert c.get(SEARCH, {"q": "nap"}).json()["results"][0]["name"] == "Napa"
    assert c.get(SEARCH, {"q": "n"}).status_code == 400
    assert c.get(SEARCH, {"q": "nap", "limit": 99}).status_code == 400
