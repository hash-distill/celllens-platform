import importlib
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.tests.test_api_modes import settings, write_registry


@pytest.mark.parametrize("cell_line", ["RPE1", "Jurkat", "HepG2"])
def test_new_context_requests_reach_registered_asset_gate(tmp_path, cell_line):
    write_registry(tmp_path, valid=True)
    registry = tmp_path / "data" / "registry"
    for filename, key in [("models.json", "models"), ("datasets.json", "datasets")]:
        path = registry / filename
        document = json.loads(path.read_text())
        document[key][0]["cell_line"] = cell_line
        path.write_text(json.dumps(document))
    with TestClient(create_app(settings(tmp_path, worker_enabled=False, gpu_available=True))) as client:
        response = client.post("/api/v1/runs", json={"cell_line": cell_line, "perturbation": "MYC"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "WORKER_UNAVAILABLE"


def test_control_selection_never_mixes_backgrounds_or_perturbed_cells():
    from importlib.util import find_spec

    assert find_spec("scripts.prepare_context_assets") is not None, "multi-context preparation is missing"
    module = importlib.import_module("scripts.prepare_context_assets")
    lines = np.array(["k562", "rpe1", "rpe1", "jurkat", "rpe1", "rpe1"])
    perts = np.array(
        ["non-targeting", "AAMP", "non-targeting", "non-targeting", "non-targeting", "non-targeting"]
    )
    selected = module.select_control_rows(lines, perts, "RPE1", max_cells=2, seed=42)
    assert len(selected) == 2
    assert len(set(selected)) == 2
    assert set(selected) <= {2, 4, 5}
    assert np.array_equal(selected, module.select_control_rows(lines, perts, "RPE1", max_cells=2, seed=42))
    with pytest.raises(ValueError, match="No.*control"):
        module.select_control_rows(lines, perts, "HepG2", max_cells=2, seed=42)


def test_partial_contiguous_reads_preserve_source_values_and_order(tmp_path):
    import fsspec
    import h5py

    module = importlib.import_module("scripts.prepare_context_assets")
    assert hasattr(module, "read_expression_rows"), "bounded parallel source reader is missing"
    path = tmp_path / "matrix.h5"
    source = np.arange(120, dtype=np.float32).reshape(20, 6)
    with h5py.File(path, "w") as frame:
        frame.create_dataset("X", data=source)
    with h5py.File(path, "r") as frame:
        dataset = frame["X"]
        rows = np.array([2, 5, 17])
        actual = module.read_expression_rows(fsspec.filesystem("file"), str(path), dataset, rows)
    assert np.array_equal(actual.toarray(), source[rows])
