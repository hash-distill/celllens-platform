"""Extract real observations from a pinned atlas and prepare immutable CPU comparisons."""

import argparse
import json
from pathlib import Path
from typing import Any

import anndata as ad
import fsspec
import h5py
import numpy as np
import pandas as pd

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.measured_comparison import prepare_comparison
from scripts.extract_replogle_k562 import decode_categorical, decode_strings, open_dataset, open_group
from scripts.prepare_context_assets import DATA_REPO, DATA_REVISION, read_expression_rows

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/registry/observations.json"
SOURCE = {
    "kind": "measured_rna",
    "repo": DATA_REPO,
    "revision": DATA_REVISION,
    "file": "replogle_concat.h5ad",
    "url": f"https://huggingface.co/datasets/{DATA_REPO}/tree/{DATA_REVISION}",
}


def candidates() -> list[dict[str, Any]]:
    rows = []
    for path in sorted((ROOT / "data/derived/runs").glob("*/manifest.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        contract = path.parent / "expression_contract.json"
        if (
            manifest["request"]["mode"] in {"online", "validation"}
            and contract.is_file()
            and json.loads(contract.read_text())["analysis_version"] == "expression-cp10k-v2"
        ):
            rows.append({"run_id": path.parent.name, **manifest["request"]})
    return rows


def extract() -> None:
    if CATALOG.exists():
        raise ValueError("Existing observation catalog is immutable; use a new version for new selection")
    targets = sorted({(r["cell_line"], r["perturbation"]) for r in candidates()})
    selection = {
        "selection": "existing genuine expression-cp10k-v2 model runs, before comparison scoring",
        "seed": 42,
        "max_measured_cells_per_pair": 256,
        "targets": targets,
        "source": SOURCE,
    }
    proof = ROOT / "reports/measured-comparison-2026-10-15"
    proof.mkdir(parents=True, exist_ok=True)
    atomic_write_json(proof / "selection.json", selection)
    fs = fsspec.filesystem("hf")
    url = f"hf://datasets/{DATA_REPO}@{DATA_REVISION}/replogle_concat.h5ad"
    catalog = []
    with (
        fs.open(url, "rb", block_size=1 << 20, cache_type="blockcache") as stream,
        h5py.File(stream, "r") as h5,
    ):
        obs, var = open_group(h5, "obs"), open_group(h5, "var")
        contexts = decode_categorical(open_group(obs, "cell_line"))
        perturbations = decode_categorical(open_group(obs, "gene"))
        batches = np.asarray(open_dataset(obs, "gem_group")[:])
        names = decode_strings(open_dataset(var, str(var.attrs["_index"]))[:])
        index = open_dataset(obs, str(obs.attrs["_index"]))
        matrix = open_dataset(h5, "X")
        for context, target in targets:
            available = np.flatnonzero((contexts == context.lower()) & (perturbations == target))
            entry = {
                "cell_line": context,
                "perturbation": target,
                "source": SOURCE,
                "available_cells_in_source": int(len(available)),
            }
            print(f"measured source {context}/{target}: {len(available)} cells", flush=True)
            if not len(available):
                catalog.append(
                    {
                        **entry,
                        "status": "unavailable",
                        "n_cells": 0,
                        "reason": "No matching measured cells in this pinned filtered atlas",
                    }
                )
                continue
            rows = np.sort(
                np.random.default_rng(42).choice(available, size=min(256, len(available)), replace=False)
            )
            output = ROOT / "data/raw/measured-comparison-v1" / context.lower() / f"{target}.h5ad"
            if output.exists():
                measured = ad.read_h5ad(output)
                if not np.array_equal(measured.obs["source_row"].to_numpy(), rows):
                    raise ValueError(f"Existing extraction has different source rows: {output}")
            else:
                measured = ad.AnnData(
                    read_expression_rows(fs, url, matrix, rows),
                    obs=pd.DataFrame(
                        {
                            "gene": target,
                            "cell_line": context.lower(),
                            "gem_group": batches[rows],
                            "source_row": rows,
                            "cell_barcode": decode_strings(index[rows]),
                        },
                        index=pd.Index([f"source_{i}" for i in rows]),
                    ),
                    var=pd.DataFrame(index=pd.Index(names)),
                )
                measured.uns["celllens_provenance"] = {
                    **SOURCE,
                    "expression_scale": "log1p_cp10k",
                    "sampling_seed": 42,
                    "selection": "fixed random source rows without replacement",
                    "observations_generated": False,
                    "training_exclusion_verified": False,
                }
                output.parent.mkdir(parents=True, exist_ok=True)
                measured.write_h5ad(output, compression="gzip")
            matrix_values: Any = measured.X
            values = np.asarray(matrix_values.data if hasattr(matrix_values, "toarray") else matrix_values)
            if not np.isfinite(values).all() or np.any(values < 0):
                raise ValueError("Measured source expression is invalid")
            catalog.append(
                {
                    **entry,
                    "status": "available",
                    "n_cells": int(measured.n_obs),
                    "path": output.relative_to(ROOT).as_posix(),
                    "sha256": file_sha256(output),
                    "expression_scale": "log1p_cp10k",
                    "sampling_seed": 42,
                }
            )
            print(f"saved {context}/{target}: {measured.n_obs} genuine observations", flush=True)
    atomic_write_json(CATALOG, {"schema_version": 1, "selection": selection, "observations": catalog})


def evaluate(run_ids: list[str] | None) -> None:
    results = []
    for row in candidates():
        if run_ids and row["run_id"] not in run_ids:
            continue
        try:
            doc = prepare_comparison(ROOT, row["run_id"])
            results.append({**row, "comparison": bool(doc), "expression": doc["expression"] if doc else None})
            print(
                f"comparison {row['run_id']} {row['cell_line']}/{row['perturbation']}: {bool(doc)}",
                flush=True,
            )
        except Exception as exc:
            results.append({**row, "error": str(exc)})
            print(f"comparison failed {row['run_id']}: {exc}", flush=True)
    atomic_write_json(ROOT / "reports/measured-comparison-2026-10-15/evaluation.json", {"items": results})
    if any("error" in row for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["extract", "evaluate"])
    parser.add_argument("--run-id", action="append")
    args = parser.parse_args()
    extract() if args.phase == "extract" else evaluate(args.run_id)
