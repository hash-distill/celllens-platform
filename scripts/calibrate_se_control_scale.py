"""Test a control-derived SE mu condition without tuning on perturbation labels.

The installed training code uses mean nonzero log target expression for its
one-dimensional RDA condition. Estimate this from measured control features and
reuse each source control's condition for its simulated prediction. This remains
an approximation to sampled training targets, not a proven encoder pairing.
"""

import json
from pathlib import Path
from typing import cast

import anndata as ad
import numpy as np
import pandas as pd
import yaml

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.engines.se_decode_engine import (
    SEGeneDecoder,
    metabolic_query_keys,
    positive_log_expression_mean,
)
from backend.app.services.completeness import compute_official_completeness
from backend.app.services.gene_identity import GeneIdentityAdapter
from backend.app.services.scientific_analysis import _load_frozen_database, _select_prediction_population
from scripts.evaluate_se_observed import compare_deltas, dense_values, weighted_observed_mean

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "reports/metabolic-full-coverage-2026-10-09"


def main():
    summary_path = PROOF / "se-control-scale-experiment.json"
    if summary_path.exists():
        raise ValueError(f"Preserve existing control-scale experiment: {summary_path}")
    baseline = {
        r["cell_line"]: r
        for r in json.loads((PROOF / "se-query-signed-experiment.json").read_text())["experiments"]
    }
    observations_root = PROOF / "se-observed-diagnostic-shared-batches"
    observations = {
        r["cell_line"]: r
        for r in json.loads((observations_root / "manifest.json").read_text())["diagnostics"]
    }
    database_root = ROOT / "data/registry/sccellfie/human"
    adapter = GeneIdentityAdapter.load(ROOT / "data/registry/gene_identity", database_root)
    database, version = _load_frozen_database(database_root)
    config = yaml.safe_load((ROOT / "models/se600m-epoch16/config.yaml").read_text())
    if config["model"]["rda"] is not True:
        raise ValueError("This condition estimator requires the registered SE RDA model")
    decoder = SEGeneDecoder(ROOT / "models/se600m-epoch16", device="cuda")
    symbols, keys = metabolic_query_keys(adapter, set(decoder.protein))
    import state.emb.nn.model as installed_model

    records = []
    for context in ("K562", "RPE1", "Jurkat", "HepG2"):
        slug = context.lower()
        output = PROOF / f"se-query-control-scale-{slug}"
        if output.exists():
            raise ValueError(f"Preserve existing scale trial: {output}")
        output.mkdir()
        control_path = PROOF / f"se-controls/{slug}.h5ad"
        native_path = PROOF / f"se-native-signed-{slug}/predicted.h5ad"
        control = ad.read_h5ad(control_path)
        prediction, _ = _select_prediction_population(ad.read_h5ad(native_path), "gene", "AAMP")
        control_depths = positive_log_expression_mean(dense_values(control.X))
        source_depth = dict(zip(control.obs["source_row"], control_depths, strict=True))
        if not set(prediction.obs["source_row"]) <= source_depth.keys():
            raise ValueError("Prediction source controls cannot be matched to measured scale estimates")
        prediction_depths = np.asarray([source_depth[row] for row in prediction.obs["source_row"]])
        panel = ad.read_h5ad(PROOF / f"se-query-signed-{slug}/predicted.h5ad").var.copy()
        raw = {}
        for name, frame, depths in (
            ("reconstructed_control", control, control_depths),
            ("predicted", prediction, prediction_depths),
        ):
            raw[name] = decoder.decode(np.asarray(frame.obsm["X_state"]), keys, read_depth=depths)
            obs = cast(pd.DataFrame, frame.obs).copy()
            obs["se_mu_condition"] = depths
            result = ad.AnnData(raw[name], obs=obs, var=cast(pd.DataFrame, panel))
            result.obsm["X_state"] = np.asarray(frame.obsm["X_state"]).copy()
            result.uns["celllens_provenance"] = {
                "kind": name,
                "expression_scale": "unmodified SE log target regression output",
                "condition": "mean nonzero measured source-control expression across 6546 features",
                "condition_is_estimated": True,
                "condition_changes_after_perturbation": False,
                "encoder_pairing_verified": False,
                "source_sha256": file_sha256(
                    control_path if name == "reconstructed_control" else native_path
                ),
            }
            result.write_h5ad(output / f"{name}.h5ad", compression="gzip")
        control, _ = adapter.adapt(control)
        shared = [g for g in symbols if g in control.var_names]
        columns = [symbols.index(g) for g in shared]
        measured_control = dense_values(control[:, shared].X)
        reconstruction = raw["reconstructed_control"][:, columns]
        record = {
            "cell_line": context,
            "perturbation": "AAMP",
            "output_genes": len(symbols),
            "decoder": decoder.provenance,
            "installed_training_model_sha256": file_sha256(Path(installed_model.__file__)),
            "condition_contract": "StateEmbeddingModel.shared_step mu = nanmean(Y excluding zeros)",
            "estimator_scope": "measured 6546 source features; sampled SE training task not reproduced",
            "condition_source_control_sha256": file_sha256(control_path),
            "depth_statistics": {
                "min": float(control_depths.min()),
                "mean": float(control_depths.mean()),
                "max": float(control_depths.max()),
            },
            "raw_outputs": {
                name: {
                    "sha256": file_sha256(output / f"{name}.h5ad"),
                    "negative_fraction": float(np.mean(values < 0)),
                    "minimum": float(values.min()),
                    "maximum": float(values.max()),
                }
                for name, values in raw.items()
            },
            "reconstruction_diagnostic": {
                "measured_genes": len(shared),
                "mean_gene_pearson": float(
                    np.corrcoef(measured_control.mean(0), reconstruction.mean(0))[0, 1]
                ),
                "rmse_in_source_values": float(np.sqrt(np.mean((measured_control - reconstruction) ** 2))),
                "baseline_read_depth_4_rmse": baseline[context]["reconstruction_diagnostic"][
                    "rmse_in_source_values"
                ],
            },
            "production_eligible": False,
            "metabolic_scores_generated": False,
            "held_out_validation": False,
            "unresolved": [
                "exact encoder checkpoint pairing not established",
                "mean over measured features approximates sampled training target mean",
                "raw regression outputs can be negative",
                "405 metabolic genes have no measurements in this source panel",
                "held-out perturbation performance not established",
            ],
        }
        observed_report = observations[context]
        if observed_report.get("status") == "not_comparable":
            record["observed_diagnostic"] = observed_report
        else:
            measured, _ = adapter.adapt(ad.read_h5ad(observations_root / f"{slug}-measured.h5ad"))
            valid_batches = [int(b) for b in observed_report["batch_weights"]]
            keep = np.isin(np.asarray(control.obs["gem_group"]), valid_batches)
            control_batches = np.asarray(control.obs["gem_group"])[keep]
            observed_delta = weighted_observed_mean(
                measured[:, shared].X, np.asarray(measured.obs["gem_group"]), control_batches
            )
            observed_delta -= measured_control[keep].mean(0)
            predicted_delta = weighted_observed_mean(
                raw["predicted"][:, columns], np.asarray(prediction.obs["gem_group"]), control_batches
            )
            predicted_delta -= raw["reconstructed_control"][keep][:, columns].mean(0)
            record["observed_diagnostic"] = {
                **compare_deltas(predicted_delta, observed_delta),
                "measured_cells": len(measured),
                "control_cells": int(keep.sum()),
                "measured_sha256": file_sha256(observations_root / f"{slug}-measured.h5ad"),
                "sampling_and_weights_manifest_sha256": file_sha256(observations_root / "manifest.json"),
                "baseline_read_depth_4": observed_report["se_query"],
            }
            pd.DataFrame(
                {
                    "gene": shared,
                    "observed_delta": observed_delta,
                    "control_scale_query_delta": predicted_delta,
                }
            ).to_csv(output / "observed_deltas.csv", index=False)
        pd.DataFrame(
            {
                "gene": symbols,
                "reconstructed_control": raw["reconstructed_control"].mean(0),
                "predicted": raw["predicted"].mean(0),
            }
        ).assign(predicted_delta=lambda frame: frame["predicted"] - frame["reconstructed_control"]).to_csv(
            output / "raw_gene_deltas.csv", index=False
        )
        completeness = compute_official_completeness(symbols, database, version)
        completeness["source_prediction_sha256"] = file_sha256(output / "predicted.h5ad")
        atomic_write_json(output / "official_completeness.json", completeness)
        record["coverage"] = completeness["overall_summary"]
        atomic_write_json(output / "manifest.json", record)
        records.append(record)
        print(
            json.dumps(
                {
                    "context": context,
                    "depth": record["depth_statistics"],
                    "reconstruction": record["reconstruction_diagnostic"],
                    "observed": record["observed_diagnostic"],
                    "prediction_negative_fraction": record["raw_outputs"]["predicted"]["negative_fraction"],
                }
            ),
            flush=True,
        )
    atomic_write_json(summary_path, {"experiments": records, "production_eligible": False})


if __name__ == "__main__":
    main()
