"""Methods/data introduction uses registered facts without loading expression matrices."""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.tests.test_api_modes import settings, write_registry


def prepare(root):
    write_registry(root, valid=True)
    registry = root / "data/registry"
    panel = registry / "panel.txt"
    panel.write_text("MYC\nALDOA\nTP53\n", encoding="utf-8")
    document = json.loads((registry / "models.json").read_text())
    document["models"][0].update(
        {
            "gene_list_path": "data/registry/panel.txt",
            "gene_list_sha256": hashlib.sha256(panel.read_bytes()).hexdigest(),
            "supported_perturbations": ["MYC", "ALDOA"],
            "code_version": "0.11.1",
            "expression_scale": "log1p_cp10k",
        }
    )
    (registry / "models.json").write_text(json.dumps(document))
    (registry / "observations.json").write_text(
        json.dumps(
            {
                "observations": [
                    {
                        "cell_line": "K562",
                        "perturbation": "MYC",
                        "status": "available",
                        "n_cells": 12,
                        "source": {"kind": "measured_rna", "repo": "official-source", "revision": "pinned"},
                    },
                    {"cell_line": "K562", "perturbation": "ALDOA", "status": "unavailable", "n_cells": 0},
                ]
            }
        )
    )
    return panel


def test_data_summary_distinguishes_expression_panel_targets_and_registered_measurements(tmp_path):
    prepare(tmp_path)
    with TestClient(create_app(settings(tmp_path, worker_enabled=False))) as client:
        response = client.get("/api/v1/catalog/data-summary")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    row = response.json()["contexts"][0]
    assert row["expression_gene_count"] == 3
    assert row["perturbation_count"] == 2
    assert row["panel_verified"] is True
    assert row["control_registered"] is True
    assert row["registered_observations"] == [{"perturbation": "MYC", "cell_count": 12}]
    assert row["expression_genes"] == ["MYC", "ALDOA", "TP53"]
    assert str(tmp_path) not in response.text
    assert "control.h5ad" not in response.text


def test_changed_panel_is_unavailable_instead_of_showing_a_stale_gene_count(tmp_path):
    panel = prepare(tmp_path)
    app = create_app(settings(tmp_path, worker_enabled=False))
    with TestClient(app) as client:
        assert client.get("/api/v1/catalog/data-summary").json()["contexts"][0]["panel_verified"]
        panel.write_text("MODIFIED\n", encoding="utf-8")
        row = client.get("/api/v1/catalog/data-summary").json()["contexts"][0]
    assert row["panel_verified"] is False
    assert row["expression_gene_count"] is None
    assert row["expression_genes"] == []


def test_methods_subpages_support_direct_navigation_without_science_assets(tmp_path):
    prepare(tmp_path)
    dist = tmp_path / "frontend/dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html>CellLens methods</html>")
    with TestClient(create_app(settings(tmp_path, worker_enabled=False))) as client:
        for path in (
            "/methods",
            "/methods/models",
            "/methods/data",
            "/methods/backgrounds",
            "/methods/coverage",
        ):
            response = client.get(path)
            assert response.status_code == 200
            assert "CellLens methods" in response.text
        assert client.get("/methods/unknown").status_code == 404


def write_control_metadata(root, *, perturbation="non-targeting"):
    h5py = pytest.importorskip("h5py")
    path = root / "data/raw/control.h5ad"
    with h5py.File(path, "w") as handle:
        obs = handle.create_group("obs")
        obs.attrs["_index"] = "_index"
        obs.create_dataset("_index", data=[b"c1", b"c2", b"c3", b"c4"])
        obs.create_dataset("cell_line", data=[b"k562"] * 4)
        gene = obs.create_group("gene")
        gene.create_dataset("categories", data=[perturbation.encode()])
        gene.create_dataset("codes", data=[0] * 4)
        # No X dataset: the overview must only inspect observation metadata.
    registry_path = root / "data/registry/datasets.json"
    document = json.loads(registry_path.read_text())
    document["datasets"][0]["control_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    registry_path.write_text(json.dumps(document))
    return path


def test_control_count_is_read_from_verified_observations_without_expression(tmp_path):
    prepare(tmp_path)
    control = write_control_metadata(tmp_path)
    app = create_app(settings(tmp_path, worker_enabled=False))
    with TestClient(app) as client:
        row = client.get("/api/v1/catalog/data-summary").json()["contexts"][0]
        assert row["control_cell_count"] == 4
        assert row["control_metadata_verified"] is True
        with control.open("ab") as stream:
            stream.write(b"changed")
        row = client.get("/api/v1/catalog/data-summary").json()["contexts"][0]
        assert row["control_cell_count"] is None
        assert row["control_metadata_verified"] is False


def test_perturbed_rows_are_not_advertised_as_non_targeting_controls(tmp_path):
    prepare(tmp_path)
    write_control_metadata(tmp_path, perturbation="ALDOA")
    with TestClient(create_app(settings(tmp_path, worker_enabled=False))) as client:
        row = client.get("/api/v1/catalog/data-summary").json()["contexts"][0]
    assert row["control_cell_count"] is None
    assert row["control_metadata_verified"] is False
