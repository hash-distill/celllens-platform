import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.schemas import CreateRunRequest
from backend.app.services.cell_state import (
    CellStateUnavailable,
    aligned_task_scores,
    cell_state_document,
    distribution,
    frozen_inputs,
    joint_umap,
    metabolic_matrices,
    reference_pca,
)
from backend.app.services.cell_state_figure import render_cell_state
from backend.app.services.scientific_analysis import _combine_sources, _select_prediction_population
from backend.tests.test_task_trace import completed_app

ad = pytest.importorskip("anndata")
pytest.importorskip("sklearn")
pytest.importorskip("matplotlib")


def fixture_container(tmp_path):
    derived = tmp_path / "runs"
    root = derived / "run_cells"
    root.mkdir(parents=True)
    control = ad.AnnData(np.array([[0, 1, 3], [2, 4, 1], [3, 2, 6], [1, 4, 5]], dtype=float))
    control.var_names = ["MYC", "ENO1", "ENO2"]
    control.obs_names = [f"c{i}" for i in range(4)]
    predicted = ad.AnnData(np.array([[2, 2, 4], [10, 10, 10], [3, 4, 6]], dtype=float))
    predicted.var_names = control.var_names.copy()
    predicted.obs_names = ["p0", "p1", "p2"]
    predicted.obs["gene"] = ["MYC", "control", "MYC"]
    control_path = tmp_path / "control.h5ad"
    control.write_h5ad(control_path)
    predicted.write_h5ad(root / "predicted.h5ad")
    selected, population = _select_prediction_population(predicted, "gene", "MYC")
    genes = tmp_path / "genes.txt"
    genes.write_text("MYC\nENO1\nENO2\n", encoding="utf-8")
    request = CreateRunRequest(cell_line="K562", perturbation="MYC", mode="online")
    contract = {
        "analysis_version": "expression-cp10k-v2",
        "gene_count": 3,
        "source_scales": {"control": "log1p_cp10k", "predicted": "log1p_cp10k", "observed": None},
        "population_selection": population,
        "validation_population": None,
    }
    atomic_write_json(root / "expression_contract.json", contract)
    columns = [{"source_symbol": g, "analysis_symbol": g} for g in control.var_names]
    atomic_write_json(
        root / "gene_identity.json", {"sources": {s: {"columns": columns} for s in ("control", "predicted")}}
    )
    means = pd.DataFrame(
        {"control": control.X.mean(0), "predicted": selected.X.mean(0)}, index=control.var_names
    )
    means["predicted_delta"] = means.predicted - means.control
    means.to_csv(root / "gene_deltas.csv")
    combined = _combine_sources(ad, control, selected, None)
    scores = pd.DataFrame(
        {
            "T": [1, 2, 3, 4, 6, 8],
            "U": [20, 50, 10, 40, 70, 90],
            "incomplete": [np.nan, 1, 2, 3, 4, 5],
            "constant": [0, 0, 0, 0, 3, 4],
            "source": combined.obs.celllens_source.to_numpy(),
        },
        index=combined.obs_names,
    )
    scores.iloc[::-1].to_csv(root / "metabolic_task_scores.csv")  # ID join must recover original ordering.
    assets = {
        "model_id": "model",
        "dataset_id": "dataset",
        "expression_key": "X",
        "control_sha256": file_sha256(control_path),
        "gene_list_sha256": file_sha256(genes),
    }
    manifest = {
        "request": request.model_dump(mode="json"),
        "assets": assets,
        "outputs": {p.name: {"sha256": file_sha256(p)} for p in root.iterdir()},
    }
    atomic_write_json(root / "manifest.json", manifest)
    registered = {
        "run_cells": [
            SimpleNamespace(
                relative_path="runs/run_cells/manifest.json", sha256=file_sha256(root / "manifest.json")
            )
        ]
    }
    store = SimpleNamespace(
        artifacts=lambda run: registered[run], get=lambda _: SimpleNamespace(request=request)
    )
    settings = SimpleNamespace(derived_root=derived, project_root=tmp_path)
    registry = SimpleNamespace(
        models=[{"id": "model", "gene_list_path": "genes.txt"}],
        datasets=[{"id": "dataset", "control_path": "control.h5ad"}],
    )
    return SimpleNamespace(store=store, settings=settings, registry=registry), root, registered


def test_pca_reference_axes_cannot_be_rotated_by_predictions():
    rng = np.random.default_rng(8)
    control = rng.normal(size=(20, 5))
    coords, variance = reference_pca({"control": control, "predicted": control + 1})
    changed, variance2 = reference_pca({"control": control, "predicted": rng.normal(100, 8, size=(7, 5))})
    np.testing.assert_allclose(coords["control"], changed["control"])
    assert variance == variance2 and 0 < sum(variance) <= 1
    centered = control - control.mean(0)
    _, singular, _ = np.linalg.svd(centered, full_matrices=False)
    np.testing.assert_allclose(variance, (singular**2 / (singular**2).sum())[:2])


@pytest.mark.parametrize("matrix", [np.ones((3, 2)), np.ones((1, 3)), np.array([[1, np.nan], [2, 3]])])
def test_pca_rejects_undefined_references(matrix):
    with pytest.raises(CellStateUnavailable):
        reference_pca({"control": matrix, "predicted": matrix})


def test_distribution_preserves_zero_and_missing_without_fake_significance():
    result = distribution(np.array([0, 1, 1, 4, np.nan]))
    assert result["n"] == 5 and result["n_valid"] == 4
    assert result["mean"] == 1.5 and result["median"] == 1
    assert result["ecdf"] == [[0, 0.25], [1, 0.75], [4, 1]]
    assert "p_value" not in result


def test_task_alignment_rejects_wrong_ids_or_sources():
    frame = pd.DataFrame({"source": ["control", "predicted"]}, index=["a", "b"])
    for ids, sources in [
        (["a", "a"], ["control", "predicted"]),
        (["a", "z"], ["control", "predicted"]),
        (["a", "b"], ["predicted", "control"]),
    ]:
        with pytest.raises(CellStateUnavailable):
            aligned_task_scores(frame, ids, sources)


def test_reconstruction_matches_saved_means_and_joins_shuffled_task_ids(tmp_path):
    container, _, _ = fixture_container(tmp_path)
    gene = cell_state_document(container, "run_cells", "gene", "MYC")
    assert gene["distributions"]["control"]["n"] == 4
    assert gene["distributions"]["predicted"]["n"] == 2
    assert gene["distributions"]["predicted"]["mean"] == 2.5
    assert gene["provenance"]["expression_slots"] == {"control": "X", "predicted": "X"}
    assert gene["provenance"]["gene_means_verified"] and gene["provenance"]["task_cell_ids_verified"]
    task = cell_state_document(container, "run_cells", "task", "T")
    assert task["distributions"]["control"]["mean"] == 2.5
    assert task["distributions"]["predicted"]["mean"] == 7
    assert {p["cell_id"]: p["value"] for p in task["points"]}["p2-1"] == 8
    np.testing.assert_allclose(
        [[p["x"], p["y"]] for p in task["points"]], [[p["x"], p["y"]] for p in gene["points"]]
    )
    json.dumps(task, allow_nan=False)


def test_cache_does_not_bypass_frozen_input_hashes(tmp_path):
    container, root, _ = fixture_container(tmp_path)
    cell_state_document(container, "run_cells", "gene", "MYC")
    with (root / "metabolic_task_scores.csv").open("a") as handle:
        handle.write("tampered")
    with pytest.raises(CellStateUnavailable, match="changed"):
        cell_state_document(container, "run_cells", "gene", "MYC")


def test_umap_keeps_cell_identity_feature_values_and_pca_separate(tmp_path):
    container, root, _ = fixture_container(tmp_path)
    before = {path.name: file_sha256(path) for path in root.iterdir()}
    pca = cell_state_document(container, "run_cells", "gene", "MYC")
    gene = cell_state_document(container, "run_cells", "gene", "MYC", "umap")
    task = cell_state_document(container, "run_cells", "task", "T", "umap")
    assert gene["method"] == "joint-umap" and gene["fit_source"] == "joint"
    assert gene["explained_variance_ratio"] == []
    assert gene["embedding_parameters"]["fit_sources"] == ["control", "predicted"]
    assert gene["embedding_parameters"]["preprocessing"]["n_components"] == 3
    assert gene["embedding_parameters"]["n_neighbors"] == 5
    assert gene["distributions"] == pca["distributions"]
    assert [(p["cell_id"], p["source"], p["value"]) for p in gene["points"]] == [
        (p["cell_id"], p["source"], p["value"]) for p in pca["points"]
    ]
    assert [(p["x"], p["y"]) for p in gene["points"]] == [(p["x"], p["y"]) for p in task["points"]]
    assert task["distributions"]["predicted"]["mean"] == 7
    again = cell_state_document(container, "run_cells", "gene", "MYC")
    assert again == pca
    assert {path.name: file_sha256(path) for path in root.iterdir()} == before
    image = render_cell_state(gene, "svg")
    assert b"UMAP 1" in image and b"UMAP 2" in image and b"Joint UMAP" in image
    assert b"control variance" not in image
    json.dumps(gene, allow_nan=False)
    with (root / "metabolic_task_scores.csv").open("a") as stream:
        stream.write("tampered")
    with pytest.raises(CellStateUnavailable, match="changed"):
        cell_state_document(container, "run_cells", "gene", "MYC", "umap")


def test_joint_umap_is_reproducible_and_includes_observed_cells():
    rng = np.random.default_rng(14)
    matrices = {
        "control": rng.normal(size=(25, 8)),
        "predicted": rng.normal(size=(10, 8)) + 0.7,
        "observed": rng.normal(size=(5, 8)) + 0.2,
    }
    coordinates, parameters = joint_umap(matrices)
    repeated, repeated_parameters = joint_umap(matrices)
    assert parameters == repeated_parameters
    assert parameters["fit_sources"] == ["control", "predicted", "observed"]
    assert parameters["preprocessing"]["n_components"] == 8
    for source in matrices:
        assert coordinates[source].shape == (len(matrices[source]), 2)
        assert np.isfinite(coordinates[source]).all()
        np.testing.assert_array_equal(coordinates[source], repeated[source])


@pytest.mark.parametrize(
    "matrix", [np.ones((4, 2)), np.ones((2, 3)), np.array([[1, 2], [3, np.inf], [4, 5]])]
)
def test_umap_rejects_invalid_expression(matrix):
    with pytest.raises(CellStateUnavailable):
        joint_umap({"control": matrix})


def test_wrong_saved_means_are_rejected_even_with_resealed_manifest(tmp_path):
    container, root, registered = fixture_container(tmp_path)
    genes = pd.read_csv(root / "gene_deltas.csv", index_col=0)
    genes["control"] += 1
    genes.to_csv(root / "gene_deltas.csv")
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["outputs"]["gene_deltas.csv"]["sha256"] = file_sha256(root / "gene_deltas.csv")
    atomic_write_json(root / "manifest.json", manifest)
    registered["run_cells"][0].sha256 = file_sha256(root / "manifest.json")
    with pytest.raises(CellStateUnavailable, match="gene means"):
        cell_state_document(container, "run_cells", "gene", "MYC")


def test_replay_requires_exact_original_manifest(tmp_path):
    container, root, registered = fixture_container(tmp_path)
    replay = container.settings.derived_root / "run_replay"
    replay.mkdir()
    manifest = json.loads((root / "manifest.json").read_text())
    manifest.update(
        source_type="frozen_precomputed", source_run_id="run_cells", original_manifest_sha256="wrong"
    )
    atomic_write_json(replay / "manifest.json", manifest)
    registered["run_replay"] = [
        SimpleNamespace(
            relative_path="runs/run_replay/manifest.json", sha256=file_sha256(replay / "manifest.json")
        )
    ]
    with pytest.raises(CellStateUnavailable, match="Original run manifest"):
        frozen_inputs(container, "run_replay")


@pytest.mark.parametrize("format,magic", [("svg", b"<?xml"), ("pdf", b"%PDF"), ("png", b"\x89PNG")])
def test_scientific_exports_are_real_vector_or_300dpi_raster(tmp_path, format, magic):
    container, _, _ = fixture_container(tmp_path)
    doc = cell_state_document(container, "run_cells", "gene", "MYC")
    image = render_cell_state(doc, format)
    assert image.startswith(magic)
    if format == "svg":
        assert b"Global expression distribution" in image and b"Per-cell feature distribution" in image
        assert b"control variance" in image and b"log1p(CP10K)" in image
    if format == "png":
        from io import BytesIO

        from PIL import Image

        img = Image.open(BytesIO(image))
        assert img.size == (4200, 2580) and round(img.info["dpi"][0]) == 300


def test_cell_state_api_preserves_unavailable_and_validation_states(tmp_path):
    app, _ = completed_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/v1/runs/missing/cell-state").status_code == 404
        assert (
            client.get("/api/v1/runs/run_trace/cell-state").json()["detail"]["code"]
            == "CELL_STATE_UNAVAILABLE"
        )
        assert client.get("/api/v1/runs/run_trace/cell-state?feature_kind=umap").status_code == 422
        assert client.get("/api/v1/runs/run_trace/cell-state?embedding=random").status_code == 422
        assert client.get("/api/v1/runs/run_trace/cell-state/figure?embedding=random").status_code == 422
        assert client.get("/api/v1/runs/run_trace/cell-state/figure?file_format=exe").status_code == 422
        assert client.get("/api/v1/runs/run_trace/cell-state?space=invalid").status_code == 422
        assert client.get("/api/v1/runs/run_trace/cell-state/figure?space=invalid").status_code == 422


def test_metabolic_preprocessing_excludes_missing_and_constant_controls_without_imputation():
    scores = pd.DataFrame(
        {
            "T": [0, 1, 2, 3, 5],
            "U": [20, 30, 50, 10, 90],
            "missing": [1, 2, 3, np.nan, 5],
            "constant": [0, 0, 0, 9, 12],
            "source": ["control"] * 3 + ["predicted", "observed"],
        }
    )
    before = scores.copy(deep=True)
    matrices, metadata = metabolic_matrices(scores)
    assert metadata["feature_ids"] == ["T", "U"]
    assert metadata["excluded_incomplete"] == ["missing"]
    assert metadata["excluded_constant_control"] == ["constant"]
    np.testing.assert_allclose(matrices["control"].mean(axis=0), 0, atol=1e-14)
    np.testing.assert_allclose(matrices["control"].std(axis=0), 1)
    raw = scores[["T", "U"]].to_numpy()
    expected = (raw - raw[:3].mean(0)) / raw[:3].std(0)
    np.testing.assert_allclose(np.concatenate(list(matrices.values())), expected)
    pd.testing.assert_frame_equal(scores, before)
    with pytest.raises(CellStateUnavailable, match="至少两个"):
        metabolic_matrices(scores.drop(columns="U"))


@pytest.mark.parametrize("embedding", ["pca", "umap"])
def test_metabolic_coordinates_use_scores_and_feature_changes_only_recolor(tmp_path, embedding):
    container, root, _ = fixture_container(tmp_path)
    before = {path.name: file_sha256(path) for path in root.iterdir()}
    original = cell_state_document(container, "run_cells", "task", "T", embedding)
    task = cell_state_document(container, "run_cells", "task", "T", embedding, "metabolic")
    other = cell_state_document(container, "run_cells", "task", "U", embedding, "metabolic")
    assert task["embedding_space"] == "metabolic"
    assert task["embedding_preprocessing"]["feature_ids"] == ["T", "U"]
    assert task["embedding_preprocessing"]["scaling"] == "control-zscore"

    def xy(doc):
        return [(p["x"], p["y"]) for p in doc["points"]]

    assert xy(task) == xy(other) and xy(task) != xy(original)
    assert task["distributions"] == original["distributions"]
    assert [(p["cell_id"], p["source"], p["value"]) for p in task["points"]] == [
        (p["cell_id"], p["source"], p["value"]) for p in original["points"]
    ]
    if embedding == "pca":
        combined = _combine_sources(
            ad,
            ad.read_h5ad(container.settings.project_root / "control.h5ad"),
            _select_prediction_population(ad.read_h5ad(root / "predicted.h5ad"), "gene", "MYC")[0],
            None,
        )
        scores = aligned_task_scores(
            pd.read_csv(root / "metabolic_task_scores.csv", index_col=0),
            combined.obs_names.tolist(),
            combined.obs.celllens_source.tolist(),
        )
        expected, variance = reference_pca(metabolic_matrices(scores)[0])
        np.testing.assert_allclose(xy(task), np.concatenate(list(expected.values())))
        assert task["explained_variance_ratio"] == variance
    image = render_cell_state(task, "svg")
    assert b"metabolic tasks" in image and b"control z-score scaling" in image
    assert b"3 genes" not in image
    if embedding == "umap":
        assert b"UMAP 1" in image and b"control variance" not in image
    assert {path.name: file_sha256(path) for path in root.iterdir()} == before
    json.dumps(task, allow_nan=False)
    with pytest.raises(CellStateUnavailable, match="任务分数着色"):
        cell_state_document(container, "run_cells", "gene", "MYC", embedding, "metabolic")
