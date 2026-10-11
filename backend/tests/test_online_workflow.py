import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.tests.test_api_modes import settings, write_registry
from backend.tests.test_context_capabilities import protocol_registry


@pytest.mark.parametrize("mode", ["precomputed", "validation"])
def test_removed_modes_cannot_create_records_even_with_registered_assets(tmp_path, mode):
    protocol_registry(tmp_path)
    app = create_app(settings(tmp_path, gpu_available=True, worker_enabled=False))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            json={
                "cell_line": "K562",
                "perturbation": "MYC",
                "mode": mode,
            },
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "EXPERIMENT_MODE_REMOVED"
        assert client.get("/api/v1/runs").json()["total"] == 0


def test_catalog_only_advertises_online_targets(tmp_path):
    protocol_registry(tmp_path)
    app = create_app(settings(tmp_path, worker_enabled=False))
    with TestClient(app) as client:
        context = client.get("/api/v1/catalog/contexts").json()[0]
        assert context["validation_ready"] is False
        assert context["precomputed_ready"] is False
        for mode in ("precomputed", "validation"):
            assert (
                client.get(f"/api/v1/catalog/perturbations?cell_line=K562&mode={mode}").json()["items"] == []
            )
        assert client.get("/api/v1/catalog/perturbations?cell_line=K562").json()["items"] == ["MYC"]


def test_online_still_checks_worker_availability(tmp_path):
    write_registry(tmp_path, valid=True)
    with TestClient(create_app(settings(tmp_path, worker_enabled=False))) as client:
        response = client.post("/api/v1/runs", json={"cell_line": "K562", "perturbation": "MYC"})
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "WORKER_UNAVAILABLE"
