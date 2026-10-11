import json

import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.core.run_manifest import file_sha256
from backend.app.main import create_app
from backend.app.schemas import CreateRunRequest
from backend.app.services.scientific_analysis import _projection_document
from backend.tests.historical_bundle import _create_precomputed_run
from backend.tests.test_api_runs import _settings, _write_registry
from backend.tests.test_system_integration import write_bundle
from scripts import build_demo_bundle
from scripts.repair_demo_projections import supplement


def projection():
    return {
        "method": "seeded-random-projection",
        "seed": 42,
        "points": [
            {"x": 1.0, "y": 2.0, "source": "control", "cell_index": 0},
            {"x": 2.0, "y": 3.0, "source": "predicted", "cell_index": 0},
        ],
    }


@pytest.mark.parametrize("fault", ["missing", "unhashed", "empty", "nonfinite", "one_source"])
def test_incomplete_projection_is_rejected_before_creating_precomputed_run(tmp_path, fault):
    _write_registry(tmp_path)
    source = write_bundle(tmp_path)
    (source / "projection.json").unlink()
    document = projection()
    original = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    original["files"].pop("projection.json", None)
    (source / "manifest.json").write_text(json.dumps(original), encoding="utf-8")
    if fault == "empty":
        document["points"] = []
    elif fault == "nonfinite":
        document["points"][0]["x"] = float("nan")
    elif fault == "one_source":
        document["points"] = document["points"][:1]
    path = source / "projection.json"
    if fault != "missing":
        path.write_text(json.dumps(document), encoding="utf-8")
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if fault not in {"missing", "unhashed"}:
        manifest["files"]["projection.json"] = file_sha256(path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        with pytest.raises(HTTPException) as error:
            _create_precomputed_run(
                CreateRunRequest(cell_line="K562", perturbation="MYC", mode="precomputed"),
                app.state.container,
            )
        assert error.value.status_code == 500
        assert error.value.detail["code"] == "INVALID_PRECOMPUTED_RESULT"
        assert client.get("/api/v1/runs").json()["total"] == 0
        assert client.get("/api/v1/catalog/contexts").json()[0]["precomputed_ready"] is False


def test_generated_demo_projection_is_derived_from_saved_single_cell_matrix(tmp_path, monkeypatch):
    monkeypatch.setattr(build_demo_bundle, "PROJECT_ROOT", tmp_path)
    root = build_demo_bundle.build("K562", "MYC", 20)
    path = root / "projection.json"
    assert path.is_file(), "Synthetic demo must include a single-cell projection"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["data_kind"] == "synthetic_demo"
    with np.load(root / "demo_cells.npz", allow_pickle=False) as cells:
        control, predicted = cells["control"], cells["predicted"]
        assert control.shape == predicted.shape
        assert len(cells["genes"]) == control.shape[1]
        expected = _projection_document(
            [("control", control), ("predicted", predicted)],
            seed=document["seed"],
            max_points=12000,
        )
    assert document["points"] == expected["points"]
    assert len(document["points"]) == len(control) + len(predicted)
    assert document["input_sha256"] == file_sha256(root / "demo_cells.npz")
    assert set(point["source"] for point in document["points"]) == {"control", "predicted"}
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"]["projection.json"] == file_sha256(path)


def test_historical_demo_supplement_preserves_originals_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(build_demo_bundle, "PROJECT_ROOT", tmp_path)
    root = build_demo_bundle.build("K562", "MYC", 20)
    (root / "projection.json").unlink()
    (root / "demo_cells.npz").unlink()
    originals = {p.name: file_sha256(p) for p in root.iterdir() if p.is_file()}
    result = supplement(root)
    assert result["action"] == "supplemented"
    assert all(file_sha256(root / name) == digest for name, digest in originals.items())
    projection_hash = file_sha256(root / "projection.json")
    assert supplement(root)["action"] == "already_complete"
    assert file_sha256(root / "projection.json") == projection_hash
    provenance = json.loads((root / "projection_provenance.json").read_text(encoding="utf-8"))
    assert provenance["original_files"] == originals
    assert provenance["data_kind"] == "synthetic_demo"


def test_historical_real_results_cannot_be_supplemented_with_synthetic_cells(tmp_path):
    root = write_bundle(tmp_path)
    (root / "projection.json").unlink()
    with pytest.raises(ValueError, match="non-synthetic"):
        supplement(root)
    assert not (root / "demo_cells.npz").exists()
