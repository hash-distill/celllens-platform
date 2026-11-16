import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.schemas import CreateRunRequest, RunStatus, RunSummary


def _write_registry(root: Path) -> None:
    registry = root / "data" / "registry"
    registry.mkdir(parents=True)
    (registry / "models.json").write_text(
        json.dumps(
            {
                "models": [
                    {
                        "id": "state-test",
                        "cell_line": "K562",
                        "enabled": True,
                        "supported_perturbations": ["MYC"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (registry / "datasets.json").write_text(
        json.dumps({"datasets": [{"id": "data-test", "cell_line": "K562", "enabled": True}]}),
        encoding="utf-8",
    )


def _settings(tmp_path: Path, **kwargs) -> Settings:
    return Settings(
        project_root=tmp_path,
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'test.db').as_posix()}",
        create_database_schema=True,
        **kwargs,
    )


def test_create_run_does_not_leave_a_queued_job_without_worker(tmp_path: Path):
    _write_registry(tmp_path)
    app = create_app(_settings(tmp_path, gpu_available=True, worker_enabled=False))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            json={"cell_line": "K562", "perturbation": "myc", "mode": "online", "n_cells": 128},
        )
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "WORKER_UNAVAILABLE"


def test_create_run_rejects_unregistered_perturbation(tmp_path: Path):
    _write_registry(tmp_path)
    app = create_app(_settings(tmp_path, gpu_available=True, worker_enabled=False))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            json={"cell_line": "K562", "perturbation": "TP53", "mode": "online"},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "UNSUPPORTED_PERTURBATION"


def test_old_expression_summary_warning_does_not_rewrite_the_artifact(tmp_path: Path):
    _write_registry(tmp_path)
    app = create_app(_settings(tmp_path, worker_enabled=False))
    app.state.container.store.create("run_old", CreateRunRequest(cell_line="K562", perturbation="MYC"))
    app.state.container.store.transition("run_old", RunStatus.COMPLETED, 100)
    root = app.state.container.settings.derived_root / "run_old"
    root.mkdir(parents=True)
    path = root / "summary.json"
    path.write_text(
        RunSummary(
            run_id="run_old", cell_line="K562", perturbation="MYC", status="completed", stage_progress=100
        ).model_dump_json(),
        encoding="utf-8",
    )
    original = path.read_bytes()
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/run_old/summary")
        assert "expression-cp10k-v2" in response.json()["warnings"][-1]
        assert path.read_bytes() == original
        (root / "expression_contract.json").write_text("{}")
        assert client.get("/api/v1/runs/run_old/summary").json()["warnings"] == []
