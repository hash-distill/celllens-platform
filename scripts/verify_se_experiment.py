"""Audit genuine rerun outputs and keep excluded diagnostics explicitly marked."""

import json
from pathlib import Path

import anndata as ad
import numpy as np

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.engines.se_decode_engine import positive_log_expression_mean
from backend.app.services.scientific_analysis import _select_prediction_population
from scripts.evaluate_se_observed import dense_values

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "reports/metabolic-full-coverage-2026-10-09"


def main():
    rows = []
    for context in ("K562", "RPE1", "Jurkat", "HepG2"):
        slug = context.lower()
        original = PROOF / f"se-native-{slug}/predicted.h5ad"
        repaired = PROOF / f"se-native-signed-{slug}/predicted.h5ad"
        before, _ = _select_prediction_population(ad.read_h5ad(original), "gene", "AAMP")
        after, population = _select_prediction_population(ad.read_h5ad(repaired), "gene", "AAMP")
        expression_equal = np.array_equal(np.asarray(before.X), np.asarray(after.X))
        latent_recovers = np.array_equal(before.obsm["X_state"], np.clip(after.obsm["X_state"], 0, 14))
        if not expression_equal or not latent_recovers:
            raise ValueError("Signed latent repair changed another official model path")
        if after.obsm["X_state"].shape != (64, 2058) or not np.isfinite(after.obsm["X_state"]).all():
            raise ValueError("Invalid signed latent dimensions or values")
        if not np.any(after.obsm["X_state"] < 0):
            raise ValueError("SE latent coordinates unexpectedly lost their negative values")
        queries = PROOF / f"se-query-signed-{slug}"
        predicted = ad.read_h5ad(queries / "predicted.h5ad")
        control = ad.read_h5ad(queries / "reconstructed_control.h5ad")
        if predicted.shape != (64, 931) or control.shape != (64, 931):
            raise ValueError("Incomplete genuine SE query output")
        if predicted.var["hgnc_id"].nunique() != 931 or predicted.var["se_embedding_key"].nunique() != 931:
            raise ValueError("Ambiguous SE query identities")
        if not np.isfinite(np.asarray(predicted.X)).all() or not np.isfinite(np.asarray(control.X)).all():
            raise ValueError("Non-finite query expression")
        report = json.loads((queries / "official_completeness.json").read_text())
        summary = report["overall_summary"]
        for key, value in (
            ("n_genes_in_db_present_in_adata", 931),
            ("n_tasks_fully_covered_all", 218),
            ("n_reactions_fully_covered_all", 787),
        ):
            if summary[key] != value:
                raise ValueError(f"Incomplete official dataset availability: {key}")
        row = {
            "cell_line": context,
            "population": population,
            "native_expression_bitwise_unchanged": expression_equal,
            "clipping_signed_latent_recovers_original_cli_output": latent_recovers,
            "signed_latent_negative_fraction": float(np.mean(after.obsm["X_state"] < 0)),
            "source_prediction_sha256": file_sha256(repaired),
            "query_prediction_sha256": file_sha256(queries / "predicted.h5ad"),
            "coverage": summary,
            "production_eligible": False,
        }
        rows.append(row)
    scale_rows = []
    scale_summary = PROOF / "se-control-scale-experiment.json"
    if scale_summary.exists():
        for record in json.loads(scale_summary.read_text())["experiments"]:
            slug = record["cell_line"].lower()
            root = PROOF / f"se-query-control-scale-{slug}"
            source_path = PROOF / f"se-controls/{slug}.h5ad"
            source = ad.read_h5ad(source_path)
            values = dense_values(source.X)
            depths = positive_log_expression_mean(values)
            source_depths = dict(zip(source.obs["source_row"], depths, strict=True))
            if file_sha256(source_path) != record["condition_source_control_sha256"]:
                raise ValueError("Scale condition input hash changed")
            for name in ("reconstructed_control", "predicted"):
                path = root / f"{name}.h5ad"
                frame = ad.read_h5ad(path)
                if frame.shape != (64, 931) or not np.isfinite(np.asarray(frame.X)).all():
                    raise ValueError("Invalid genuine control-scale query matrix")
                if file_sha256(path) != record["raw_outputs"][name]["sha256"]:
                    raise ValueError("Control-scale query hash changed")
                expected = np.asarray([source_depths[row] for row in frame.obs["source_row"]])
                if not np.array_equal(np.asarray(frame.obs["se_mu_condition"]), expected):
                    raise ValueError("Scale condition differs from measured source controls")
                original_panel = ad.read_h5ad(PROOF / f"se-query-signed-{slug}/predicted.h5ad")
                if not frame.var.equals(original_panel.var):
                    raise ValueError("Control-scale query identities differ from verified panel")
            report = json.loads((root / "official_completeness.json").read_text())
            if report["source_prediction_sha256"] != file_sha256(root / "predicted.h5ad"):
                raise ValueError("Control-scale completeness report references another prediction")
            if report["overall_summary"]["n_tasks_fully_covered_all"] != 218:
                raise ValueError("Control-scale candidate lacks full task gene availability")
            scale_rows.append(
                {
                    "cell_line": record["cell_line"],
                    "input_condition_exactly_reproduced": True,
                    "query_hashes_and_identities_verified": True,
                    "production_eligible": False,
                }
            )
    measured_rows = []
    inventory_path = PROOF / "validation-candidate-inventory.json"
    for experiment_manifest in sorted(PROOF.glob("se-measured-*/manifest.json")):
        experiment = json.loads(experiment_manifest.read_text())
        if {r["cell_line"] for r in experiment["experiments"]} != {"K562", "RPE1", "Jurkat", "HepG2"}:
            raise ValueError("Measured diagnostic does not contain all four backgrounds")
        for record in experiment["experiments"]:
            root = experiment_manifest.parent / record["cell_line"].lower()
            if record["selection_inventory_sha256"] != file_sha256(inventory_path):
                raise ValueError("Measured perturbation selection changed after inference")
            native_path = root / "native/predicted.h5ad"
            if record["native_prediction_sha256"] != file_sha256(native_path):
                raise ValueError("Measured native prediction hash changed")
            native, _ = _select_prediction_population(
                ad.read_h5ad(native_path), "gene", record["perturbation"]
            )
            if native.obsm["X_state"].shape != (64, 2058) or not np.any(native.obsm["X_state"] < 0):
                raise ValueError("Measured diagnostic lost signed native latent coordinates")
            control_path = PROOF / f"se-controls/{record['cell_line'].lower()}.h5ad"
            control = ad.read_h5ad(control_path)
            if file_sha256(control_path) != record["source_control_sha256"]:
                raise ValueError("Measured diagnostic source control hash changed")
            depths = positive_log_expression_mean(dense_values(control.X))
            source_depths = dict(zip(control.obs["source_row"], depths, strict=True))
            for name in ("predicted", "reconstructed_control"):
                path = root / f"{name}.h5ad"
                query = ad.read_h5ad(path)
                if query.shape != (64, 931) or not np.isfinite(np.asarray(query.X)).all():
                    raise ValueError("Incomplete measured perturbation query")
                if file_sha256(path) != record["raw_outputs"][name]["sha256"]:
                    raise ValueError("Measured perturbation query hash changed")
                expected = np.asarray([source_depths[row] for row in query.obs["source_row"]])
                if not np.array_equal(np.asarray(query.obs["se_mu_condition"]), expected):
                    raise ValueError("Measured perturbation condition was not derived from source controls")
                panel = ad.read_h5ad(PROOF / "se-query-signed-k562/predicted.h5ad")
                if not query.var.equals(panel.var):
                    raise ValueError("Measured perturbation gene query identities changed")
            measured_path = root / "measured.h5ad"
            measured = ad.read_h5ad(measured_path)
            if file_sha256(measured_path) != record["measured_sha256"]:
                raise ValueError("Real perturbation measurement hash changed")
            if measured.obs["source_row"].tolist() != record["measured_source_rows"]:
                raise ValueError("Real perturbation source rows changed")
            if (
                measured.obs["source_row"].duplicated().any()
                or not (measured.obs["gene"] == record["perturbation"]).all()
            ):
                raise ValueError("Measured cells were duplicated or selected from another perturbation")
            completeness = json.loads((root / "official_completeness.json").read_text())
            if completeness["source_prediction_sha256"] != file_sha256(root / "predicted.h5ad"):
                raise ValueError("Measured perturbation completeness references another output")
            if completeness["overall_summary"]["n_tasks_fully_covered_all"] != 218:
                raise ValueError("Measured perturbation query lacks full task availability")
            measured_rows.append(
                {
                    "cell_line": record["cell_line"],
                    "perturbation": record["perturbation"],
                    "query_identities_hashes_and_conditions_verified": True,
                    "real_measured_cell_selection_verified": True,
                    "production_eligible": False,
                }
            )
    preserved = {}
    for run_id in (
        "run_4d0b3038ea8642af",
        "run_30dc0a6410ca4e2d",
        "run_5e06e0fd0b9140a7",
        "run_1b544f2cff4d400a",
    ):
        root = ROOT / f"data/derived/runs/{run_id}"
        manifest = json.loads((root / "manifest.json").read_text())
        for filename, record in manifest["outputs"].items():
            if file_sha256(root / filename) != record["sha256"]:
                raise ValueError(f"Original genuine run changed: {run_id}/{filename}")
        preserved[run_id] = {
            "manifest_sha256": file_sha256(root / "manifest.json"),
            "original_outputs_match_frozen_manifest": True,
        }
    atomic_write_json(
        PROOF / "se-experiment-verification.json",
        {
            "runs": rows,
            "control_scale_runs": scale_rows,
            "measured_diagnostics": measured_rows,
            "original_runs": preserved,
        },
    )
    atomic_write_json(
        PROOF / "excluded-diagnostics.json",
        {
            "directories": [f"se-native-{c}" for c in ("k562", "rpe1", "jurkat", "hepg2")]
            + [f"se-query-{c}" for c in ("k562", "rpe1", "jurkat", "hepg2")]
            + [f"se-native-unclipped-{c}" for c in ("k562", "rpe1", "jurkat", "hepg2")]
            + [f"se-query-unclipped-{c}" for c in ("k562", "rpe1", "jurkat", "hepg2")],
            "incomplete_observed_trials": ["se-observed-diagnostic", "se-observed-diagnostic-weighted"],
            "figures": [
                "real-se-predictions.png",
                "real-se-predictions.svg",
                "real-se-unclipped-predictions.png",
                "real-se-unclipped-predictions.svg",
            ],
            "projection_data": [
                "real-se-projection-coordinates.csv",
                "real-se-projection-transform.npz",
                "real-se-projection-manifest.json",
                "real-se-unclipped-projection-coordinates.csv",
                "real-se-unclipped-projection-transform.npz",
                "real-se-unclipped-projection-manifest.json",
            ],
            "reason": "Official CLI clipped signed SE latent coordinates; retain for diagnosis only",
            "accepted_candidate_directories": [
                f"se-query-signed-{c}" for c in ("k562", "rpe1", "jurkat", "hepg2")
            ],
            "production_eligible": False,
        },
    )
    print(
        f"Verified four signed predictions, 931-gene queries, {len(scale_rows)} control-scale trials, "
        f"{len(measured_rows)} measured diagnostics and preserved original runs"
    )


if __name__ == "__main__":
    main()
