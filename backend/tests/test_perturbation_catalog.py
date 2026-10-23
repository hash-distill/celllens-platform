import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import anndata as ad
import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.data_catalog import router
from backend.app.services.perturbation_catalog import (
    SOURCE,
    catalog_document,
    pair_detail,
    query_pairs,
    seal_document,
)
from scripts.build_perturbation_catalog import aggregate_counts


def test_measured_gene_choices_are_complete_classified_and_independent_of_model_support(container):
    from backend.app.api.catalog import router as catalog_router

    targets = ["ALDOA", *[f"GENE{i:03}" for i in range(125)]]
    document = seal_document(
        {
            "schema_version": 1,
            "source": SOURCE,
            "metadata_complete": True,
            "metadata": {"columns": ["obs.cell_line", "obs.gene"], "n_obs": 127, "sha256": "a" * 64},
            **aggregate_counts(["K562"] * 127, [*targets, "non-targeting"]),
        }
    )
    (container.registry.registry_root / "perturbation_catalog.json").write_text(json.dumps(document))
    container.settings.registry_root = Path(__file__).resolve().parents[2] / "data/registry"
    container.registry.supported_perturbations = lambda _context: []
    app = FastAPI()
    app.state.container = container
    app.include_router(catalog_router, prefix="/api/v1")
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/perturbations?cell_line=K562&mode=measured")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == sorted(targets)
        assert len(data["genes"]) == 126
        assert next(row for row in data["genes"] if row["symbol"] == "ALDOA")["category_ids"] == ["PC00144"]
        assert {row["id"]: row["count"] for row in data["categories"]} == {
            "unclassified": 125,
            "PC00144": 1,
        }
        assert data["classification"]["available"] is True
        assert client.get("/api/v1/catalog/perturbations?cell_line=K562").json()["items"] == []
        assert client.get("/api/v1/catalog/perturbations?cell_line=Other&mode=measured").status_code == 422


def test_official_split_retains_provenance_but_excludes_control():
    from scripts.build_perturbation_catalog import parse_official_split

    content = b'[fewshot."replogle.k562"]\ntest=["ALDOA", "non-targeting"]\nval=["ABHD11"]\n'
    split = parse_official_split(content, "K562")
    assert split["test"] == ["ALDOA"]
    assert split["val"] == ["ABHD11"]
    assert split["declared_test_entries_including_control"] == 2
    assert split["training_exclusion_verified"] is False


def test_corrupt_categorical_code_is_rejected(tmp_path):
    import h5py

    from scripts.build_perturbation_catalog import read_labels

    with h5py.File(tmp_path / "metadata.h5", "w") as handle:
        group = handle.create_group("gene")
        group.create_dataset("categories", data=[b"ALDOA"])
        group.create_dataset("codes", data=[0, 99])
        with pytest.raises(ValueError, match="categorical"):
            read_labels(group)


@pytest.fixture
def container(tmp_path: Path):
    folder = tmp_path / "data/registry"
    folder.mkdir(parents=True)
    counts = aggregate_counts(
        ["k562", "k562", "k562", "jurkat", "jurkat"],
        ["ALDOA", "ALDOA", "non-targeting", "ABHD11", "non-targeting"],
    )
    document = seal_document(
        {
            "schema_version": 1,
            "source": SOURCE,
            "metadata_complete": True,
            "metadata": {"columns": ["obs.cell_line", "obs.gene"], "n_obs": 5, "sha256": "a" * 64},
            **counts,
            "official_splits": {
                "K562": {"test": ["ALDOA"], "val": [], "sha256": "b" * 64, "file": "k562.toml"}
            },
        }
    )
    (folder / "perturbation_catalog.json").write_text(json.dumps(document), encoding="utf-8")
    registry = SimpleNamespace(
        models=[{"cell_line": name} for name in ("K562", "Jurkat", "HepG2", "RPE1")],
        registry_root=folder,
        supported_perturbations=lambda name: ["ALDOA", "ABHD11", "NON-TARGETING"],
    )
    return SimpleNamespace(settings=SimpleNamespace(project_root=tmp_path), registry=registry)


def test_full_count_aggregation_retains_controls_and_all_rows():
    result = aggregate_counts(["k562", "K562", "rpe1"], ["ALDOA", "ALDOA", "non-targeting"])
    assert result["context_totals"] == {"K562": 2, "RPE1": 1}
    assert sum(row["cell_count"] for row in result["counts"]) == 3
    assert result["counts"][0] == {"cell_line": "K562", "perturbation": "ALDOA", "cell_count": 2}


def test_aggregation_rejects_different_lengths_and_unknown_context():
    with pytest.raises(ValueError):
        aggregate_counts(["k562"], [])
    with pytest.raises(ValueError):
        aggregate_counts(["arbitrary"], ["ALDOA"])


def test_measured_source_is_available_before_local_download(container):
    row = pair_detail(container, "K562", "ALDOA")
    assert row["source_cell_count"] == 2
    assert row["source_status"] == "measured"
    assert row["local_verified"] is False
    assert row["local_measured_cells"] == 0
    assert row["recommended_action"] == "measured"
    assert row["official_split"] == "test"
    assert row["training_exclusion_verified"] is False
    assert row["generalization_verified"] is False


def test_source_only_targets_remain_measured_beyond_model_vocabulary(container):
    container.registry.supported_perturbations = lambda _: ["ALDOA", "NON-TARGETING"]
    row = pair_detail(container, "Jurkat", "ABHD11")
    assert row["model_supported"] is False
    assert row["recommended_action"] == "measured"
    assert query_pairs(container, query="ABHD11", availability="measured")["total"] == 1
    assert pair_detail(container, "K562", "OUTSIDE")["recommended_action"] == "unsupported"


@pytest.mark.parametrize("rows", [None, [None], ["invalid"]])
def test_damaged_local_registry_does_not_hide_verified_source(container, rows):
    path = container.settings.project_root / "data/registry/observations.json"
    path.write_text(json.dumps({"observations": rows}))
    row = pair_detail(container, "K562", "ALDOA")
    assert row["source_status"] == "measured"
    assert row["local_verified"] is False


def test_source_missing_is_scoped_and_differs_from_unknown(container):
    assert pair_detail(container, "RPE1", "ALDOA")["recommended_action"] == "predict_exploratory"
    assert pair_detail(container, "RPE1", "ALDOA")["source_cell_count"] == 0
    path = container.registry.registry_root / "perturbation_catalog.json"
    path.unlink()
    row = pair_detail(container, "RPE1", "ALDOA")
    assert row["source_cell_count"] is None
    assert row["source_status"] == "unknown"
    assert row["recommended_action"] == "check_source"


def test_tampered_or_incomplete_document_is_unknown(container):
    path = container.registry.registry_root / "perturbation_catalog.json"
    document = json.loads(path.read_text())
    document["counts"][0]["cell_count"] += 1
    path.write_text(json.dumps(document))
    assert catalog_document(container.settings.project_root)["source_verified"] is False
    assert pair_detail(container, "K562", "ALDOA")["source_status"] == "unknown"
    document = seal_document(document)
    path.write_text(json.dumps(document))
    assert catalog_document(container.settings.project_root)["source_verified"] is False


def test_filters_pagination_summary_and_control_exclusion(container):
    result = query_pairs(container, availability="measured", limit=1, offset=1)
    assert result["total"] == 2
    assert len(result["items"]) == 1
    assert result["source_verified"] is True
    assert result["summary"]["model_supported_pairs"] == 8
    assert result["summary"]["model_supported_unmeasured_pairs"] == 6
    assert all(row["perturbation"] != "NON-TARGETING" for row in query_pairs(container)["items"])
    assert query_pairs(container, cell_line="K562", query="ald")["total"] == 1
    assert query_pairs(container, availability="missing")["total"] == 6
    assert query_pairs(container, model_supported=False)["total"] == 0


def test_local_count_requires_hash_and_actual_metadata(container):
    root = container.settings.project_root
    target = root / "local.h5ad"
    frame = ad.AnnData(
        np.ones((1, 2)),
        obs=pd.DataFrame({"cell_line": ["k562"], "gene": ["ALDOA"]}, index=["cell"]),
    )
    frame.write_h5ad(target)
    observation = {
        "cell_line": "K562",
        "perturbation": "ALDOA",
        "status": "available",
        "n_cells": 1,
        "path": "local.h5ad",
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "source": SOURCE,
    }
    path = root / "data/registry/observations.json"
    path.write_text(json.dumps({"observations": [observation]}))
    row = pair_detail(container, "K562", "ALDOA")
    assert (row["local_verified"], row["local_measured_cells"]) == (True, 1)
    observation["n_cells"] = 2
    path.write_text(json.dumps({"observations": [observation]}))
    assert pair_detail(container, "K562", "ALDOA")["local_verified"] is False
    observation["path"] = "../escape.h5ad"
    path.write_text(json.dumps({"observations": [observation]}))
    assert pair_detail(container, "K562", "ALDOA")["local_verified"] is False


@pytest.mark.parametrize(
    "cell_line,perturbation",
    [("other", "ALDOA"), ("K562", "../secret"), ("K562", "https://example.org/a"), ("K562", "NON-TARGETING")],
)
def test_unsafe_or_control_pair_is_rejected(container, cell_line, perturbation):
    with pytest.raises(ValueError):
        pair_detail(container, cell_line, perturbation)


def test_api_full_filtered_csv_and_invalid_input(container):
    app = FastAPI()
    app.state.container = container
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as client:
        response = client.get("/api/v1/data-catalog", params={"availability": "missing", "limit": 1})
        assert response.status_code == 200
        assert response.json()["total"] == 6
        csv = client.get("/api/v1/data-catalog/download.csv", params={"availability": "missing"})
        assert csv.status_code == 200
        assert len(csv.text.strip().splitlines()) == 7
        assert "generalization_verified" in csv.text
        assert (
            client.get(
                "/api/v1/data-catalog/pair", params={"cell_line": "K562", "perturbation": "ALDOA"}
            ).json()["source_status"]
            == "measured"
        )
        assert (
            client.get(
                "/api/v1/data-catalog/pair", params={"cell_line": "other", "perturbation": "ALDOA"}
            ).status_code
            == 422
        )
        assert client.get("/api/v1/data-catalog", params={"availability": "nonsense"}).status_code == 422
        assert client.get("/api/v1/data-catalog", params={"offset": -1}).status_code == 422
