import json
from pathlib import Path

import pytest

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.measured_comparison import (
    ComparisonUnavailable,
    load_comparison,
    observation_for,
    paired_rows,
)


def test_catalog_requires_matching_context_target_and_verified_real_file(tmp_path):
    root = tmp_path / "data/registry"
    root.mkdir(parents=True)
    source = tmp_path / "measured.h5ad"
    source.write_bytes(b"fixture identity only; no scientific claims")
    entry = {
        "cell_line": "Jurkat",
        "perturbation": "ABHD11",
        "status": "available",
        "path": "measured.h5ad",
        "sha256": file_sha256(source),
        "n_cells": 97,
        "source": {"kind": "measured_rna", "revision": "fixed"},
    }
    atomic_write_json(root / "observations.json", {"schema_version": 1, "observations": [entry]})
    assert observation_for(tmp_path, "Jurkat", "ABHD11")["n_cells"] == 97
    assert observation_for(tmp_path, "RPE1", "ABHD11") is None
    assert observation_for(tmp_path, "Jurkat", "AQR") is None
    source.write_bytes(b"changed")
    with pytest.raises(ComparisonUnavailable, match="hash"):
        observation_for(tmp_path, "Jurkat", "ABHD11")


def test_paired_rows_keep_zero_effects_and_reject_missing_or_nonfinite():
    import pandas as pd

    frame = pd.DataFrame(
        {
            "control": [1.0, 2.0, 1.0],
            "predicted": [1.0, 3.0, float("nan")],
            "observed": [1.0, 4.0, 2.0],
            "predicted_delta": [0.0, 1.0, float("nan")],
            "observed_delta": [0.0, 2.0, 1.0],
        },
        index=["ZERO", "CHANGE", "MISSING"],
    )
    rows = paired_rows(frame)
    assert [x["id"] for x in rows] == ["ZERO", "CHANGE"]
    assert rows[0]["predicted_delta"] == 0
    assert rows[1]["absolute_error"] == 1


def test_historical_comparison_uses_its_frozen_dataset_after_control_pool_change(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from backend.app.core.registry import RegistryEntry
    from backend.app.services import measured_comparison

    class FrozenDatasetSelected(Exception):
        pass

    directory = tmp_path / "data/derived/runs/run_historical"
    directory.mkdir(parents=True)
    atomic_write_json(
        directory / "manifest.json",
        {
            "request": {"cell_line": "K562", "perturbation": "ALDOA", "mode": "online", "n_cells": 64},
            "assets": {"dataset_id": "old-control"},
        },
    )
    old = {"id": "old-control", "cell_line": "K562", "enabled": False}
    active = {"id": "new-control", "cell_line": "K562", "enabled": True}
    registry = SimpleNamespace(
        datasets=[active, old],
        model_for=lambda _: None,
        dataset_for=lambda _: RegistryEntry(active, tmp_path),
    )
    monkeypatch.setattr(measured_comparison, "load_comparison", lambda *args: None)
    monkeypatch.setattr(
        measured_comparison, "observation_for", lambda *args: {"expression_scale": "log1p_cp10k"}
    )

    def check_dataset(model, dataset, assets):
        assert dataset.payload["id"] == assets["dataset_id"]
        raise FrozenDatasetSelected

    monkeypatch.setattr(measured_comparison, "validate_frozen_contract", check_dataset)
    with pytest.raises(FrozenDatasetSelected):
        measured_comparison._prepare_comparison(tmp_path, "run_historical", registry, "attempt")


def test_no_finite_metabolic_pairs_have_no_error_or_agreement_score():
    import pandas as pd

    from backend.app.engines.evidence_engine import compare_task_deltas

    missing = pd.Series({"T1": float("nan")})
    metrics = compare_task_deltas(missing, missing, missing)
    assert metrics.valid_task_count == 0
    assert metrics.mae is None
    assert metrics.direction_agreement is None
    assert metrics.top_k_overlap is None


def test_catalog_exposes_only_verified_matching_measured_shortcuts(tmp_path):
    from fastapi.testclient import TestClient

    from backend.app.main import create_app
    from backend.tests.test_system_integration import _settings, _write_registry

    _write_registry(tmp_path)
    measured = tmp_path / "measured.h5ad"
    measured.write_bytes(b"catalog identity fixture")
    row = {
        "cell_line": "K562",
        "perturbation": "MYC",
        "status": "available",
        "n_cells": 7,
        "path": "measured.h5ad",
        "sha256": file_sha256(measured),
        "source": {"kind": "measured_rna"},
    }
    atomic_write_json(tmp_path / "data/registry/observations.json", {"observations": [row]})
    with TestClient(create_app(_settings(tmp_path))) as client:
        doc = client.get("/api/v1/catalog/perturbations?cell_line=K562").json()
        assert doc["measured_comparisons"] == [{"perturbation": "MYC", "measured_cells": 7}]
        measured.write_bytes(b"changed")
        doc = client.get("/api/v1/catalog/perturbations?cell_line=K562").json()
        assert doc["measured_comparisons"] == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("expression_key", "X"),
        ("model_expression_scale", "raw_counts"),
        ("dataset_expression_scale", "cp10k"),
        ("config_sha256", "changed"),
    ],
)
def test_changed_registry_interpretation_cannot_relabel_frozen_prediction(tmp_path, field, value):
    from backend.app.core.registry import RegistryEntry
    from backend.app.services.measured_comparison import validate_frozen_contract

    model = RegistryEntry(
        {
            "id": "model",
            "embed_key": "X_hvg",
            "expression_scale": "log1p_cp10k",
            "config_sha256": "config",
            "checkpoint_sha256": "checkpoint",
            "gene_list_sha256": "genes",
        },
        tmp_path,
    )
    dataset = RegistryEntry({"id": "dataset", "expression_scale": "log1p_cp10k"}, tmp_path)
    assets = {
        "model_id": "model",
        "dataset_id": "dataset",
        "input_embed_key": "X_hvg",
        "expression_key": "X_hvg",
        "model_expression_scale": "log1p_cp10k",
        "dataset_expression_scale": "log1p_cp10k",
        "config_sha256": "config",
        "checkpoint_sha256": "checkpoint",
        "gene_list_sha256": "genes",
    }
    validate_frozen_contract(model, dataset, assets)
    assets[field] = value
    with pytest.raises(ComparisonUnavailable, match="interpretation"):
        validate_frozen_contract(model, dataset, assets)


def test_preparation_state_precedes_files_and_failed_attempt_can_retry(tmp_path, monkeypatch):
    from backend.app.services import measured_comparison as service

    service.mark_comparison_pending(tmp_path, "run_retry")
    assert service.comparison_state(tmp_path, "run_retry")["status"] == "preparing"
    attempts = []

    def prepare(root, run_id, registry, attempt_id):
        path = root / "data/derived/comparisons" / f"{run_id}.attempt-{attempt_id}.partial"
        path.mkdir(parents=True)
        attempts.append(path)
        if len(attempts) == 1:
            raise ValueError("retryable fixture failure")
        return {"status": "available"}

    monkeypatch.setattr(service, "_prepare_comparison", prepare)
    with pytest.raises(ValueError):
        service.prepare_comparison(tmp_path, "run_retry")
    assert service.comparison_state(tmp_path, "run_retry")["status"] == "failed"
    assert service.prepare_comparison(tmp_path, "run_retry")["status"] == "available"
    assert attempts[0] != attempts[1] and all(path.is_dir() for path in attempts)


def test_comparison_missing_is_not_a_fake_metric_report(tmp_path):
    assert load_comparison(tmp_path, "run_missing") is None
    with pytest.raises(ComparisonUnavailable):
        load_comparison(tmp_path, "../outside")


def write_bundle(root: Path):
    original = root / "data/derived/runs/run_test"
    original.mkdir(parents=True)
    atomic_write_json(original / "manifest.json", {"request": {"cell_line": "K562", "perturbation": "AAMP"}})
    bundle = root / "data/derived/comparisons/run_test"
    bundle.mkdir(parents=True)
    report = {
        "status": "available",
        "run_id": "run_test",
        "cell_line": "K562",
        "perturbation": "AAMP",
        "genes": [],
    }
    atomic_write_json(bundle / "comparison.json", report)
    atomic_write_json(
        bundle / "manifest.json",
        {
            "run_id": "run_test",
            "source_manifest_sha256": file_sha256(original / "manifest.json"),
            "inputs": {},
            "outputs": {"comparison.json": file_sha256(bundle / "comparison.json")},
        },
    )
    return bundle


def test_reader_rejects_changed_report_and_changed_original(tmp_path):
    bundle = write_bundle(tmp_path)
    assert load_comparison(tmp_path, "run_test")["perturbation"] == "AAMP"
    (bundle / "comparison.json").write_text(json.dumps({"run_id": "run_test", "genes": ["fake"]}))
    with pytest.raises(ComparisonUnavailable, match="hash"):
        load_comparison(tmp_path, "run_test")
    bundle.joinpath("manifest.json").unlink()
    with pytest.raises(ComparisonUnavailable):
        load_comparison(tmp_path, "run_test")


def test_api_unavailable_and_verified_download_have_distinct_states(tmp_path):
    from fastapi.testclient import TestClient

    from backend.app.main import create_app
    from backend.app.schemas import CreateRunRequest, RunStatus
    from backend.tests.test_system_integration import _settings, _write_registry

    _write_registry(tmp_path)
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        store = app.state.container.store
        store.create("run_test", CreateRunRequest(cell_line="K562", perturbation="AAMP"))
        store.transition("run_test", RunStatus.COMPLETED, 100)
        empty = client.get("/api/v1/runs/run_test/comparison")
        assert empty.status_code == 200
        assert empty.json()["status"] == "unavailable"
        assert "expression" not in empty.json()
        write_bundle(tmp_path)
        response = client.get("/api/v1/runs/run_test/comparison")
        assert response.json()["perturbation"] == "AAMP"
        assert client.get("/api/v1/runs/run_test/comparison/download").status_code == 200
        original = tmp_path / "data/derived/runs/run_test"
        atomic_write_json(original / "summary.json", {"cell_line": "K562", "perturbation": "AAMP"})
        for name in ["manifest.json", "summary.json"]:
            path = original / name
            store.register_artifact(
                "run_test",
                name,
                f"run_test/{name}",
                file_sha256(path),
                path.stat().st_size,
                "application/json",
            )
        preview = client.get(
            "/api/v1/assistant/context", params={"source_kind": "run", "source_id": "run_test"}
        )
        assert preview.status_code == 200
        assert preview.json()["data"]["measured_comparison"]["run_id"] == "run_test"
        (tmp_path / "data/derived/comparisons/run_test/comparison.json").write_text("{}")
        assert client.get("/api/v1/runs/run_test/comparison").status_code == 409
        assert client.get("/api/v1/runs/run_test/comparison/download").status_code == 409
        assert (
            client.get(
                "/api/v1/assistant/context", params={"source_kind": "run", "source_id": "run_test"}
            ).status_code
            == 409
        )
        assert client.get("/api/v1/runs/run_unknown/comparison").status_code == 404
