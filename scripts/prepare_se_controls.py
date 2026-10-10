"""Extract genuine expression and original SE embeddings from pinned official data."""

import json
from pathlib import Path

import fsspec
import h5py
import numpy as np

from backend.app.core.run_manifest import file_sha256
from scripts.extract_replogle_k562 import (
    build_anndata,
    decode_categorical,
    decode_strings,
    open_dataset,
    open_group,
)
from scripts.prepare_context_assets import read_expression_rows, select_control_rows

ROOT = Path(__file__).resolve().parents[1]
REVISION = "d790193bb2c93726541a75ca3fa873a92ed44da5"
OUT = ROOT / "reports/metabolic-full-coverage-2026-10-09/se-controls"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    filesystem = fsspec.filesystem("hf")
    url = f"hf://datasets/arcinstitute/State-Replogle-Filtered@{REVISION}/replogle_concat.h5ad"
    with filesystem.open(url, "rb", block_size=1 << 20, cache_type="blockcache") as stream:
        with h5py.File(stream, "r") as h5:
            obs, var = open_group(h5, "obs"), open_group(h5, "var")
            lines = decode_categorical(open_group(obs, "cell_line"))
            perts = decode_categorical(open_group(obs, "gene"))
            batches = np.asarray(open_dataset(obs, "gem_group")[:])
            genes = decode_strings(open_dataset(var, str(var.attrs["_index"]))[:])
            reports = []
            for context in ("K562", "RPE1", "Jurkat", "HepG2"):
                path = OUT / f"{context.lower()}.h5ad"
                if path.exists():
                    raise ValueError(
                        f"Preserve existing experimental control; inspect before replacing: {path}"
                    )
                rows = select_control_rows(lines, perts, context, max_cells=64, seed=42)
                barcodes = np.empty(len(lines), dtype=object)
                barcodes[rows] = decode_strings(open_dataset(obs, "cell_barcode")[rows])
                expression = read_expression_rows(filesystem, url, open_dataset(h5, "X"), rows)
                latent = read_expression_rows(
                    filesystem, url, open_dataset(h5, "obsm/X_state"), rows
                ).toarray()
                hvg = read_expression_rows(filesystem, url, open_dataset(h5, "obsm/X_hvg"), rows).toarray()
                if latent.shape != (64, 2058) or not np.isfinite(latent).all():
                    raise ValueError("Invalid official SE input")
                frame = build_anndata(expression, hvg, genes, perts, lines, batches, barcodes, rows)
                frame.obs["source_row"] = rows
                frame.obsm["X_state"] = latent
                provenance = {
                    "repo": "arcinstitute/State-Replogle-Filtered",
                    "revision": REVISION,
                    "source_file": "replogle_concat.h5ad",
                    "matrix_slot": "X",
                    "expression_kind": "measured source expression unchanged",
                    "embedding_kind": "original official source obsm/X_state unchanged",
                    "encoder_checkpoint_provenance_verified": False,
                    "sampling_seed": 42,
                }
                frame.uns["celllens_input_provenance"] = provenance
                frame.write_h5ad(path, compression="gzip")
                reports.append(
                    {
                        "cell_line": context,
                        "path": str(path.relative_to(ROOT)),
                        "sha256": file_sha256(path),
                        "source_rows": rows.tolist(),
                        "provenance": provenance,
                    }
                )
                print(f"extracted measured controls and official X_state: {context}", flush=True)
    (OUT / "manifest.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
