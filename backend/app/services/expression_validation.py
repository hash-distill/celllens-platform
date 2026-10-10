"""Expression and DE diagnostics on declared log1p(CP10K), independent of metabolism."""

from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from backend.app.core.errors import ScientificContractError
from backend.app.services.expression_scale import validate_expression


def correlation(a: np.ndarray, b: np.ndarray, *, ranked: bool = False) -> float | None:
    if len(a) < 2 or np.std(a) == 0 or np.std(b) == 0:
        return None
    result = float(cast(Any, spearmanr(a, b))[0] if ranked else np.corrcoef(a, b)[0, 1])
    return result if np.isfinite(result) else None


def compare_expression_deltas(predicted: np.ndarray, observed: np.ndarray) -> dict[str, Any]:
    predicted, observed = np.asarray(predicted, dtype=float), np.asarray(observed, dtype=float)
    if predicted.shape != observed.shape or predicted.ndim != 1 or not len(predicted):
        raise ScientificContractError("Delta validation requires a nonempty identical gene panel")
    if not np.isfinite(predicted).all() or not np.isfinite(observed).all():
        raise ScientificContractError("Delta validation requires finite values")
    mse = float(np.mean((predicted - observed) ** 2))
    baseline = float(np.mean(observed**2))
    ratio = mse / baseline if baseline > 0 else None
    return {
        "gene_count": len(predicted),
        "mae": float(np.mean(np.abs(predicted - observed))),
        "mse": mse,
        "rmse": float(np.sqrt(mse)),
        "signed_delta_pearson": correlation(predicted, observed),
        "absolute_delta_pearson": correlation(np.abs(predicted), np.abs(observed)),
        "signed_delta_spearman": correlation(predicted, observed, ranked=True),
        "direction_agreement": float(np.mean(np.sign(predicted) == np.sign(observed))),
        "no_change_mae": float(np.mean(np.abs(observed))),
        "no_change_mse": baseline,
        "mse_relative_to_no_change": ratio,
        "mse_improvement_over_no_change": 1 - ratio if ratio is not None else None,
        "beats_no_change_mse": mse < baseline if baseline > 0 else None,
    }


def differential_expression(control: Any, target: Any) -> pd.DataFrame:
    import anndata as ad
    import scanpy as sc

    if min(control.n_obs, target.n_obs) < 2:
        raise ScientificContractError("Wilcoxon diagnostics require at least two cells per population")
    c, t = control.copy(), target.copy()
    c.obs["evaluation_group"], t.obs["evaluation_group"] = "control", "target"
    combined = ad.concat([c, t], index_unique="-")
    combined.uns["log1p"] = {"base": None}
    sc.tl.rank_genes_groups(
        combined,
        groupby="evaluation_group",
        groups=["target"],
        reference="control",
        method="wilcoxon",
        corr_method="benjamini-hochberg",
        tie_correct=True,
        use_raw=False,
        n_genes=combined.n_vars,
    )
    frame = sc.get.rank_genes_groups_df(combined, group="target").set_index("names")
    return cast(
        pd.DataFrame, frame.reindex(control.var_names)[["scores", "logfoldchanges", "pvals", "pvals_adj"]]
    )


def compare_de(predicted: pd.DataFrame, observed: pd.DataFrame) -> dict[str, Any]:
    from sklearn.metrics import average_precision_score

    ps = set(predicted.index[predicted["pvals_adj"] < 0.05])
    os = set(observed.index[observed["pvals_adj"] < 0.05])
    shared = sorted(ps & os)
    n = len(os)
    pred_order = predicted.loc[list(ps), "logfoldchanges"].abs().sort_values(ascending=False).index
    obs_order = observed.loc[list(os), "logfoldchanges"].abs().sort_values(ascending=False).index
    truth = (observed["pvals_adj"] < 0.05).astype(int).to_numpy()
    probability_rank = -np.log10(np.maximum(predicted["pvals_adj"].to_numpy(), 1e-300))
    result: dict[str, Any] = {
        "observed_significant_genes": n,
        "predicted_significant_genes": len(ps),
        "shared_significant_genes": len(shared),
        "effect_size_absolute_error": abs(len(ps) - n),
        "overlap_at_n": len(set(pred_order[:n]) & set(obs_order[:n])) / n if n else None,
        "direction_agreement_on_shared_degs": float(
            np.mean(
                np.sign(predicted.loc[shared, "logfoldchanges"])
                == np.sign(observed.loc[shared, "logfoldchanges"])
            )
        )
        if shared
        else None,
        "average_precision": float(average_precision_score(truth, probability_rank)) if n else None,
        "auprc_definition": "average precision of observed BH-FDR<0.05 labels ranked by predicted adjusted p",
        "no_change_average_precision": float(truth.mean()) if n else None,
        "no_change_overlap_at_n": 0.0 if n else None,
        "no_change_predicted_significant_genes": 0,
    }
    for k in (50, 100, 200):
        denominator = min(k, len(observed))
        result[f"overlap_at_{k}"] = len(set(pred_order[:k]) & set(obs_order[:k])) / denominator
    return result


def build_expression_validation(
    control: Any, predicted: Any, observed: Any, output_dir: Path
) -> tuple[dict[str, Any], list[Path]]:
    for source in (control, predicted, observed):
        if source.uns.get("celllens_expression", {}).get("scale") != "log1p_cp10k":
            raise ScientificContractError("Validation requires declared log1p_cp10k expression scale")
        validate_expression(source.X)
    if not (control.var_names.equals(predicted.var_names) and control.var_names.equals(observed.var_names)):
        raise ScientificContractError("Validation gene identities and order differ")
    means = [np.asarray(source.X.mean(axis=0)).reshape(-1) for source in (control, predicted, observed)]
    expression = compare_expression_deltas(means[1] - means[0], means[2] - means[0])
    pred_de, real_de = differential_expression(control, predicted), differential_expression(control, observed)
    combined = pd.concat({"predicted": pred_de, "observed": real_de}, axis=1)
    combined.columns = [f"{source}_{metric}" for source, metric in combined.columns]
    combined.index.name = "gene"
    path = output_dir / "differential_expression.csv"
    combined.to_csv(path)
    document = {
        "schema_version": 2,
        "implementation": "CellLens paper-aligned expression diagnostics; not an official Cell-Eval export",
        "protocol_status": "unconfirmed",
        "held_out_validation": False,
        "expression": expression,
        "differential_expression": compare_de(pred_de, real_de),
        "parameters": {
            "expression_scale": "log1p_cp10k",
            "mean": "per-cell log expression mean",
            "de_method": "wilcoxon",
            "tie_correct": True,
            "multiple_testing": "benjamini-hochberg",
            "fdr": 0.05,
            "baseline": "no_change: predicted perturbation equals measured control",
            "population_counts": {
                "control": control.n_obs,
                "predicted": predicted.n_obs,
                "observed": observed.n_obs,
            },
        },
        "package_versions": {name: version(name) for name in ("scanpy", "scipy", "scikit-learn")},
        "multi_perturbation_metrics": {
            "perturbation_discrimination": None,
            "effect_size_correlation": None,
            "reason": "requires a frozen evaluation containing multiple perturbations",
        },
        "unavailable_baselines": {
            "context_mean": "requires training-only perturbed context data",
            "perturbation_mean": "requires training-only other-context effects",
            "linear": "requires a model fitted only on declared training data",
        },
        "warnings": [
            "Matched observations do not prove checkpoint training exclusion or held-out generalization.",
            "Cell-level Wilcoxon is a diagnostic; cells are not independent biological replicates.",
            "All-gene direction agreement differs from direction agreement on shared significant DEGs.",
        ],
    }
    return document, [path]
