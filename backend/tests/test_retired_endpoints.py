import json

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


@pytest.fixture
def client(tmp_path):
    registry = tmp_path / "data/registry"
    registry.mkdir(parents=True)
    for filename, key in (("models.json", "models"), ("datasets.json", "datasets")):
        (registry / filename).write_text(json.dumps({key: []}))
    dist = tmp_path / "frontend/dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html>CellLens</html>")
    app = create_app(
        Settings(
            _env_file=None,
            project_root=tmp_path,
            database_url=f"sqlite+pysqlite:///{tmp_path / 'test.db'}",
            create_database_schema=True,
            worker_enabled=False,
        )
    )
    return TestClient(app)


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/login"),
        ("GET", "/analyses/ana_" + "a" * 32),
        ("GET", "/api/v1/data-capabilities"),
        ("GET", "/api/v1/datasets/ds_" + "a" * 32),
        ("POST", "/api/v1/analyses"),
        ("GET", "/api/v1/analyses/ana_" + "a" * 32),
    ],
)
def test_retired_routes_are_unavailable(client, method, path):
    assert client.request(method, path).status_code == 404


def test_public_contract_only_exposes_current_workflows(client):
    schema = client.get("/openapi.json").json()
    assert not any(
        path.startswith(("/api/v1/analyses", "/api/v1/data-capabilities")) for path in schema["paths"]
    )
    status = client.get("/api/v1/system-status").json()
    assert not any(key.startswith("upload") for key in status["workers"])
    assert "limits" not in status
    assert client.get("/api/v1/experiments").json()["items"] == []
    assert client.get("/api/v1/experiments?source=upload").status_code == 422


def test_dataset_library_reuses_path_without_restoring_arbitrary_uploads(client):
    assert client.get("/datasets").status_code == 200
    catalog = client.get("/api/v1/datasets")
    assert catalog.status_code == 200
    assert catalog.json()["items"][0]["status"] == "needs_preparation"
    assert (
        client.post("/api/v1/datasets", json={"url": "https://example.org/private.h5ad"}).status_code == 405
    )
    schema = client.get("/openapi.json").json()["paths"]
    assert set(schema["/api/v1/datasets"]) == {"get"}
    assert "/api/v1/datasets/{dataset_id}/conditions" in schema
    assert "/api/v1/datasets/{dataset_id}/analyses" in schema
    assert client.get("/api/v1/datasets/unregistered/conditions").status_code == 404


def test_assistant_and_coverage_reject_retired_sources(client):
    assert (
        client.get(
            "/api/v1/assistant/context",
            params={
                "source_kind": "analysis",
                "source_id": "ana_" + "a" * 32,
            },
        ).status_code
        == 422
    )
    assert client.get("/api/v1/coverage?analysis_id=ana_" + "a" * 32).status_code == 422
