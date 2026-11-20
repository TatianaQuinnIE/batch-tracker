"""system.yaml must be valid against the course schema and must match the code.

Run from the repository root (CI's describe job runs it):
    pip install pytest==8.3.4 pyyaml==6.0.2 openapi-spec-validator==0.9.0
    pytest -v tests/test_system_description.py

The schema only checks the shape. These tests also check that what system.yaml says is
true of the code: the same services as docker-compose.yml, every environment variable
each service reads (and only those) with the same defaults, existing OpenAPI documents
and migration folders, and calls to endpoints that the called service documents.
"""
import json
import re
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = yaml.safe_load((ROOT / "system.yaml").read_text())
SCHEMA = json.loads((ROOT / "system.schema.json").read_text())
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
SERVICES = sorted(SYSTEM["services"])

# os.environ.get("NAME", "default") or os.environ["NAME"] in the service's own code.
ENV_READ = re.compile(
    r"""os\.environ(?:\.get\(\s*|\[)["']([A-Z][A-Z0-9_]*)["']"""  # the name
    r"""(?:\s*,\s*["']([^"']*)["'])?"""  # the default, if any
)


def env_read_by(service):
    """{name: default or None} for every variable the service's code reads (not its tests)."""
    folder = ROOT / SYSTEM["services"][service]["path"]
    found = {}
    for source in folder.rglob("*.py"):
        parts = source.relative_to(folder).parts
        # Skip the tests and anything local and untracked (.venv, __pycache__).
        if "tests" in parts or any(part.startswith((".", "__")) for part in parts[:-1]):
            continue
        for name, default in ENV_READ.findall(source.read_text()):
            found[name] = default or None
    return found


def openapi_endpoints(service):
    document = yaml.safe_load((ROOT / SYSTEM["services"][service]["openapi"]).read_text())
    return {f"{method.upper()} {path}" for path, item in document["paths"].items() for method in item}


def test_valid_against_the_course_schema():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    jsonschema.Draft202012Validator(SCHEMA).validate(SYSTEM)


def test_names_follow_the_prefix():
    prefix = SYSTEM["prefix"]
    assert prefix == SYSTEM["student"].replace(".", "-")
    assert SYSTEM["ui"]["storage_account"].startswith(prefix.replace("-", "") + "ui")
    assert SYSTEM["azure"]["resource_group"] == f"rg-{prefix}"
    for name in ("container_apps_environment", "sql_server"):
        assert SYSTEM["azure"][name].startswith(prefix)
    for name, service in SYSTEM["services"].items():
        assert service["azure"]["container_app"] == f"{prefix}-{name}"
        assert service["azure"]["sql_database"] == f"{prefix}-{name}-db"


def test_public_url_is_the_storage_static_website():
    storage = re.escape(SYSTEM["ui"]["storage_account"])
    assert re.fullmatch(rf"https://{storage}\.z\d+\.web\.core\.windows\.net/?", SYSTEM["public_url"])


def test_same_services_as_compose():
    # db, db-init and ui in compose are infrastructure, not domain services.
    domain = {name for name, svc in COMPOSE["services"].items() if "build" in svc}
    assert domain == set(SYSTEM["services"])
    assert set(SYSTEM["ui"]["calls"]) <= set(SYSTEM["services"])


@pytest.mark.parametrize("service", SERVICES)
def test_paths_exist(service):
    described = SYSTEM["services"][service]
    assert (ROOT / described["path"] / "Dockerfile").is_file()
    assert (ROOT / described["openapi"]).is_file()
    assert sorted((ROOT / described["migrations"]).glob("*.sql")), "no migration files"


@pytest.mark.parametrize("service", SERVICES)
def test_env_is_exactly_what_the_code_reads(service):
    assert set(SYSTEM["services"][service]["env"]) == set(env_read_by(service))


@pytest.mark.parametrize("service", SERVICES)
def test_env_defaults_match_the_code(service):
    code = env_read_by(service)
    for name, var in SYSTEM["services"][service]["env"].items():
        if var.get("secret"):
            continue
        assert str(var["default"]) == code[name], name
    assert SYSTEM["services"][service]["port_default"] == int(code["PORT"])


@pytest.mark.parametrize("service", SERVICES)
def test_calls_use_documented_endpoints(service):
    described = SYSTEM["services"][service]
    for call in described.get("calls", []):
        assert call["service"] in SYSTEM["services"]
        assert call["url_env"] in described["env"]
        assert set(call["endpoints"]) <= openapi_endpoints(call["service"])
    timeout_env = {c["service"]: f"{c['service'].upper()}_TIMEOUT_S" for c in described.get("calls", [])}
    for call in described.get("calls", []):
        default = described["env"].get(timeout_env[call["service"]], {}).get("default")
        if default is not None:
            assert float(default) == call["timeout_s"]
