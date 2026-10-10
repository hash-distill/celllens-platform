"""Run official ST-SE on unchanged official X_state, without activating new models."""

import json
from pathlib import Path

import anndata as ad
import numpy as np

from backend.app.core.registry import RegistryEntry
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.engines.state_engine import StateCliEngine, StateRunInput
from backend.app.engines.state_se_runner import OFFICIAL_INFER_SHA256
from backend.app.services.completeness import compute_official_completeness
from backend.app.services.gene_identity import GeneIdentityAdapter
from backend.app.services.scientific_analysis import _load_frozen_database, _select_prediction_population

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "reports/metabolic-full-coverage-2026-10-09"


def main():
    database_root = ROOT / "data/registry/sccellfie/human"
    adapter = GeneIdentityAdapter.load(ROOT / "data/registry/gene_identity", database_root)
    database, version = _load_frozen_database(database_root)
    engine = StateCliEngine(device="cuda")
    summaries = []
    for context in ("K562", "RPE1", "Jurkat", "HepG2"):
        slug = context.lower()
        model_dir = ROOT / f"models/st-se-full-{slug}"
        manifest = json.loads((model_dir / "source_manifest.json").read_text())
        for filename, digest in manifest["files"].items():
            if file_sha256(model_dir / filename) != digest:
                raise ValueError(f"Pinned ST-SE asset changed: {filename}")
        output = PROOF / f"se-native-signed-{slug}"
        output.mkdir(exist_ok=True)
        predicted_path = output / "predicted.h5ad"
        if predicted_path.exists():
            raise ValueError(f"Preserve existing prediction: {predicted_path}")
        model = RegistryEntry(
            {
                "id": f"experimental-st-se-full-{slug}",
                "model_dir": str(model_dir.relative_to(ROOT)),
                "checkpoint_path": str((model_dir / "checkpoints/best.ckpt").relative_to(ROOT)),
                "embed_key": "X_state",
                "perturbation_column": "gene",
                "cell_type_column": "cell_line",
                "control_perturbation": "non-targeting",
            },
            ROOT,
        )
        control_path = PROOF / f"se-controls/{slug}.h5ad"
        engine.infer(StateRunInput(context, "AAMP", control_path, 64, 42), model, predicted_path)
        predicted = ad.read_h5ad(predicted_path)
        target, population = _select_prediction_population(predicted, "gene", "AAMP")
        if target.obsm["X_state"].shape != (64, 2058):
            raise ValueError("ST-SE latent output dimensions differ from registered release")
        if not np.isfinite(target.obsm["X_state"]).all():
            raise ValueError("Non-finite actual ST-SE output")
        if not np.any(target.obsm["X_state"] < 0):
            raise ValueError("SE prediction has no signed negative coordinates; inspect clipping")
        legacy_path = PROOF / f"se-native-{slug}/predicted.h5ad"
        differential = None
        if legacy_path.exists():
            legacy, _ = _select_prediction_population(ad.read_h5ad(legacy_path), "gene", "AAMP")
            same_expression = np.array_equal(np.asarray(target.X), np.asarray(legacy.X))
            recovers_legacy = np.array_equal(np.clip(target.obsm["X_state"], 0, 14), legacy.obsm["X_state"])
            if not same_expression or not recovers_legacy:
                raise ValueError("Latent clipping repair changed another official prediction path")
            differential = {
                "native_expression_bitwise_unchanged": same_expression,
                "clipping_signed_latent_recovers_original_cli_output": recovers_legacy,
                "original_prediction_sha256": file_sha256(legacy_path),
            }
        target, identity = adapter.adapt(target)
        report = compute_official_completeness(target.var_names.tolist(), database, version)
        report.update(
            source_prediction_sha256=file_sha256(predicted_path), analysis_kind="official ST-SE native head"
        )
        atomic_write_json(output / "official_completeness.json", report)
        atomic_write_json(output / "gene_identity.json", identity)
        summary = {
            "cell_line": context,
            "perturbation": "AAMP",
            "requested_cells": 64,
            "prediction_sha256": file_sha256(predicted_path),
            "st_source": manifest,
            "population": population,
            "expression_slot": "X",
            "latent_slot": "obsm/X_state",
            "output_genes": target.n_vars,
            "coverage": report["overall_summary"],
            "encoder_checkpoint_provenance_verified": False,
            "signed_latents_preserved": True,
            "adapter_differential_validation": differential,
            "upstream_inference_function_sha256": OFFICIAL_INFER_SHA256,
            "status": "experimental native prediction; SE query decoder not paired yet",
        }
        atomic_write_json(output / "manifest.json", summary)
        summaries.append(summary)
        print(f"genuine ST-SE prediction completed: {context}, {target.n_vars} genes", flush=True)
    atomic_write_json(PROOF / "se-native-signed-predictions.json", {"runs": summaries})


if __name__ == "__main__":
    main()
