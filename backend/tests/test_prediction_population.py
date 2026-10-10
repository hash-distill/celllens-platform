import json

import anndata as ad
import numpy as np
import pandas as pd
import pytest

from backend.app.core.errors import ScientificContractError
from backend.app.core.registry import RegistryEntry
from backend.app.engines.metabolic_engine import MetabolicResult
from backend.app.schemas import CreateRunRequest
from backend.app.services import scientific_analysis
from backend.tests.test_task_trace import fixture_data


def cells(values, labels):
    data = ad.AnnData(np.array(values, dtype=float))
    data.var_names = ["GENE1", "GENE2"]
    data.obs["gene"] = labels
    return data


def test_population_selection_preserves_target_matrix_and_excludes_simulated_controls():
    data = cells([[9, 1], [1, 10000], [8, 2]], ["myc", "non-targeting", "MYC"])
    data.obsm["X_hvg"] = data.X * 2
    selected, metadata = scientific_analysis._select_prediction_population(data, "gene", "MYC")
    assert selected.n_obs == 2 and data.n_obs == 3
    np.testing.assert_array_equal(selected.obsm["X_hvg"], [[18, 2], [16, 4]])
    assert metadata["selected_prediction_cells"] == 2
    assert metadata["excluded_prediction_cells"] == 1
    assert metadata["status"] == "matched"


@pytest.mark.parametrize("column", ["gene", "absent"])
def test_population_selection_rejects_missing_target_or_registered_column(column):
    data = cells([[1, 2]], ["non-targeting"])
    with pytest.raises(ScientificContractError):
        scientific_analysis._select_prediction_population(data, column, "MYC")


def test_all_analysis_outputs_ignore_simulated_control_rows(tmp_path, monkeypatch):
    control = cells([[1, 1], [2, 2]], ["non-targeting", "non-targeting"])
    target = cells([[9, 1], [8, 2]], ["MYC", "MYC"])
    mixed = ad.concat([target, cells([[1, 10000]], ["non-targeting"])], index_unique="-")
    mixed.var_names = target.var_names
    control.write_h5ad(tmp_path / "control.h5ad")
    target.write_h5ad(tmp_path / "target.h5ad")
    mixed.write_h5ad(tmp_path / "mixed.h5ad")
    database, _, _, _, _ = fixture_data()
    database["task_by_gene"] = pd.DataFrame({"GENE1": [1]}, index=["task_a"])
    monkeypatch.setattr(scientific_analysis, "_load_frozen_database", lambda root: (database, "test-v1"))

    class Engine:
        def run(self, combined, *, database, database_version, completeness):
            assert combined.obs["celllens_source"].value_counts().to_dict() == {"control": 2, "predicted": 2}
            # Scores depend on the actual expression received by the downstream engine.
            values = np.asarray(combined.X)[:, 0]
            return MetabolicResult(
                pd.DataFrame({"task_a": values}, index=combined.obs_names),
                pd.DataFrame({"rxn_a": values}, index=combined.obs_names),
                pd.DataFrame(),
                completeness,
                database_version,
            )

    service = scientific_analysis.ScientificAnalysisService(tmp_path, Engine())
    model = RegistryEntry({"perturbation_column": "gene", "expression_scale": "log1p_cp10k"}, tmp_path)
    dataset = RegistryEntry({"control_path": "control.h5ad", "expression_scale": "log1p_cp10k"}, tmp_path)
    request = CreateRunRequest(cell_line="K562", perturbation="MYC")
    for source in ["target", "mixed"]:
        output = tmp_path / source
        output.mkdir()
        service.run("run_test", request, model, dataset, tmp_path / f"{source}.h5ad", output)
    for name in ["gene_deltas.csv", "task_trace.json"]:
        assert (tmp_path / "target" / name).read_bytes() == (tmp_path / "mixed" / name).read_bytes()
    for name in ["metabolic_task_scores.csv", "reaction_scores.csv"]:
        before = pd.read_csv(tmp_path / "target" / name, index_col=0).reset_index(drop=True)
        after = pd.read_csv(tmp_path / "mixed" / name, index_col=0).reset_index(drop=True)
        pd.testing.assert_frame_equal(before, after)
    projection = json.loads((tmp_path / "mixed/projection.json").read_text())
    assert sum(p["source"] == "predicted" for p in projection["points"]) == 2
    assert projection["population_selection"]["excluded_prediction_cells"] == 1


def test_analysis_applies_identity_before_alignment_and_records_both_sources(tmp_path, monkeypatch):
    from backend.app.services.gene_identity import GeneIdentityAdapter, build_identity_document

    control = cells([[1, 1], [2, 2]], ["non-targeting", "non-targeting"])
    target = cells([[9, 1], [8, 2]], ["MYC", "MYC"])
    target.var_names = ["GENE1NEW", "GENE2"]
    control.write_h5ad(tmp_path / "control.h5ad")
    target.write_h5ad(tmp_path / "target.h5ad")
    hgnc = pd.DataFrame(
        [["HGNC:1", "GENE1NEW", "GENE1", ""]], columns=["hgnc_id", "symbol", "prev_symbol", "alias_symbol"]
    )
    rules = pd.DataFrame({"GPR": ["HGNC:1"], "GPR-symbol": ["GENE1"]})
    adapter = GeneIdentityAdapter(build_identity_document(rules, hgnc), provenance={"fixture": True})
    monkeypatch.setattr(GeneIdentityAdapter, "load", lambda *args: adapter)

    def unavailable(root):
        raise FileNotFoundError("test focuses on expression adaptation")

    monkeypatch.setattr(scientific_analysis, "_load_frozen_database", unavailable)
    output = tmp_path / "result"
    output.mkdir()
    result = scientific_analysis.ScientificAnalysisService(tmp_path, gene_identity_root=tmp_path).run(
        "run_identity",
        CreateRunRequest(cell_line="K562", perturbation="MYC"),
        RegistryEntry({"perturbation_column": "gene", "expression_scale": "log1p_cp10k"}, tmp_path),
        RegistryEntry({"control_path": "control.h5ad", "expression_scale": "log1p_cp10k"}, tmp_path),
        tmp_path / "target.h5ad",
        output,
    )
    genes = pd.read_csv(output / "gene_deltas.csv", index_col=0)
    assert genes.index.tolist() == ["GENE1", "GENE2"]
    assert genes.loc["GENE1", "predicted_delta"] > 0
    report = json.loads((output / "gene_identity.json").read_text())
    assert report["sources"]["predicted"]["columns"][0]["source_symbol"] == "GENE1NEW"
    assert output / "gene_identity.json" in result.artifacts
