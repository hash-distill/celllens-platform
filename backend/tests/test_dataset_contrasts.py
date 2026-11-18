import hashlib
import json
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from backend.app.core.run_manifest import file_sha256
from backend.app.services.dataset_contracts import DatasetVersion, check_analysis_budget
from backend.app.services.dataset_providers import prepare_sciplex_inputs
from backend.app.services.measured_analysis import checked_frame
from scripts.prepare_sciplex2 import build_contrasts


def fixture_source(root):
    obs = pd.DataFrame(
        {
            "organism": ["human"] * 8 + ["mouse"],
            "cell_line": ["A549"] * 9,
            "perturbation": ["Drug-A"] * 6 + ["control", "Drug-B", "Drug-A"],
            "dose_value": ["0", "0", "0", "1", "1", "1", None, "1", "1"],
            "well": ["A", "B", "C", "D", "E", "F", None, "G", "H"],
        },
        index=[f"cell-{i}" for i in range(9)],
    )
    values = np.arange(1, 37, dtype=np.float32).reshape(9, 4)
    var = pd.DataFrame(
        {"ensembl_id": ["ENSG001", "ENSG002", "ENSG003", "ENSMUSG001"]},
        index=["GENE1", "GENE2", "GENE3", "MouseGene"],
    )
    path = root / "source.h5ad"
    ad.AnnData(sparse.csr_matrix(values), obs=obs, var=var).write_h5ad(path)
    contrast = build_contrasts(obs, "fixture-v1")[0]
    version = DatasetVersion(
        id="fixture-v1",
        dataset_id="scperturb-sciplex2",
        provider="scperturb-sciplex2",
        source={"kind": "test_fixture"},
        file="source.h5ad",
        file_sha256=file_sha256(path),
        file_md5=hashlib.md5(path.read_bytes()).hexdigest(),
        file_bytes=path.stat().st_size,
        expression_slot="X",
        expression_scale="raw_counts",
        gene_identifier="gene_symbol+ensembl_id",
        total_cell_count=9,
        cell_count=8,
        gene_count=3,
        species="human",
        cell_line="A549",
        inspection={},
    )
    return path, version, contrast, values


def prepare_fixture(tmp_path, monkeypatch):
    from backend.app.services import dataset_providers

    path, version, contrast, values = fixture_source(tmp_path)
    monkeypatch.setattr(dataset_providers, "read_dataset", lambda *args: (version, [contrast]))
    monkeypatch.setattr(dataset_providers, "source_path", lambda root: path)
    request = {
        "dataset_id": version.dataset_id,
        "dataset_version": version.model_dump(),
        "condition_id": contrast.id,
        "contrast": contrast.model_dump(),
        "max_cells": 2,
        "seed": 42,
        "source_catalog_sha256": "fixture",
    }
    inputs = prepare_sciplex_inputs(tmp_path, request, tmp_path / "result", lambda *args: None)
    return request, inputs, values


def test_dose_contrast_does_not_guess_vehicle_or_replicates(tmp_path):
    _, _, contrast, _ = fixture_source(tmp_path)
    assert contrast.control_filter["dose_value"] == "0"
    assert contrast.control_filter["perturbation"] == "Drug-A"
    assert contrast.control_cell_count == 3
    assert contrast.cell_count == 3  # excludes a mouse cell and another drug
    assert contrast.dose_unit is None and contrast.time is None
    assert contrast.biological_replicate_count is None
    assert contrast.control_type == "zero_dose_same_drug_label"


def test_provider_reads_only_bounded_sparse_rows_and_preserves_labels(tmp_path, monkeypatch):
    import anndata.io

    original = anndata.io.sparse_dataset
    reads = []

    class GuardedMatrix:
        def __init__(self, handle):
            self.matrix = original(handle)

        def __getitem__(self, key):
            rows = key[0]
            assert isinstance(rows, np.ndarray) and len(rows) <= 2
            reads.append(rows.tolist())
            result = self.matrix[key]
            assert sparse.issparse(result)
            return result

    monkeypatch.setattr(anndata.io, "sparse_dataset", GuardedMatrix)
    _, inputs, values = prepare_fixture(tmp_path, monkeypatch)
    assert len(reads) == 2
    for group, entry in inputs["groups"].items():
        raw = ad.read_h5ad(entry["path"])
        assert sparse.issparse(raw.X) and raw.n_obs == 2 and raw.n_vars == 3
        assert set(raw.obs["perturbation"].astype(str)) == {"Drug-A"}
        assert "gene" not in raw.obs  # a drug was not relabelled as a target gene
        rows = raw.obs["source_row"].to_numpy()
        assert np.allclose(raw.obs["celllens_total_counts"], values[rows].sum(1))
        normalized = checked_frame(entry, "A549", "unused generic label")
        expected = np.log1p(values[rows, :3] * (10000 / values[rows].sum(1))[:, None])
        assert np.allclose(normalized.X.toarray(), expected)
        assert set(raw.obs["celllens_group"].astype(str)) == {group}


def test_changed_source_and_group_labels_fail_closed(tmp_path, monkeypatch):
    _, inputs, _ = prepare_fixture(tmp_path, monkeypatch)
    entry = inputs["groups"]["observed"]
    path = Path(entry["path"])
    frame = ad.read_h5ad(path)
    frame.obs["dose_value"] = "0"
    frame.write_h5ad(path)
    entry["sha256"] = file_sha256(path)
    with pytest.raises(ValueError, match="dose_value"):
        checked_frame(entry, "A549", "unused")
    entry["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="摘要"):
        checked_frame(entry, "A549", "unused")


def test_full_panel_memory_budget_checked_before_dense():
    assert check_analysis_budget(256, 256, 58347) < 1024**3
    with pytest.raises(ValueError, match="预算"):
        check_analysis_budget(4096, 4096, 58347)


def test_new_dataset_retains_distinct_ensembl_features_with_historical_alias_collision():
    from backend.app.core.errors import ScientificContractError
    from backend.app.services.dataset_providers import adapt_dataset_gene_identity
    from backend.app.services.gene_identity import GeneIdentityAdapter

    adapter = GeneIdentityAdapter(
        {
            "database_genes": {"ENO1": {"hgnc_id": "HGNC:3350"}},
            "approved_by_id": {"HGNC:3350": "ENO1"},
            "symbol_lookup": {
                "ENO1": {"hgnc_ids": ["HGNC:3350"], "method": "approved"},
                "ENO1-IT1": {"hgnc_ids": ["HGNC:3350"], "method": "previous"},
            },
        },
        provenance={"kind": "test_fixture"},
    )
    frame = ad.AnnData(
        sparse.csr_matrix([[10, 3], [20, 8]], dtype=float),
        var=pd.DataFrame({"ensembl_id": ["ENSG00000074800", "ENSG00000236269"]}, index=["ENO1", "ENO1-IT1"]),
    )
    # Existing strict behavior remains intact for historical and private inputs.
    with pytest.raises(ScientificContractError, match="Duplicate"):
        adapter.adapt(frame)
    result, audit = adapt_dataset_gene_identity(adapter, frame)
    assert result.var_names.tolist() == ["ENO1", "ENO1-IT1"]
    assert result.var.ensembl_id.tolist() == frame.var.ensembl_id.tolist()
    assert np.array_equal(result.X.toarray(), frame.X.toarray())
    assert audit["unresolved_alias_collision_count"] == 1
    assert audit["columns"][0]["hgnc_id"] == "HGNC:3350"
    assert audit["columns"][1]["hgnc_id"] is None
    assert audit["columns"][1]["method"] == "unresolved_alias_collision"
    frame.var["ensembl_id"] = "ENSG00000074800"
    with pytest.raises(ScientificContractError, match="distinct"):
        adapt_dataset_gene_identity(adapter, frame)


def test_new_generic_analysis_preview_matches_exact_computation(tmp_path, monkeypatch):
    from backend.app.services.measured_analysis import analyse_measured

    request, inputs, _ = prepare_fixture(tmp_path, monkeypatch)
    request.update(id="measured_fixture", cell_line="A549", perturbation="Drug-A · dose 1")
    output = tmp_path / "analysis"
    summary = analyse_measured(
        tmp_path, request, inputs, output, lambda *args: None, metabolism=False, compute_umap=False
    )
    preview = json.loads((output / "expression_preview.json").read_text())
    matrix = sparse.load_npz(output / "expression_preview.npz")
    projection = json.loads((output / "projection-pca.json").read_text())
    assert [(row["cell_id"], row["source"]) for row in preview["cells"]] == [
        (row["cell_id"], row["source"]) for row in projection["points"]
    ]
    assert matrix.shape == (4, 3)
    means = pd.read_csv(output / "genes.csv")
    assert np.allclose(means["observed_delta"], np.asarray(matrix[2:].mean(0) - matrix[:2].mean(0)).ravel())
    assert summary["contrast"]["control_type"] == "zero_dose_same_drug_label"
    assert summary["dataset_id"] == "scperturb-sciplex2"
