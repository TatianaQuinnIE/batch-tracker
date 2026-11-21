"""openapi.yaml must describe the code: the same routes, and the real responses
must match the documented schemas. CI also validates the document itself against
the OpenAPI specification."""
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

DOC = yaml.safe_load((Path(__file__).resolve().parent.parent / "openapi.yaml").read_text())
RESOURCE = Resource.from_contents(DOC, default_specification=DRAFT202012)
REGISTRY = Registry().with_resource("urn:openapi", RESOURCE)


def assert_matches(body, schema_name):
    schema = {"$ref": f"urn:openapi#/components/schemas/{schema_name}"}
    Draft202012Validator(schema, registry=REGISTRY, format_checker=FormatChecker()).validate(body)


def test_every_route_is_documented_and_nothing_else(client):
    in_code = {
        (method, rule.rule.replace("<", "{").replace(">", "}"))
        for rule in client.application.url_map.iter_rules() if rule.endpoint != "static"
        for method in rule.methods - {"HEAD", "OPTIONS"}
    }
    in_doc = {(method.upper(), path) for path, ops in DOC["paths"].items() for method in ops}
    assert in_code == in_doc


def test_health_matches(client):
    assert_matches(client.get("/health").get_json(), "HealthOk")


def test_list_and_one_batch_match(client):
    batches = client.get("/batches").get_json()
    assert batches, "seed.json should have loaded"
    for batch in batches:
        assert_matches(batch, "Batch")
    assert_matches(client.get(f"/batches/{batches[0]['batch_code']}").get_json(), "Batch")


def test_create_matches(client):
    body = {"batch_code": "doc-1", "product": "Doc soap", "produced_on": "2026-10-01",
            "expires_on": "2027-10-01", "quantity": "12"}
    assert_matches(body, "NewBatch")
    response = client.post("/batches", json=body)
    assert response.status_code == 201
    assert_matches(response.get_json(), "Batch")


def test_recall_matches(client):
    assert_matches({"reason": "Leaking caps"}, "Recall")
    response = client.post("/batches/LAV-2607/recall", json={"reason": "Leaking caps"})
    assert_matches(response.get_json(), "Batch")


def test_a_batch_without_the_002_fields_is_still_valid():
    """What a revision from before migration 002 answers during a rollout (ADR-10)."""
    assert_matches({"batch_code": "LAV-2607", "product": "Lavender soap bar",
                    "produced_on": "2026-07-01", "expires_on": "2027-07-01",
                    "quantity": 120, "status": "ok"}, "Batch")


@pytest.mark.parametrize("path", ["/batches/NOPE"])
def test_errors_match(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert_matches(response.get_json(), "Error")
