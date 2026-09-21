import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_registry(root: Path, *, valid: bool) -> None:
    registry = root / "data" / "registry"
    registry.mkdir(parents=True)
    checkpoint = root / "models" / "m" / "checkpoints" / "final.ckpt"
    control = root / "data" / "raw" / "control.h5ad"
    if valid:
        checkpoint.parent.mkdir(parents=True)
        checkpoint.write_bytes(b"checkpoint")
        control.parent.mkdir(parents=True)
        control.write_bytes(b"control")
    model = {
        "id": "state-test",
        "cell_line": "K562",
        "enabled": True,
        "supported_perturbations": ["MYC"],
        "model_dir": "models/m",
        "checkpoint_path": "models/m/checkpoints/final.ckpt",
        "checkpoint_sha256": sha256(checkpoint) if valid else "0" * 64,
    }
    dataset = {
        "id": "data-test",
        "cell_line": "K562",
        "enabled": True,
        "control_path": "data/raw/control.h5ad",
        "control_sha256": sha256(control) if valid else "0" * 64,
    }
    (registry / "models.json").write_text(json.dumps({"models": [model]}), encoding="utf-8")
    (registry / "datasets.json").write_text(json.dumps({"datasets": [dataset]}), encoding="utf-8")


def settings(root: Path, **kwargs) -> Settings:
    return Settings(
        project_root=root,
        database_url=f"sqlite+pysqlite:///{(root / 'test.db').as_posix()}",
        create_database_schema=True,
        **kwargs,
    )


def test_online_request_is_rejected_when_worker_is_disabled(tmp_path):
    write_registry(tmp_path, valid=True)
    app = create_app(settings(tmp_path, gpu_available=True, worker_enabled=False))
    with TestClient(app) as client:
        response = client.post("/api/v1/runs", json={"cell_line": "K562", "perturbation": "MYC"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "WORKER_UNAVAILABLE"


def test_precomputed_request_does_not_require_gpu_or_model_assets(tmp_path):
    write_registry(tmp_path, valid=False)
    demo = tmp_path / "data" / "demo" / "K562" / "MYC"
    demo.mkdir(parents=True)
    summary_path = demo / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "run_id": "template",
                "status": "completed",
                "stage_progress": 100,
                "cell_line": "K562",
                "perturbation": "MYC",
                "coverage": None,
                "top_genes": [],
                "metabolic_tasks": [],
                "warnings": ["precomputed"],
                "error_code": None,
            }
        ),
        encoding="utf-8",
    )
    (demo / "manifest.json").write_text(
        json.dumps({"files": {"summary.json": sha256(summary_path)}}),
        encoding="utf-8",
    )
    app = create_app(settings(tmp_path, gpu_available=False, worker_enabled=False))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            json={"cell_line": "K562", "perturbation": "MYC", "mode": "precomputed"},
        )
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        assert response.json()["status"] == "completed"
        assert client.get(f"/api/v1/runs/{run_id}/summary").json()["warnings"] == ["precomputed"]


def test_precomputed_request_rejects_a_tampered_bundle(tmp_path):
    write_registry(tmp_path, valid=False)
    demo = tmp_path / "data" / "demo" / "K562" / "MYC"
    demo.mkdir(parents=True)
    (demo / "summary.json").write_text("{}", encoding="utf-8")
    (demo / "manifest.json").write_text(json.dumps({"files": {"summary.json": "0" * 64}}), encoding="utf-8")
    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            json={"cell_line": "K562", "perturbation": "MYC", "mode": "precomputed"},
        )
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "INVALID_PRECOMPUTED_RESULT"


def test_catalog_reports_not_ready_when_registered_files_are_missing(tmp_path):
    write_registry(tmp_path, valid=False)
    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        context = client.get("/api/v1/catalog/contexts").json()[0]
    assert context["online_ready"] is False
    assert context["validation_ready"] is False


def test_completed_run_exposes_projection_tables_and_report(tmp_path):
    write_registry(tmp_path, valid=False)
    demo = tmp_path / "data" / "demo" / "K562" / "MYC"
    demo.mkdir(parents=True)
    files = {
        "summary.json": json.dumps(
            {
                "run_id": "template",
                "status": "completed",
                "stage_progress": 100,
                "cell_line": "K562",
                "perturbation": "MYC",
                "coverage": None,
                "top_genes": [],
                "metabolic_tasks": [],
                "warnings": [],
                "error_code": None,
            }
        ),
        "projection.json": json.dumps(
            {"seed": 42, "points": [{"x": 0.1, "y": -0.2, "source": "predicted"}]}
        ),
        "gene_deltas.csv": "gene,predicted_delta\nMYC,1.0\n",
        "metabolic_task_scores.csv": "cell,task_a\nc1,0.5\n",
        "reaction_scores.csv": "cell,rxn_a\nc1,0.25\n",
        "report.html": "<html><body>CellLens report</body></html>",
    }
    for name, content in files.items():
        (demo / name).write_text(content, encoding="utf-8")
    (demo / "manifest.json").write_text(
        json.dumps({"files": {name: sha256(demo / name) for name in files}}), encoding="utf-8"
    )

    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/runs",
            json={"cell_line": "K562", "perturbation": "MYC", "mode": "precomputed"},
        )
        run_id = created.json()["run_id"]
        assert client.get(f"/api/v1/runs/{run_id}/projection").json()["seed"] == 42
        assert client.get(f"/api/v1/runs/{run_id}/genes").json()["items"][0]["gene"] == "MYC"
        tasks = client.get(f"/api/v1/runs/{run_id}/metabolic-tasks")
        reactions = client.get(f"/api/v1/runs/{run_id}/reactions")
        assert tasks.status_code == 200
        assert reactions.status_code == 200
        assert len(tasks.content) < 200_000
        assert len(reactions.content) < 200_000
        report = client.get(f"/api/v1/runs/{run_id}/report")
        assert report.status_code == 200
        assert "CellLens report" in report.text
