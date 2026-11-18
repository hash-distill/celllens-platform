"""Reader contract tests use tiny fixed files; GET must not execute scientific fitting."""

import json
from types import SimpleNamespace

import pytest

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.research_projection import prediction_projection, projection_payload
from backend.tests.test_cell_state import fixture_container


def projection_fixture(tmp_path):
    container, root, registered = fixture_container(tmp_path)
    prepared = root / "cell_state"
    prepared.mkdir()
    # Frozen test fixtures, not a generated analysis or a production fallback.
    document = {
        "run_id": "run_cells",
        "embedding_space": "expression",
        "method": "control-reference-pca",
        "expression_units": "log1p(CP10K)",
        "gene_count": 3,
        "provenance": {"manifest_sha256": file_sha256(root / "manifest.json")},
        "distributions": {"control": {"n": 4}, "predicted": {"n": 2}},
        "points": [
            {
                "source": source,
                "cell_id": f"{source}:{index}",
                "cell_index": index,
                "x": float(index),
                "y": float(index + 1),
                "value": 99.0,
            }
            for source, count in (("control", 4), ("predicted", 2))
            for index in range(count)
        ],
    }
    atomic_write_json(prepared / "expression_pca.json", document)
    (prepared / "plot_data.npz").write_bytes(b"Frozen opaque plot archive; this reader only checks its hash")
    manifest = {
        "schema_version": 1,
        "run_id": "run_cells",
        "source_manifest_sha256": file_sha256(root / "manifest.json"),
        "figures": {"expression_pca": {"kind": "gene", "feature": "MYC"}},
        "unavailable": {},
        "outputs": {path.name: file_sha256(path) for path in prepared.iterdir()},
    }
    atomic_write_json(prepared / "prepared.json", manifest)
    registered["run_cells"].append(
        SimpleNamespace(
            kind="cell_state_preparation",
            relative_path="run_cells/cell_state/prepared.json",
            sha256=file_sha256(prepared / "prepared.json"),
        )
    )
    return container, root, document


def test_projection_get_reads_only_frozen_coordinates_and_drops_default_gene_color(tmp_path, monkeypatch):
    from backend.app.services import cell_state

    container, root, _ = projection_fixture(tmp_path)
    before = {str(path): file_sha256(path) for path in root.rglob("*") if path.is_file()}

    def forbidden(*args, **kwargs):
        pytest.fail("Projection GET must never reconstruct, fit PCA/UMAP or generate a figure")

    for name in ("_reconstruct", "reference_pca", "joint_umap", "cell_state_document"):
        monkeypatch.setattr(cell_state, name, forbidden)
    payload = prediction_projection(container, "run_cells", "pca")
    assert payload["method"] == "control-reference-pca"
    assert payload["counts"] == {"control": 4, "predicted": 2}
    assert payload["total_cells"] == 6
    assert all("value" not in point for point in payload["points"])
    assert before == {str(path): file_sha256(path) for path in root.rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="未冻结"):
        prediction_projection(container, "run_cells", "umap")


def test_projection_method_metadata_is_frozen_not_reconstructed(tmp_path):
    _, _, document = projection_fixture(tmp_path)
    document.update(explained_variance_ratio=[0.04, 0.02], fit_source="control")
    document["embedding_preprocessing"] = {
        "feature_ids": ["A", "B"],
        "feature_count": 2,
        "scaling": "center-only",
    }
    payload = projection_payload(document, "prediction", "pca", {})
    assert payload["explained_variance_ratio"] == [0.04, 0.02]
    assert payload["preprocessing"] == {"feature_count": 2, "scaling": "center-only"}
    assert payload["fit_source"] == "control"
    assert payload["parameters"] is None
    document["explained_variance_ratio"] = [float("nan")]
    with pytest.raises(ValueError, match="解释方差"):
        projection_payload(document, "prediction", "pca", {})


@pytest.mark.parametrize("changed", ["source", "coordinates", "archive"])
def test_projection_reader_rejects_changed_source_coordinates_or_archive(tmp_path, changed):
    container, root, _ = projection_fixture(tmp_path)
    path = {
        "source": tmp_path / "control.h5ad",
        "coordinates": root / "cell_state/expression_pca.json",
        "archive": root / "cell_state/plot_data.npz",
    }[changed]
    with path.open("ab") as handle:
        handle.write(b"changed")
    with pytest.raises(ValueError):
        prediction_projection(container, "run_cells", "pca")


def test_legacy_seeded_random_projection_is_not_relabelled_as_pca(tmp_path):
    container, root, registered = fixture_container(tmp_path)
    atomic_write_json(
        root / "projection.json",
        {"method": "seeded-random-projection", "input_units": "log1p(CP10K)", "points": []},
    )
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["outputs"]["projection.json"] = {"sha256": file_sha256(root / "projection.json")}
    atomic_write_json(root / "manifest.json", manifest)
    registered["run_cells"][0].sha256 = file_sha256(root / "manifest.json")
    with pytest.raises(ValueError, match="随机投影"):
        prediction_projection(container, "run_cells", "pca")


def test_coordinates_require_finite_values_unique_identity_and_correct_population():
    document = {
        "method": "control-reference-pca",
        "input_units": "log1p(CP10K)",
        "points": [{"source": "control", "cell_id": "a", "x": float("nan"), "y": 0}],
    }
    with pytest.raises(ValueError, match="有限"):
        projection_payload(document, "measured", "pca", {})
    document["points"][0]["x"] = 0
    document["points"].append(dict(document["points"][0]))
    with pytest.raises(ValueError, match="唯一"):
        projection_payload(document, "measured", "pca", {})
    document["points"][1].update(source="predicted", cell_id="b")
    with pytest.raises(ValueError, match="群体"):
        projection_payload(document, "measured", "pca", {})
