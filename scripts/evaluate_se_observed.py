"""Compare genuine AAMP measurements; training membership is not established.

This diagnostic neither tunes the decoder nor licenses metabolic task scoring.
Only measured shared genes and batch-weighted population means are compared.
"""

import json
from pathlib import Path

import anndata as ad
import fsspec
import h5py
import numpy as np
import pandas as pd
import scipy.sparse as sp

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.gene_identity import GeneIdentityAdapter
from backend.app.services.scientific_analysis import _select_prediction_population
from scripts.extract_replogle_k562 import decode_categorical, decode_strings, open_dataset, open_group
from scripts.prepare_context_assets import read_expression_rows
from scripts.prepare_se_controls import REVISION

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "reports/metabolic-full-coverage-2026-10-09"


def matched_observed_rows(lines, perts, batches, context, control_batches, *, seed, perturbation="AAMP"):
    rng = np.random.default_rng(seed)
    selected = []
    for batch, count in zip(*np.unique(control_batches, return_counts=True), strict=True):
        eligible = np.flatnonzero((lines == context.lower()) & (perts == perturbation) & (batches == batch))
        if not len(eligible):
            raise ValueError(f"No real {perturbation} cells for {context} batch {batch}")
        selected.extend(rng.choice(eligible, size=min(int(count), len(eligible)), replace=False).tolist())
    return np.array(sorted(selected), dtype=np.int64)


def dense_values(matrix):
    if matrix is None:
        raise ValueError("Missing measured expression")
    return matrix.toarray() if sp.issparse(matrix) else np.asarray(matrix)


def weighted_observed_mean(matrix, observed_batches, control_batches):
    matrix = dense_values(matrix)
    result = np.zeros(matrix.shape[1], dtype=np.float64)
    for batch, count in zip(*np.unique(control_batches, return_counts=True), strict=True):
        selected = observed_batches == batch
        if not np.any(selected):
            raise ValueError(f"No measured cells for required batch {batch}")
        result += matrix[selected].mean(axis=0) * (count / len(control_batches))
    return result


def compare_deltas(predicted, observed):
    predicted, observed = np.asarray(predicted), np.asarray(observed)
    if (
        predicted.shape != observed.shape
        or not np.isfinite(predicted).all()
        or not np.isfinite(observed).all()
    ):
        raise ValueError("Delta comparison requires equal finite measured panels")
    error = float(np.mean((predicted - observed) ** 2))
    baseline = float(np.mean(observed**2))
    pearson = None
    if len(observed) > 1 and np.std(predicted) > 0 and np.std(observed) > 0:
        pearson = float(np.corrcoef(predicted, observed)[0, 1])
    return {
        "genes": int(len(observed)),
        "pearson": pearson,
        "rmse": float(np.sqrt(error)),
        "no_change_rmse": float(np.sqrt(baseline)),
        "mse_relative_to_no_change": error / baseline if baseline > 0 else None,
        "scope": "unpaired population mean changes in as-provided scales; not held-out validation",
    }


def main():
    output = PROOF / "se-observed-diagnostic-shared-batches"
    if output.exists():
        raise ValueError(f"Preserve existing observed diagnostic: {output}")
    output.mkdir()
    adapter = GeneIdentityAdapter.load(
        ROOT / "data/registry/gene_identity", ROOT / "data/registry/sccellfie/human"
    )
    filesystem = fsspec.filesystem("hf")
    url = f"hf://datasets/arcinstitute/State-Replogle-Filtered@{REVISION}/replogle_concat.h5ad"
    records = []
    with filesystem.open(url, "rb", block_size=1 << 20, cache_type="blockcache") as stream:
        with h5py.File(stream, "r") as h5:
            obs, var = open_group(h5, "obs"), open_group(h5, "var")
            lines = decode_categorical(open_group(obs, "cell_line"))
            perts = decode_categorical(open_group(obs, "gene"))
            batches = np.asarray(open_dataset(obs, "gem_group")[:])
            genes = decode_strings(open_dataset(var, str(var.attrs["_index"]))[:])
            for context in ("K562", "RPE1", "Jurkat", "HepG2"):
                slug = context.lower()
                control_path = PROOF / f"se-controls/{slug}.h5ad"
                control = ad.read_h5ad(control_path)
                input_controls = len(control)
                query_root = PROOF / f"se-query-signed-{slug}"
                query = ad.read_h5ad(query_root / "predicted.h5ad")
                reconstruction = ad.read_h5ad(query_root / "reconstructed_control.h5ad")
                native_path = PROOF / f"se-native-signed-{slug}/predicted.h5ad"
                native, _ = _select_prediction_population(ad.read_h5ad(native_path), "gene", "AAMP")
                available_batches = set(batches[(lines == context.lower()) & (perts == "AAMP")])
                available_batches &= set(query.obs["gem_group"]) & set(native.obs["gem_group"])
                keep = np.isin(np.asarray(control.obs["gem_group"]), list(available_batches))
                if not np.any(keep):
                    records.append(
                        {
                            "cell_line": context,
                            "status": "not_comparable",
                            "reason": "No shared measured/predicted AAMP batches",
                            "production_eligible": False,
                        }
                    )
                    continue
                reconstruction = reconstruction[keep].copy()
                control = control[keep].copy()
                source_rows = np.asarray(control.obs["source_row"], dtype=np.int64)
                rows = matched_observed_rows(lines, perts, batches, context, batches[source_rows], seed=43)
                measured = ad.AnnData(
                    read_expression_rows(filesystem, url, open_dataset(h5, "X"), rows),
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
                provenance = {
                    "repo": "arcinstitute/State-Replogle-Filtered",
                    "revision": REVISION,
                    "source_file": "replogle_concat.h5ad",
                    "source_matrix": "X",
                    "sampling_seed": 43,
                    "training_membership_verified": False,
                    "kind": "measured AAMP expression unchanged",
                }
                measured.uns["celllens_provenance"] = provenance
                measured_path = output / f"{slug}-measured.h5ad"
                measured.write_h5ad(measured_path, compression="gzip")
                measured, _ = adapter.adapt(measured)
                control, _ = adapter.adapt(control)
                native, _ = adapter.adapt(native)
                shared = [g for g in query.var_names if g in measured.var_names and g in native.var_names]
                observed_delta = weighted_observed_mean(
                    measured[:, shared].X, batches[rows], batches[source_rows]
                ) - dense_values(control[:, shared].X).mean(axis=0)
                se_delta = weighted_observed_mean(
                    query[:, shared].X, np.asarray(query.obs["gem_group"]), batches[source_rows]
                ) - dense_values(reconstruction[:, shared].X).mean(axis=0)
                native_delta = weighted_observed_mean(
                    native[:, shared].X, np.asarray(native.obs["gem_group"]), batches[source_rows]
                ) - dense_values(control[:, shared].X).mean(axis=0)
                pd.DataFrame(
                    {
                        "gene": shared,
                        "observed_delta": observed_delta,
                        "se_query_delta": se_delta,
                        "native_head_delta": native_delta,
                    }
                ).to_csv(output / f"{slug}-deltas.csv", index=False)
                record = {
                    "cell_line": context,
                    "perturbation": "AAMP",
                    "cells": len(rows),
                    "control_cells_in_shared_batches": len(control),
                    "excluded_control_cells_without_shared_batch": input_controls - len(control),
                    "batch_distribution_weighted": True,
                    "batch_weights": {
                        str(batch): float(count / len(source_rows))
                        for batch, count in zip(
                            *np.unique(batches[source_rows], return_counts=True), strict=True
                        )
                    },
                    "source_rows": rows.tolist(),
                    "source_control_sha256": file_sha256(control_path),
                    "measured_sha256": file_sha256(measured_path),
                    "query_prediction_sha256": file_sha256(query_root / "predicted.h5ad"),
                    "query_control_sha256": file_sha256(query_root / "reconstructed_control.h5ad"),
                    "native_prediction_sha256": file_sha256(native_path),
                    "provenance": provenance,
                    "se_query": compare_deltas(se_delta, observed_delta),
                    "native_head": compare_deltas(native_delta, observed_delta),
                    "production_eligible": False,
                    "held_out_validation": False,
                    "limitations": [
                        "checkpoint training membership not established",
                        "decoder read-depth and scale not calibrated",
                        "405 metabolic genes absent from measured feature panel",
                        "single perturbation with unpaired sampled populations",
                        "comparison restricted to batches with measured AAMP and model predictions",
                    ],
                }
                records.append(record)
                print(
                    json.dumps(
                        {
                            "context": context,
                            "se_query": record["se_query"],
                            "native_head": record["native_head"],
                        }
                    ),
                    flush=True,
                )
    atomic_write_json(output / "manifest.json", {"diagnostics": records, "production_eligible": False})


if __name__ == "__main__":
    main()
