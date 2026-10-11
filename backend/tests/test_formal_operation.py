from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.schemas import CreateRunRequest
from backend.tests.historical_bundle import _create_precomputed_run
from backend.tests.test_api_runs import _settings, _write_registry
from backend.tests.test_system_integration import write_bundle


def test_formal_mode_excludes_synthetic_catalog_and_rejects_creation(tmp_path: Path):
    _write_registry(tmp_path)
    write_bundle(tmp_path)
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        assert app.state.container.settings.allow_synthetic_results is False
        assert client.get("/api/v1/catalog/contexts").json()[0]["precomputed_ready"] is False
        catalog = client.get("/api/v1/catalog/perturbations?cell_line=K562&mode=precomputed")
        assert catalog.json()["items"] == []
        response = client.post(
            "/api/v1/runs", json={"cell_line": "K562", "perturbation": "MYC", "mode": "precomputed"}
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "EXPERIMENT_MODE_REMOVED"
        assert client.get("/api/v1/runs").json()["total"] == 0
        assert not app.state.container.settings.derived_root.exists()


def test_formal_mode_preserves_readable_historical_synthetic_records(tmp_path: Path):
    _write_registry(tmp_path)
    source = write_bundle(tmp_path)
    original = (source / "manifest.json").read_bytes()
    app = create_app(_settings(tmp_path, allow_synthetic_results=True))
    with TestClient(app) as client:
        response = _create_precomputed_run(
            CreateRunRequest(cell_line="K562", perturbation="MYC", mode="precomputed"), app.state.container
        )
        run_id = response.run_id
        app.state.container.settings.allow_synthetic_results = False
        assert client.get(f"/api/v1/runs/{run_id}").json()["result_kind"] == "synthetic_demo"
        assert client.get(f"/api/v1/runs/{run_id}/summary").status_code == 200
        provenance = client.get(f"/api/v1/runs/{run_id}/provenance").json()
        assert provenance["source_type"] == "synthetic_precomputed"
        catalog = client.get("/api/v1/catalog/perturbations?cell_line=K562&mode=precomputed").json()
        assert catalog["items"] == []
        assert (source / "manifest.json").read_bytes() == original
