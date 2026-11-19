"""openapi.yaml must describe the code, and what feedback expects from batches must
be in services/batches/openapi.yaml (the contract across the seam). CI also
validates both documents against the OpenAPI specification."""
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from stub_batches import BATCHES

SERVICES = Path(__file__).resolve().parent.parent.parent
OWN = yaml.safe_load((SERVICES / "feedback" / "openapi.yaml").read_text())
BATCHES_DOC = yaml.safe_load((SERVICES / "batches" / "openapi.yaml").read_text())

REPORT = {"batch_code": "ros-2608", "rating": "4", "had_reaction": False, "comment": "ok"}


def assert_matches(body, schema_name, doc=OWN):
    resource = Resource.from_contents(doc, default_specification=DRAFT202012)
    registry = Registry().with_resource("urn:openapi", resource)
    schema = {"$ref": f"urn:openapi#/components/schemas/{schema_name}"}
    Draft202012Validator(schema, registry=registry, format_checker=FormatChecker()).validate(body)


def test_every_route_is_documented_and_nothing_else(client):
    in_code = {
        (method, rule.rule.replace("<", "{").replace(">", "}"))
        for rule in client.application.url_map.iter_rules() if rule.endpoint != "static"
        for method in rule.methods - {"HEAD", "OPTIONS"}
    }
    in_doc = {(method.upper(), path) for path, ops in OWN["paths"].items() for method in ops}
    assert in_code == in_doc


def test_responses_match_when_batches_answers(client):
    assert_matches(REPORT, "NewFeedback")
    created = client.post("/feedback", json=REPORT)
    assert created.status_code == 201
    assert_matches(created.get_json(), "BatchSummary")
    assert_matches(client.get("/feedback").get_json(), "SummaryList")
    assert_matches(client.get("/feedback/flagged").get_json(), "SummaryList")
    assert_matches(client.get("/feedback/ROS-2608").get_json(), "BatchSummary")
    assert_matches(client.get("/feedback/NOPE").get_json(), "Error")
    assert_matches(client.get("/health").get_json(), "HealthOk")


def test_responses_match_when_batches_is_down(client, batches_stub):
    client.post("/feedback", json=REPORT)
    batches_stub.stop()
    assert_matches(client.get("/feedback").get_json(), "SummaryList")
    assert_matches(client.get("/feedback/ROS-2608").get_json(), "BatchSummary")


# --- the seam: feedback's expectations against the batches document --------------

def test_the_endpoints_feedback_calls_exist_in_the_batches_document():
    assert "get" in BATCHES_DOC["paths"]["/batches"]
    assert "get" in BATCHES_DOC["paths"]["/batches/{batch_code}"]
    assert "404" in BATCHES_DOC["paths"]["/batches/{batch_code}"]["get"]["responses"]


def test_the_stub_answers_with_the_documented_batch_shape():
    # If batches changes its Batch schema, this fails and the stub must change too.
    for batch in BATCHES:
        assert_matches(batch, "Batch", doc=BATCHES_DOC)


def test_feedback_only_reads_fields_the_batches_document_promises():
    required = set(BATCHES_DOC["components"]["schemas"]["Batch"]["required"])
    assert {"batch_code", "product", "expires_on", "status"} <= required
