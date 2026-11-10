"""The OpenAPI schema is what the frontend generates its client from: it must build and describe the Day 3 routes."""
import io

import pytest
import yaml
from django.core.management import call_command


@pytest.fixture(scope="module")
def schema(django_db_blocker):
    out = io.StringIO()
    err = io.StringIO()
    call_command("spectacular", "--validate", stdout=out, stderr=err)
    return yaml.safe_load(out.getvalue()), err.getvalue()


def test_schema_contains_the_drug_and_interaction_routes(schema):
    paths = schema[0]["paths"]
    for route in ("/api/drugs/", "/api/drugs/{id}/", "/api/interactions/", "/api/interactions/{id}/"):
        assert route in paths, route
        assert set(paths[route]) == {"get"}  # read-only


def test_schema_has_no_warnings_or_errors_for_the_whole_project(schema):
    """Same bar as `manage.py spectacular --validate --fail-on-warn`: every view is described."""
    assert schema[1].strip() == "", schema[1]


def test_interaction_schema_always_lists_source_fields(schema):
    props = schema[0]["components"]["schemas"]["Interaction"]["properties"]
    assert {"source", "source_ref", "license_note", "severity"} <= set(props)
    assert "required" in schema[0]["components"]["schemas"]["Interaction"]


def test_routes_are_tagged_and_jwt_protected(schema):
    op = schema[0]["paths"]["/api/interactions/"]["get"]
    assert op["tags"] == ["Interactions"] and op["security"]