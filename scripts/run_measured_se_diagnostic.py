"""A shared measured perturbation diagnostic with genuine four-background outputs.

Selection is frozen before inference. No measured perturbed expression tunes the
decoder condition. Training membership remains unknown, so this is not a held-out
benchmark and cannot activate the production model registry.
"""

import argparse
import json
from pathlib import Path
from typing import cast

import anndata as ad
import fsspec
import h5py
import numpy as np
import pandas as pd

from backend.app.core.registry import RegistryEntry
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.engines.se_decode_engine import (
    SEGeneDecoder,
    metabolic_query_keys,
    positive_log_expression_mean,
)
from backend.app.engines.state_engine import StateCliEngine, StateRunInput
from backend.app.services.completeness import compute_official_completeness
from backend.app.services.gene_identity import GeneIdentityAdapter
from backend.app.services.scientific_analysis import _load_frozen_database, _select_prediction_population
from scripts.evaluate_se_observed import (
    compare_deltas,
    dense_values,
    matched_observed_rows,
    weighted_observed_mean,
)
from scripts.extract_replogle_k562 import decode_categorical, decode_strings, open_dataset, open_group
from scripts.prepare_context_assets import read_expression_rows
from scripts.prepare_se_controls import REVISION

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "reports/metabolic-full-coverage-2026-10-09"
CONTEXTS = ("K562", "RPE1", "Jurkat", "HepG2")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--perturbation", default="ALDOA")
    args = parser.parse_args()
    gene = args.perturbation
    inventory_path = PROOF / "validation-candidate-inventory.json"
    inventory = json.loads(inventory_path.read_text())
    if gene not in inventory["common_eligible_perturbations"]:
        raise ValueError("Select a frozen perturbation with measured support in all four backgrounds")
    output = PROOF / f"se-measured-{gene.lower()}"
    if output.exists():
        raise ValueError(f"Preserve genuine measured diagnostic: {output}")
    output.mkdir()
    database_root = ROOT / "data/registry/sccellfie/human"
    adapter = GeneIdentityAdapter.load(ROOT / "data/registry/gene_identity", database_root)
    database, version = _load_frozen_database(database_root)
    engine = StateCliEngine(device="cuda")
    # Separate GPU stages so ST subprocesses never overlap the SE decoder.
    for context in CONTEXTS:
        slug = context.lower()
        root = output / slug
        root.mkdir()
        model_dir = ROOT / f"models/st-se-full-{slug}"
        source = json.loads((model_dir / "source_manifest.json").read_text())
        for filename, digest in source["files"].items():
            if file_sha256(model_dir / filename) != digest:
                raise ValueError(f"Official ST-SE asset changed: {context}/{filename}")
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
        native_path = root / "native/predicted.h5ad"
        native_path.parent.mkdir()
        engine.infer(
            StateRunInput(context, gene, PROOF / f"se-controls/{slug}.h5ad", 64, 42), model, native_path
        )
        target, population = _select_prediction_population(ad.read_h5ad(native_path), "gene", gene)
        latent = np.asarray(target.obsm["X_state"])
        if latent.shape != (64, 2058) or not np.isfinite(latent).all() or not np.any(latent < 0):
            raise ValueError("Invalid signed native SE prediction")
        atomic_write_json(
            root / "native/manifest.json",
            {
                "cell_line": context,
                "perturbation": gene,
                "model_source": source,
                "population": population,
                "prediction_sha256": file_sha256(native_path),
                "production_eligible": False,
            },
        )
        print(f"genuine {context}/{gene} native prediction completed", flush=True)
    decoder = SEGeneDecoder(ROOT / "models/se600m-epoch16", device="cuda")
    symbols, keys = metabolic_query_keys(adapter, set(decoder.protein))
    panel = cast(pd.DataFrame, ad.read_h5ad(PROOF / "se-query-signed-k562/predicted.h5ad").var).copy()
    if panel.index.tolist() != symbols:
        raise ValueError("Frozen query identities differ from registered decoder keys")
    filesystem = fsspec.filesystem("hf")
    source_url = f"hf://datasets/arcinstitute/State-Replogle-Filtered@{REVISION}/replogle_concat.h5ad"
    records = []
    with filesystem.open(source_url, "rb", block_size=1 << 20, cache_type="blockcache") as stream:
        with h5py.File(stream, "r") as h5:
            obs, var = open_group(h5, "obs"), open_group(h5, "var")
            lines = decode_categorical(open_group(obs, "cell_line"))
            perts = decode_categorical(open_group(obs, "gene"))
            batches = np.asarray(open_dataset(obs, "gem_group")[:])
            genes = decode_strings(open_dataset(var, str(var.attrs["_index"]))[:])
            for context in CONTEXTS:
                slug, root = context.lower(), output / context.lower()
                control_path = PROOF / f"se-controls/{slug}.h5ad"
                control = ad.read_h5ad(control_path)
                native_path = root / "native/predicted.h5ad"
                native, population = _select_prediction_population(ad.read_h5ad(native_path), "gene", gene)
                control_depths = positive_log_expression_mean(dense_values(control.X))
                source_depths = dict(zip(control.obs["source_row"], control_depths, strict=True))
                if not set(native.obs["source_row"]) <= source_depths.keys():
                    raise ValueError("Native prediction source controls cannot be traced")
                prediction_depths = np.asarray([source_depths[row] for row in native.obs["source_row"]])
                raw = {}
                for name, frame, depths in (
                    ("reconstructed_control", control, control_depths),
                    ("predicted", native, prediction_depths),
                ):
                    raw[name] = decoder.decode(np.asarray(frame.obsm["X_state"]), keys, read_depth=depths)
                    result_obs = cast(pd.DataFrame, frame.obs).copy()
                    result_obs["se_mu_condition"] = depths
                    result = ad.AnnData(raw[name], obs=result_obs, var=panel.copy())
                    result.obsm["X_state"] = np.asarray(frame.obsm["X_state"]).copy()
                    result.uns["celllens_provenance"] = {
                        "kind": name,
                        "perturbation": gene,
                        "expression_scale": "unmodified SE regression output",
                        "condition": "mean nonzero measured source-control expression",
                        "condition_is_estimated": True,
                        "training_exclusion_verified": False,
                        "encoder_pairing_verified": False,
                        "source_sha256": file_sha256(
                            control_path if name == "reconstructed_control" else native_path
                        ),
                    }
                    result.write_h5ad(root / f"{name}.h5ad", compression="gzip")
                available_batches = set(batches[(lines == context.lower()) & (perts == gene)])
                available_batches &= set(native.obs["gem_group"])
                keep = np.isin(np.asarray(control.obs["gem_group"]), list(available_batches))
                if int(keep.sum()) < 32:
                    raise ValueError("Model resampling left too few comparable measured control batches")
                control_batches = np.asarray(control.obs["gem_group"])[keep]
                rows = matched_observed_rows(
                    lines, perts, batches, context, control_batches, seed=43, perturbation=gene
                )
                measured = ad.AnnData(
                    read_expression_rows(filesystem, source_url, open_dataset(h5, "X"), rows),
                    obs=pd.DataFrame(
                        {
                            "gene": perts[rows],
                            "cell_line": lines[rows],
                            "gem_group": batches[rows],
                            "source_row": rows,
                        },
                        index=decode_strings(open_dataset(obs, "cell_barcode")[rows]),
                    ),
                    var=pd.DataFrame(index=genes),
                )
                measured.uns["celllens_provenance"] = {
                    "repo": "arcinstitute/State-Replogle-Filtered",
                    "revision": REVISION,
                    "kind": "measured expression unchanged",
                    "sampling_seed": 43,
                    "training_exclusion_verified": False,
                }
                measured_path = root / "measured.h5ad"
                measured.write_h5ad(measured_path, compression="gzip")
                measured, _ = adapter.adapt(measured)
                control, _ = adapter.adapt(control)
                native, _ = adapter.adapt(native)
                shared = [g for g in symbols if g in control.var_names and g in measured.var_names]
                columns = [symbols.index(g) for g in shared]
                observed_delta = weighted_observed_mean(measured[:, shared].X, batches[rows], control_batches)
                observed_delta -= dense_values(control[keep, shared].X).mean(0)
                query_delta = weighted_observed_mean(
                    raw["predicted"][:, columns], np.asarray(native.obs["gem_group"]), control_batches
                )
                query_delta -= raw["reconstructed_control"][keep][:, columns].mean(0)
                native_delta = weighted_observed_mean(
                    native[:, shared].X, np.asarray(native.obs["gem_group"]), control_batches
                ) - dense_values(control[keep, shared].X).mean(0)
                pd.DataFrame(
                    {
                        "gene": shared,
                        "observed_delta": observed_delta,
                        "se_query_delta": query_delta,
                        "native_head_delta": native_delta,
                    }
                ).to_csv(root / "observed_deltas.csv", index=False)
                pd.DataFrame(
                    {
                        "gene": symbols,
                        "reconstructed_control": raw["reconstructed_control"].mean(0),
                        "predicted": raw["predicted"].mean(0),
                    }
                ).assign(
                    predicted_delta=lambda frame: frame["predicted"] - frame["reconstructed_control"]
                ).to_csv(root / "raw_gene_deltas.csv", index=False)
                completeness = compute_official_completeness(symbols, database, version)
                completeness["source_prediction_sha256"] = file_sha256(root / "predicted.h5ad")
                atomic_write_json(root / "official_completeness.json", completeness)
                record = {
                    "cell_line": context,
                    "perturbation": gene,
                    "population": population,
                    "source_data_revision": REVISION,
                    "selection_inventory_sha256": file_sha256(inventory_path),
                    "source_control_sha256": file_sha256(control_path),
                    "native_prediction_sha256": file_sha256(native_path),
                    "measured_sha256": file_sha256(measured_path),
                    "measured_source_rows": rows.tolist(),
                    "measured_cells": len(measured),
                    "control_cells_in_shared_batches": int(keep.sum()),
                    "decoder": decoder.provenance,
                    "query_keys": dict(zip(symbols, keys, strict=True)),
                    "se_query_diagnostic": compare_deltas(query_delta, observed_delta),
                    "native_head_diagnostic": compare_deltas(native_delta, observed_delta),
                    "coverage": completeness["overall_summary"],
                    "raw_outputs": {
                        name: {
                            "sha256": file_sha256(root / f"{name}.h5ad"),
                            "negative_fraction": float(np.mean(values < 0)),
                            "minimum": float(values.min()),
                            "maximum": float(values.max()),
                        }
                        for name, values in raw.items()
                    },
                    "observed_support_in_all_four_backgrounds": True,
                    "held_out_validation": False,
                    "production_eligible": False,
                    "metabolic_scores_generated": False,
                    "limitations": [
                        "training membership and exact encoder pairing unverified",
                        "SE condition estimated from measured source-control features",
                        "unpaired batch-weighted population mean comparison",
                        "405 metabolic genes lack measurements; raw regression values can be negative",
                    ],
                }
                atomic_write_json(root / "manifest.json", record)
                records.append(record)
                print(
                    json.dumps(
                        {
                            "context": context,
                            "perturbation": gene,
                            "observed_cells": len(measured),
                            "se_query": record["se_query_diagnostic"],
                            "native": record["native_head_diagnostic"],
                        }
                    ),
                    flush=True,
                )
    atomic_write_json(output / "manifest.json", {"experiments": records, "production_eligible": False})


if __name__ == "__main__":
    main()
