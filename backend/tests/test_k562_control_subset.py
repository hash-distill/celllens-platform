import json

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from backend.app.core.errors import AssetNotReadyError
from backend.app.core.registry import AssetRegistry
from backend.app.core.run_manifest import file_sha256
from backend.app.services.control_metadata import control_cell_count
from scripts.prepare_k562_control_1024 import prepare_subset


@pytest.fixture(params=["dense", "sparse"])
def control_project(tmp_path, request):
    import anndata as ad

    registry = tmp_path / "data/registry"
    registry.mkdir(parents=True)
    source = tmp_path / "data/raw/replogle-k562/control.h5ad"
    source.parent.mkdir(parents=True)
    frame = ad.AnnData(
        np.arange(1200 * 3, dtype=np.float32).reshape(1200, 3),
        obs=pd.DataFrame(
            {
                "cell_line": "k562",
                "gene": "non-targeting",
                "gem_group": [str(index % 4) for index in range(1200)],
            },
            index=[f"cell_{index}" for index in range(1200)],
        ),
        var=pd.DataFrame(index=["GENE1", "GENE2", "GENE3"]),
    )
    frame.obsm["X_hvg"] = frame.X[:, :2].copy()
    if request.param == "sparse":
        frame.X = sparse.csr_matrix(frame.X)
        frame.obsm["X_hvg"] = sparse.csr_matrix(frame.obsm["X_hvg"])
    frame.write_h5ad(source)
    (registry / "models.json").write_text('{"models": []}', encoding="utf-8")
    (registry / "datasets.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "datasets": [
                    {
                        "id": "replogle-k562-control-v1",
                        "cell_line": "K562",
                        "control_path": source.relative_to(tmp_path).as_posix(),
                        "control_sha256": file_sha256(source),
                        "expression_scale": "log1p_cp10k",
                        "enabled": True,
                    },
                    {"id": "rpe1", "cell_line": "RPE1", "enabled": False},
                ],
            }
        ),
        encoding="utf-8",
    )
    return tmp_path, source


def test_subset_preserves_original_values_and_historical_dataset(control_project):
    import anndata as ad

    root, source = control_project
    original_hash = file_sha256(source)
    original = ad.read_h5ad(source)
    result = prepare_subset(root)
    registry = AssetRegistry(root, root / "data/registry")
    active = registry.dataset_for("K562")
    subset = ad.read_h5ad(active.path("control_path"))

    assert control_cell_count(registry, "K562") == 1024
    assert active.payload["id"] != "replogle-k562-control-v1"
    assert subset.n_vars == original.n_vars
    assert subset.obs_names.is_unique
    selected = original[subset.obs_names].copy()
    for actual, expected in ((subset.X, selected.X), (subset.obsm["X_hvg"], selected.obsm["X_hvg"])):
        if sparse.issparse(actual):
            assert (actual != expected).nnz == 0
        else:
            np.testing.assert_array_equal(actual, expected)
    expected_rows = np.sort(np.random.default_rng(42).choice(1200, size=1024, replace=False))
    np.testing.assert_array_equal(subset.obs_names, original.obs_names[expected_rows])
    assert file_sha256(source) == original_hash
    historical = next(row for row in registry.datasets if row["id"] == "replogle-k562-control-v1")
    assert historical["enabled"] is False
    assert historical["control_sha256"] == original_hash
    assert historical["control_path"] == source.relative_to(root).as_posix()
    assert registry.dataset_for("RPE1", require_enabled=False).payload["id"] == "rpe1"
    assert subset.uns["celllens_control_subset"]["parent_sha256"] == original_hash
    assert result["control_cells"] == 1024


def test_repeated_preparation_does_not_rewrite_frozen_subset(control_project):
    root, _ = control_project
    prepare_subset(root)
    registry_path = root / "data/registry/datasets.json"
    before = registry_path.read_bytes()
    active = AssetRegistry(root, root / "data/registry").dataset_for("K562")
    before_hash = file_sha256(active.path("control_path"))
    result = prepare_subset(root)
    assert result["changed"] is False
    assert registry_path.read_bytes() == before
    assert file_sha256(active.path("control_path")) == before_hash


def test_existing_subset_is_independent_after_parent_is_explicitly_retired(control_project):
    root, source = control_project
    prepare_subset(root)
    source.unlink()
    registry_path = root / "data/registry/datasets.json"
    document = json.loads(registry_path.read_text(encoding="utf-8"))
    document["datasets"] = [row for row in document["datasets"] if row["id"] != "replogle-k562-control-v1"]
    registry_path.write_text(json.dumps(document), encoding="utf-8")
    before = registry_path.read_bytes()
    result = prepare_subset(root)
    assert result["changed"] is False
    assert result["control_cells"] == 1024
    assert registry_path.read_bytes() == before


def test_changed_parent_is_rejected_without_registry_changes(control_project):
    root, source = control_project
    before = (root / "data/registry/datasets.json").read_bytes()
    with source.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(AssetNotReadyError, match="SHA-256 mismatch"):
        prepare_subset(root)
    assert (root / "data/registry/datasets.json").read_bytes() == before
