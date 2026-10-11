import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.core.diagnostic_protocol import load_diagnostic_protocol
from backend.app.core.run_manifest import file_sha256
from backend.app.main import create_app
from backend.app.schemas import CreateRunRequest
from backend.tests.historical_bundle import _create_precomputed_run
from backend.tests.test_api_modes import settings, write_registry


def protocol_registry(root: Path) -> Path:
    write_registry(root, valid=True)
    path = root / "data/registry/datasets.json"
    data = json.loads(path.read_text())
    observed = root / "data/raw/measured.h5ad"
    observed.write_bytes(b"unit test measured asset")
    protocol = root / "data/registry/diagnostic.json"
    protocol.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "matched_observation_diagnostic",
                "cell_line": "K562",
                "perturbations": ["MYC"],
                "observed_sha256": file_sha256(observed),
                "expression_scale": "log1p_cp10k",
                "batch_key": "gem_group",
                "held_out_validation": False,
                "training_exclusion_verified": False,
            }
        )
    )
    data["datasets"][0].update(
        observed_path="data/raw/measured.h5ad",
        observed_sha256=file_sha256(observed),
        expression_scale="log1p_cp10k",
        validation_batch_key="gem_group",
        validation_protocol_path="data/registry/diagnostic.json",
        validation_protocol_sha256=file_sha256(protocol),
    )
    path.write_text(json.dumps(data))
    return protocol


def test_validation_without_registered_protocol_rejects_before_job_creation(tmp_path: Path):
    write_registry(tmp_path, valid=True)
    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs", json={"cell_line": "K562", "perturbation": "MYC", "mode": "validation"}
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "EXPERIMENT_MODE_REMOVED"
        assert client.get("/api/v1/runs").json()["total"] == 0


def test_historical_diagnostic_protocol_is_checked_but_not_advertised(tmp_path: Path):
    protocol = protocol_registry(tmp_path)
    app = create_app(settings(tmp_path, worker_enabled=True, gpu_available=True))
    with TestClient(app) as client:
        registry = app.state.container.registry
        assert load_diagnostic_protocol(registry.dataset_for("K562"), registry.model_for("K562"))[
            "perturbations"
        ] == ["MYC"]
        assert client.get("/api/v1/catalog/contexts").json()[0]["validation_ready"] is False
        assert (
            client.get("/api/v1/catalog/perturbations?cell_line=K562&mode=validation").json()["items"] == []
        )
        protocol.write_text("{}")
        assert client.get("/api/v1/catalog/contexts").json()[0]["validation_ready"] is False
        assert (
            client.get("/api/v1/catalog/perturbations?cell_line=K562&mode=validation").json()["items"] == []
        )


def test_frozen_kind_without_original_manifest_is_rejected(tmp_path: Path):
    write_registry(tmp_path, valid=False)
    bundle = tmp_path / "data/demo/K562/MYC"
    bundle.mkdir(parents=True)
    (bundle / "summary.json").write_text(
        json.dumps(
            {
                "run_id": "original",
                "status": "completed",
                "stage_progress": 100,
                "cell_line": "K562",
                "perturbation": "MYC",
            }
        )
    )
    (bundle / "projection.json").write_text(
        json.dumps(
            {
                "method": "seeded-random-projection",
                "seed": 42,
                "points": [
                    {"x": 0, "y": 0, "source": "control", "cell_index": 0},
                    {"x": 1, "y": 1, "source": "predicted", "cell_index": 0},
                ],
            }
        )
    )
    (bundle / "manifest.json").write_text(
        json.dumps(
            {"kind": "frozen_model_result", "files": {p.name: file_sha256(p) for p in bundle.iterdir()}}
        )
    )
    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        with pytest.raises(HTTPException) as error:
            _create_precomputed_run(
                CreateRunRequest(cell_line="K562", perturbation="MYC", mode="precomputed"),
                app.state.container,
            )
        assert error.value.status_code == 500
        assert client.get("/api/v1/runs").json()["total"] == 0


def test_frozen_replay_preserves_values_and_rebinds_run_identity(tmp_path: Path):
    write_registry(tmp_path, valid=False)
    bundle = tmp_path / "data/demo/K562/MYC"
    bundle.mkdir(parents=True)
    documents = {
        "summary.json": {
            "run_id": "original",
            "status": "completed",
            "stage_progress": 100,
            "cell_line": "K562",
            "perturbation": "MYC",
        },
        "projection.json": {
            "method": "seeded-random-projection",
            "seed": 42,
            "points": [
                {"x": 0, "y": 0, "source": "control", "cell_index": 0},
                {"x": 1, "y": 1, "source": "predicted", "cell_index": 0},
            ],
        },
        "expression_contract.json": {"run_id": "original", "analysis_version": "expression-cp10k-v2"},
        "task_trace.json": {"run_id": "original", "tasks": {}, "reactions": {}, "genes": {}},
        "official_completeness.json": {"run_id": "original"},
        "validation_metrics.json": {"held_out_validation": False, "expression": {"mse": 0.25}},
    }
    for name, document in documents.items():
        (bundle / name).write_text(json.dumps(document))
    for name in (
        "gene_deltas.csv",
        "metabolic_task_scores.csv",
        "reaction_scores.csv",
        "metabolic_coverage.csv",
    ):
        (bundle / name).write_text("frozen,values\nMYC,0.25\n")
    original_files = {p.name: file_sha256(p) for p in bundle.iterdir()}
    source = {
        "request": {"cell_line": "K562", "perturbation": "MYC", "mode": "validation"},
        "outputs": {name: {"sha256": digest} for name, digest in original_files.items()},
        "assets": {"model_id": "real-test"},
    }
    (bundle / "source_manifest.json").write_text(json.dumps(source))
    files = {p.name: file_sha256(p) for p in bundle.iterdir()}
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "kind": "frozen_model_result",
                "source_run_id": "original",
                "source_manifest_sha256": file_sha256(bundle / "source_manifest.json"),
                "files": files,
            }
        )
    )
    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        response = _create_precomputed_run(
            CreateRunRequest(cell_line="K562", perturbation="MYC", mode="precomputed"), app.state.container
        )
        run_id = response.run_id
        assert client.get(f"/api/v1/runs/{run_id}").json()["result_kind"] == "frozen_model_result"
        assert client.get("/api/v1/runs").json()["items"][0]["result_kind"] == "frozen_model_result"
        assert client.get(f"/api/v1/runs/{run_id}/provenance").json()["source_type"] == "frozen_precomputed"
        assert client.get(f"/api/v1/runs/{run_id}/validation").json()["expression"]["mse"] == 0.25
        destination = app.state.container.settings.derived_root / run_id
        assert file_sha256(destination / "gene_deltas.csv") == original_files["gene_deltas.csv"]
        assert json.loads((destination / "task_trace.json").read_text())["run_id"] == run_id
        assert json.loads((destination / "official_completeness.json").read_text())["run_id"] == run_id
        assert len(app.state.container.store.artifacts(run_id)) >= len(files)
