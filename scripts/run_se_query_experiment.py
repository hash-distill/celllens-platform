"""Produce faithful 931-gene SE queries; retain compatibility/scaling uncertainty."""

import json
from pathlib import Path
from typing import cast

import anndata as ad
import numpy as np
import pandas as pd

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.engines.se_decode_engine import SEGeneDecoder, metabolic_query_keys
from backend.app.services.completeness import compute_official_completeness
from backend.app.services.gene_identity import GeneIdentityAdapter
from backend.app.services.scientific_analysis import _load_frozen_database, _select_prediction_population

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "reports/metabolic-full-coverage-2026-10-09"


def main():
    if not (PROOF / "se-native-signed-predictions.json").is_file():
        raise SystemExit("Complete all native predictions first; do not overlap GPU inference")
    database_root = ROOT / "data/registry/sccellfie/human"
    adapter = GeneIdentityAdapter.load(ROOT / "data/registry/gene_identity", database_root)
    database, version = _load_frozen_database(database_root)
    decoder = SEGeneDecoder(ROOT / "models/se600m-epoch16", device="cuda")
    symbols, keys = metabolic_query_keys(adapter, set(decoder.protein))
    if len(symbols) != 931:
        raise ValueError("Metabolic query panel differs from frozen 931-gene database")
    records = []
    for context in ("K562", "RPE1", "Jurkat", "HepG2"):
        slug = context.lower()
        output = PROOF / f"se-query-signed-{slug}"
        if output.exists():
            raise ValueError(f"Preserve existing SE query experiment: {output}")
        output.mkdir()
        control_path = PROOF / f"se-controls/{slug}.h5ad"
        prediction_path = PROOF / f"se-native-signed-{slug}/predicted.h5ad"
        control = ad.read_h5ad(control_path)
        predicted, population = _select_prediction_population(ad.read_h5ad(prediction_path), "gene", "AAMP")
        raw = {}
        # Freeze the public inference default for both sources. This setting is
        # part of the experiment, and requires calibration before task scoring.
        for name, source in (("reconstructed_control", control), ("predicted", predicted)):
            raw[name] = decoder.decode(np.asarray(source.obsm["X_state"]), keys, read_depth=4.0)
            var = pd.DataFrame(
                {
                    "hgnc_id": [adapter.document["database_genes"][s]["hgnc_id"] for s in symbols],
                    "approved_symbol": [
                        adapter.document["database_genes"][s]["approved_symbol"] for s in symbols
                    ],
                    "se_embedding_key": keys,
                },
                index=pd.Index(symbols),
            )
            frame = ad.AnnData(raw[name], obs=cast(pd.DataFrame, source.obs).copy(), var=var)
            frame.obsm["X_state"] = np.asarray(source.obsm["X_state"]).copy()
            frame.uns["celllens_provenance"] = {
                "kind": name,
                "expression_slot": "X",
                "expression_scale": "unmodified SE decoder output",
                "encoder_pairing_verified": False,
                "read_depth": 4.0,
                "source_file_sha256": file_sha256(
                    control_path if name == "reconstructed_control" else prediction_path
                ),
            }
            frame.write_h5ad(output / f"{name}.h5ad", compression="gzip")
        adapted_control, _ = adapter.adapt(control)
        shared = [gene for gene in symbols if gene in adapted_control.var_names]
        measured = np.asarray(adapted_control[:, shared].X.toarray())
        reconstructed = raw["reconstructed_control"][:, [symbols.index(g) for g in shared]]
        correlation = float(np.corrcoef(measured.mean(axis=0), reconstructed.mean(axis=0))[0, 1])
        differences = pd.DataFrame(
            {
                "reconstructed_control": raw["reconstructed_control"].mean(axis=0),
                "predicted": raw["predicted"].mean(axis=0),
            },
            index=pd.Index(symbols),
        )
        differences["predicted_delta"] = differences["predicted"] - differences["reconstructed_control"]
        differences.index.name = "gene"
        differences.to_csv(output / "raw_gene_deltas.csv")
        completeness = compute_official_completeness(symbols, database, version)
        completeness.update(
            analysis_kind="gene availability in genuine experimental SE queries",
            source_prediction_sha256=file_sha256(output / "predicted.h5ad"),
        )
        atomic_write_json(output / "official_completeness.json", completeness)
        record = {
            "cell_line": context,
            "perturbation": "AAMP",
            "population": population,
            "output_genes": len(symbols),
            "read_depth": 4.0,
            "decoder": decoder.provenance,
            "gene_identity": adapter.provenance,
            "query_keys": dict(zip(symbols, keys, strict=True)),
            "source_control_sha256": file_sha256(control_path),
            "source_st_prediction_sha256": file_sha256(prediction_path),
            "raw_outputs": {
                name: {
                    "sha256": file_sha256(output / f"{name}.h5ad"),
                    "minimum": float(value.min()),
                    "maximum": float(value.max()),
                    "negative_fraction": float(np.mean(value < 0)),
                }
                for name, value in raw.items()
            },
            "reconstruction_diagnostic": {
                "measured_genes": len(shared),
                "mean_gene_pearson": correlation,
                "rmse_in_source_values": float(np.sqrt(np.mean((measured - reconstructed) ** 2))),
                "scope": "as-provided source values; not held-out perturbation validation",
            },
            "coverage": completeness["overall_summary"],
            "production_eligible": False,
            "unresolved": [
                "ST-SE training encoder checkpoint not recorded in official source",
                "read-depth and expression-scale calibration pending",
                "held-out perturbation evaluation pending",
            ],
            "metabolic_scores_generated": False,
        }
        atomic_write_json(output / "manifest.json", record)
        records.append(record)
        print(
            json.dumps(
                {
                    "context": context,
                    "genes": len(symbols),
                    "pearson": correlation,
                    "prediction_negative_fraction": record["raw_outputs"]["predicted"]["negative_fraction"],
                    "production_eligible": False,
                }
            ),
            flush=True,
        )
    atomic_write_json(PROOF / "se-query-signed-experiment.json", {"experiments": records})


if __name__ == "__main__":
    main()
