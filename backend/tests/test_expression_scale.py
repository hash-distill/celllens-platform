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


def test_log_expression_mean_is_not_normalized_or_logged_again():
    frame = ad.AnnData(np.log1p([[100.0, 1.0], [0.0, 9.0]]))
    frame.uns["celllens_expression"] = {"scale": "log1p_cp10k"}
    expected = np.asarray(frame.X).mean(axis=0)
    np.testing.assert_allclose(scientific_analysis._normalized_gene_mean(frame), expected)


def test_pipeline_passes_linear_cp10k_without_rescaling_the_hvg_panel(tmp_path, monkeypatch):
    database, _, _, _, _ = fixture_data()
    database["task_by_gene"] = pd.DataFrame({"GENE1": [1]}, index=["task_a"])
    monkeypatch.setattr(scientific_analysis, "_load_frozen_database", lambda root: (database, "fixture"))
    control = ad.AnnData(np.log1p([[100.0, 1.0], [200.0, 2.0]]))
    control.var_names = ["GENE1", "GENE2"]
    predicted = control.copy()
    predicted.X = np.log1p([[300.0, 3.0], [400.0, 4.0]])
    control.write_h5ad(tmp_path / "control.h5ad")
    predicted.write_h5ad(tmp_path / "predicted.h5ad")
    received = []

    class Engine:
        def run(self, combined, *, database, database_version, completeness):
            received.append(combined.copy())
            scores = pd.DataFrame({"task_a": np.asarray(combined.X)[:, 0]}, index=combined.obs_names)
            return MetabolicResult(
                scores,
                scores.rename(columns={"task_a": "rxn_a"}),
                pd.DataFrame(),
                completeness,
                database_version,
            )

    output = tmp_path / "result"
    output.mkdir()
    result = scientific_analysis.ScientificAnalysisService(tmp_path, Engine()).run(
        "run_scale",
        CreateRunRequest(cell_line="K562", perturbation="MYC"),
        RegistryEntry({"expression_scale": "log1p_cp10k"}, tmp_path),
        RegistryEntry({"control_path": "control.h5ad", "expression_scale": "log1p_cp10k"}, tmp_path),
        tmp_path / "predicted.h5ad",
        output,
    )
    assert received, result.summary["warnings"]
    np.testing.assert_allclose(received[0].X, [[100.0, 1.0], [200.0, 2.0], [300.0, 3.0], [400.0, 4.0]])
    assert received[0].uns["normalization"]["target_sum"] == 10_000
    assert received[0].uns["celllens_expression"]["scale"] == "cp10k"
    table = pd.read_csv(output / "gene_deltas.csv", index_col=0)
    np.testing.assert_allclose(table["control"], control.X.mean(axis=0))


def test_unknown_expression_scale_is_rejected_before_scientific_results(tmp_path):
    control = ad.AnnData(np.array([[1.0, 2.0], [2.0, 1.0]]))
    control.var_names = ["GENE1", "GENE2"]
    control.write_h5ad(tmp_path / "control.h5ad")
    output = tmp_path / "result"
    output.mkdir()
    with pytest.raises(ScientificContractError, match="expression scale"):
        scientific_analysis.ScientificAnalysisService(tmp_path).run(
            "run_unknown",
            CreateRunRequest(cell_line="K562", perturbation="MYC"),
            RegistryEntry({}, tmp_path),
            RegistryEntry({"control_path": "control.h5ad"}, tmp_path),
            tmp_path / "control.h5ad",
            output,
        )
    assert not (output / "gene_deltas.csv").exists()


def test_validation_reports_gene_accuracy_and_no_change_baseline_without_metabolic_database(tmp_path):
    rng = np.random.default_rng(42)
    control = ad.AnnData(np.log1p(rng.uniform(1, 2, size=(24, 3))))
    control.var_names = ["GENE1", "GENE2", "GENE3"]
    observed = control.copy()
    observed.X[:, 0] += 1.5
    observed.X[:, 2] -= 0.2
    control.write_h5ad(tmp_path / "control.h5ad")
    observed.write_h5ad(tmp_path / "observed.h5ad")
    output = tmp_path / "result"
    output.mkdir()
    scientific_analysis.ScientificAnalysisService(tmp_path).run(
        "run_accuracy",
        CreateRunRequest(cell_line="K562", perturbation="MYC", mode="validation"),
        RegistryEntry({"expression_scale": "log1p_cp10k"}, tmp_path),
        RegistryEntry(
            {
                "control_path": "control.h5ad",
                "observed_path": "observed.h5ad",
                "expression_scale": "log1p_cp10k",
            },
            tmp_path,
        ),
        tmp_path / "observed.h5ad",
        output,
    )
    path = output / "validation_metrics.json"
    assert path.is_file(), "Expression validation must survive unavailable metabolic analysis"
    document = json.loads(path.read_text())
    assert document["expression"]["mse"] == pytest.approx(0)
    assert document["expression"]["mse_relative_to_no_change"] == pytest.approx(0)
    assert document["expression"]["direction_agreement"] == pytest.approx(1)
    assert document["differential_expression"]["observed_significant_genes"] >= 1
    assert document["differential_expression"]["overlap_at_n"] == pytest.approx(1)
    assert document["protocol_status"] == "unconfirmed"
    assert document["held_out_validation"] is False


def test_raw_count_conversion_uses_full_library_counts_and_keeps_source_unchanged():
    from backend.app.services.expression_scale import linear_cp10k, prepare_log_expression

    source = ad.AnnData(np.array([[10.0, 10.0], [0.0, 5.0]]))
    source.obs["full_counts"] = [100.0, 200.0]
    saved = source.X.copy()
    prepared = prepare_log_expression(source, "raw_counts", total_counts_key="full_counts")
    np.testing.assert_allclose(linear_cp10k(prepared).X, [[1000.0, 1000.0], [0.0, 250.0]])
    np.testing.assert_array_equal(source.X, saved)
    with pytest.raises(ScientificContractError, match="full-library"):
        prepare_log_expression(source, "raw_counts")


def test_sparse_cp10k_conversion_preserves_zeros_and_does_not_renormalize():
    from scipy.sparse import csr_matrix, issparse

    from backend.app.services.expression_scale import linear_cp10k, prepare_log_expression

    source = ad.AnnData(csr_matrix([[100.0, 0.0], [2.0, 3.0]]))
    result = linear_cp10k(prepare_log_expression(source, "cp10k"))
    assert issparse(result.X)
    np.testing.assert_allclose(result.X.toarray(), source.X.toarray())


def test_zero_observed_effect_does_not_claim_a_baseline_gain():
    from backend.app.services.expression_validation import compare_expression_deltas

    result = compare_expression_deltas(np.zeros(3), np.zeros(3))
    assert result["mse_relative_to_no_change"] is None
    assert result["beats_no_change_mse"] is None
    assert result["signed_delta_pearson"] is None


def test_empty_deg_sets_are_undefined_not_a_perfect_score():
    from backend.app.services.expression_validation import compare_de

    frame = pd.DataFrame({"pvals_adj": [1.0, 1.0], "logfoldchanges": [0.0, 0.0]}, index=["A", "B"])
    result = compare_de(frame, frame)
    assert result["overlap_at_n"] is None
    assert result["average_precision"] is None
    assert result["direction_agreement_on_shared_degs"] is None


def test_validation_excludes_unshared_batches_without_copying_observed_cells():
    control = ad.AnnData(np.array([[1.0], [2.0], [9999.0]]))
    control.obs["batch"] = ["a", "a", "b"]
    target = control[:2].copy()
    c, p, o, report = scientific_analysis._match_validation_batches(control, target, target, "batch")
    assert c.n_obs == p.n_obs == o.n_obs == 2
    np.testing.assert_array_equal(c.X, [[1.0], [2.0]])
    assert report["common_batches"] == ["a"]
    assert control.n_obs == 3
