import json
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import pytest

from backend.app.core.run_manifest import file_sha256


def measured_inputs(root: Path):
    folder = root / "inputs"
    folder.mkdir(parents=True)
    groups = {}
    matrices = {
        "control": np.array([[1, 2, 3, 4], [2, 3, 5, 7], [3, 1, 4, 2]], dtype=np.float32),
        "observed": np.array([[4, 3, 2, 1], [2, 1, 6, 5]], dtype=np.float32),
    }
    for source, matrix in matrices.items():
        frame = ad.AnnData(
            matrix,
            obs=pd.DataFrame(
                {
                    "gene": "non-targeting" if source == "control" else "ALDOA",
                    "cell_line": "k562",
                    "gem_group": "batch-one",
                },
                index=[f"{source}_{i}" for i in range(len(matrix))],
            ),
            var=pd.DataFrame(index=["ALDOA", "GAPDH", "CUSTOM1", "CUSTOM2"]),
        )
        path = folder / f"{source}.h5ad"
        frame.write_h5ad(path)
        groups[source] = {"path": str(path), "sha256": file_sha256(path), "expression_scale": "log1p_cp10k"}
    return {"groups": groups, "source_cell_count": 2, "source": {"repo": "verified fixture"}}, matrices


def analyse(root, inputs, *, metabolism=False):
    from backend.app.services.measured_analysis import analyse_measured

    return analyse_measured(
        root,
        {
            "id": "measured_fixture",
            "cell_line": "K562",
            "perturbation": "ALDOA",
            "seed": 42,
            "max_cells": 256,
        },
        inputs,
        root / "result",
        lambda progress, message: None,
        metabolism=metabolism,
        compute_umap=False,
    )


def test_measured_analysis_retains_real_full_panel_and_never_creates_prediction(tmp_path, monkeypatch):
    from backend.app.engines.state_engine import StateCliEngine

    def forbidden(*args, **kwargs):
        pytest.fail("Measured analysis must never call STATE")

    monkeypatch.setattr(StateCliEngine, "infer", forbidden)
    inputs, matrices = measured_inputs(tmp_path)
    result = analyse(tmp_path, inputs)
    assert result["source_kind"] == "measured"
    assert result["counts"] == {"control": 3, "observed": 2}
    assert result["gene_count"] == 4
    frame = pd.read_csv(tmp_path / "result/genes.csv")
    assert frame["gene"].tolist() == ["ALDOA", "GAPDH", "CUSTOM1", "CUSTOM2"]
    assert np.allclose(frame["observed_delta"], matrices["observed"].mean(0) - matrices["control"].mean(0))
    assert not any("predicted" in field for field in frame.columns)
    projection = json.loads((tmp_path / "result/projection-pca.json").read_text())
    assert {p["source"] for p in projection["points"]} == {"control", "observed"}
    assert len(projection["points"]) == 5
    assert not (tmp_path / "result/predicted.h5ad").exists()


@pytest.mark.parametrize("change", ["hash", "background", "label", "negative", "duplicate"])
def test_measured_analysis_rejects_misidentified_or_changed_input(tmp_path, change):
    inputs, _ = measured_inputs(tmp_path)
    entry = inputs["groups"]["observed"]
    path = Path(entry["path"])
    if change == "hash":
        entry["sha256"] = "0" * 64
    else:
        frame = ad.read_h5ad(path)
        if change == "background":
            frame.obs["cell_line"] = "rpe1"
        elif change == "label":
            frame.obs["gene"] = "MYC"
        elif change == "negative":
            frame.X[0, 0] = -1
        else:
            frame.obs_names = ["same", "same"]
        frame.write_h5ad(path)
        entry["sha256"] = file_sha256(path)
    with pytest.raises(ValueError):
        analyse(tmp_path, inputs)


def test_measured_batch_matching_uses_shared_batches_without_copying_cells(tmp_path):
    inputs, _ = measured_inputs(tmp_path)
    control_entry = inputs["groups"]["control"]
    frame = ad.read_h5ad(control_entry["path"])
    frame.obs["gem_group"] = ["batch-one", "batch-one", "different-batch"]
    frame.write_h5ad(control_entry["path"])
    control_entry["sha256"] = file_sha256(Path(control_entry["path"]))
    result = analyse(tmp_path, inputs)
    assert result["input_counts"]["control"] == 3
    assert result["counts"]["control"] == 2
    assert result["batch_matching"]["common_batches"] == ["batch-one"]
    assert result["counts"]["observed"] == 2


def test_missing_optional_database_preserves_measured_expression(tmp_path):
    inputs, _ = measured_inputs(tmp_path)
    identity = tmp_path / "data/registry/gene_identity"
    identity.mkdir(parents=True)
    (identity / "manifest.json").write_text(json.dumps({"database_manifest_sha256": "missing"}))
    result = analyse(tmp_path, inputs)
    assert result["gene_count"] == 4
    assert result["metabolism"]["available"] is False
    assert any("基因身份映射不可用" in warning for warning in result["warnings"])


def test_measured_preparation_rejects_mismatching_frozen_source(tmp_path):
    from backend.app.services.measured_inputs import prepare_inputs

    with pytest.raises(ValueError, match="源版本"):
        prepare_inputs(
            tmp_path,
            {"source_cell_count": 2, "source": {"revision": "different"}},
            tmp_path / "staging",
            lambda *args: None,
        )


def test_preparing_local_measurements_reuses_verified_data_without_model_or_network(tmp_path, monkeypatch):
    from backend.app.services.measured_inputs import prepare_inputs
    from backend.app.services.resource_downloads import CATALOG

    groups, _ = measured_inputs(tmp_path)
    registry = tmp_path / "data/registry"
    registry.mkdir(parents=True)
    (registry / "models.json").write_text(json.dumps({"models": []}))
    control, observed = groups["groups"]["control"], groups["groups"]["observed"]
    (registry / "datasets.json").write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "id": "source",
                        "cell_line": "K562",
                        "enabled": True,
                        "control_path": Path(control["path"]).relative_to(tmp_path).as_posix(),
                        "control_sha256": control["sha256"],
                        "expression_scale": "log1p_cp10k",
                    }
                ]
            }
        )
    )
    source = json.loads(CATALOG.read_text())["control_source"]
    (registry / "observations.json").write_text(
        json.dumps(
            {
                "observations": [
                    {
                        "cell_line": "K562",
                        "perturbation": "ALDOA",
                        "status": "available",
                        "n_cells": 2,
                        "path": Path(observed["path"]).relative_to(tmp_path).as_posix(),
                        "sha256": observed["sha256"],
                        "expression_scale": "log1p_cp10k",
                        "source": {
                            "repo": source["repo"],
                            "revision": source["revision"],
                            "file": source["filename"],
                        },
                    }
                ]
            }
        )
    )

    def forbidden(*args, **kwargs):
        pytest.fail("No network needed for valid existing real observations")

    import fsspec

    monkeypatch.setattr(fsspec, "filesystem", forbidden)
    result = prepare_inputs(
        tmp_path,
        {"cell_line": "K562", "perturbation": "ALDOA", "max_cells": 256, "seed": 42, "source_cell_count": 2},
        tmp_path / "staging",
        lambda *args: None,
    )
    assert result["groups"]["control"]["sha256"] == control["sha256"]
    assert result["groups"]["observed"]["sha256"] == observed["sha256"]
    assert result["source_cell_count"] == 2
    assert not (tmp_path / "models").exists()
