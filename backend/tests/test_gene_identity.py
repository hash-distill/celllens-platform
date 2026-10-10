import anndata as ad
import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from backend.app.core.errors import ScientificContractError
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.gene_identity import GeneIdentityAdapter, build_identity_document


def adapter():
    hgnc = pd.DataFrame(
        [
            ["HGNC:1", "ADSS2", "ADSS", ""],
            ["HGNC:7419", "MT-CO1", "", "COX1"],
            ["HGNC:9604", "PTGS1", "", "COX1"],
        ],
        columns=["hgnc_id", "symbol", "prev_symbol", "alias_symbol"],
    )
    rxn = pd.DataFrame({"GPR": ["HGNC:1 and HGNC:7419"], "GPR-symbol": ["ADSS and COX1"]})
    return GeneIdentityAdapter(build_identity_document(rxn, hgnc), provenance={"fixture": True})


def test_identity_adapter_preserves_expression_and_uses_database_ids():
    source = ad.AnnData(
        np.array([[2.0, 5.0, 0.0], [3.0, 0.0, 9.0]]), var=pd.DataFrame(index=["ADSS2", "MT-CO1", "OTHER"])
    )
    mapped, report = adapter().adapt(source)
    assert mapped.var_names.tolist() == ["ADSS", "COX1", "OTHER"]
    np.testing.assert_array_equal(mapped.X, source.X)
    assert source.var_names.tolist() == ["ADSS2", "MT-CO1", "OTHER"]
    assert mapped.var["source_gene_symbol"].tolist() == source.var_names.tolist()
    assert report["renamed_columns"] == 2
    assert report["columns"][1]["hgnc_id"] == "HGNC:7419"


def test_sparse_measurements_are_preserved_without_densifying_or_filling():
    values = sparse.csr_matrix([[0.0, 4.0], [9.0, 0.0]])
    source = ad.AnnData(values, var=pd.DataFrame(index=["ADSS2", "MT-CO1"]))
    mapped, _ = adapter().adapt(source)
    assert sparse.isspmatrix_csr(mapped.X)
    assert mapped.X.dtype == values.dtype
    np.testing.assert_array_equal(mapped.X.data, values.data)
    np.testing.assert_array_equal(mapped.X.indices, values.indices)
    np.testing.assert_array_equal(mapped.X.indptr, values.indptr)


def test_ambiguous_symbol_is_not_guessed_but_explicit_hgnc_id_resolves_it():
    source = ad.AnnData(np.ones((1, 1)), var=pd.DataFrame(index=["COX1"]))
    with pytest.raises(ScientificContractError, match="Ambiguous"):
        adapter().adapt(source)
    source.var["hgnc_id"] = ["HGNC:7419"]
    mapped, report = adapter().adapt(source)
    assert mapped.var_names.tolist() == ["COX1"]
    assert report["columns"][0]["approved_symbol"] == "MT-CO1"


def test_identity_collisions_and_conflicting_id_are_rejected():
    source = ad.AnnData(np.ones((1, 2)), var=pd.DataFrame(index=["ADSS", "ADSS2"]))
    with pytest.raises(ScientificContractError, match="Duplicate"):
        adapter().adapt(source)
    source = source[:, :1].copy()
    source.var["hgnc_id"] = ["HGNC:7419"]
    with pytest.raises(ScientificContractError, match="conflicts"):
        adapter().adapt(source)


def test_mismatched_gpr_structure_is_rejected():
    rxn = pd.DataFrame({"GPR": ["HGNC:1 or HGNC:7419"], "GPR-symbol": ["ADSS and COX1"]})
    with pytest.raises(ScientificContractError, match="structure"):
        build_identity_document(rxn, pd.DataFrame())


def test_frozen_loader_detects_mapping_and_database_changes(tmp_path):
    identity = tmp_path / "identity"
    database = tmp_path / "database"
    identity.mkdir()
    database.mkdir()
    atomic_write_json(database / "manifest.json", {"files": {}})
    atomic_write_json(identity / "human.json", adapter().document)
    atomic_write_json(
        identity / "manifest.json",
        {
            "database_manifest_sha256": file_sha256(database / "manifest.json"),
            "files": {"human.json": file_sha256(identity / "human.json")},
        },
    )
    assert len(GeneIdentityAdapter.load(identity, database).by_id) == 2
    original = (identity / "human.json").read_bytes()
    (identity / "human.json").write_text("{}")
    with pytest.raises(ScientificContractError, match="asset hash"):
        GeneIdentityAdapter.load(identity, database)
    (identity / "human.json").write_bytes(original)
    atomic_write_json(database / "manifest.json", {"files": {}, "changed": True})
    with pytest.raises(ScientificContractError, match="database manifest"):
        GeneIdentityAdapter.load(identity, database)
