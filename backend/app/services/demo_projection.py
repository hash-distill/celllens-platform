"""Generate explicit synthetic single-cell inputs for demonstration projections."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.app.core.projection import validate_projection
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.scientific_analysis import _projection_document


def write_demo_projection(
    root: Path,
    *,
    seed: int = 20260920,
    cells_per_source: int = 512,
    original_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Sample reproducible expression heterogeneity; never invent XY coordinates directly."""
    table = pd.read_csv(root / "gene_deltas.csv")
    if table.empty or table["gene"].duplicated().any():
        raise ValueError("Demo requires a unique nonempty gene panel")
    means = table[["control", "predicted"]].apply(pd.to_numeric, errors="raise").to_numpy()
    if not np.isfinite(means).all() or np.any(means < 0) or cells_per_source < 2:
        raise ValueError("Demo requires finite nonnegative expression and at least two cells")
    rng = np.random.default_rng(seed)
    arrays = {}
    for source, mean in zip(("control", "predicted"), means.T, strict=True):
        noise = rng.normal(0, 0.2, size=(cells_per_source, len(table)))
        noise -= noise.mean(axis=0, keepdims=True)
        arrays[source] = np.expm1(np.maximum(mean + noise, 0)).astype(np.float32)
    path = root / "demo_cells.npz"
    temporary = path.with_suffix(".npz.tmp")
    with temporary.open("wb") as handle:
        np.savez_compressed(handle, genes=table["gene"].astype(str).to_numpy(dtype=str), **arrays)
    temporary.replace(path)
    document = _projection_document(list(arrays.items()), seed=seed, max_points=12000)
    document.update(
        {
            "data_kind": "synthetic_demo",
            "generator": "synthetic-single-cell-v1",
            "input_artifact": path.name,
            "input_sha256": file_sha256(path),
            "gene_deltas_sha256": file_sha256(root / "gene_deltas.csv"),
            "source_counts": {source: len(matrix) for source, matrix in arrays.items()},
            "generation": "Zero-centered noise on saved demo log-expression means; expm1 to counts",
            "warnings": [
                "Synthetic single-cell samples, not STATE predictions or experimental observations."
            ],
            "original_manifest_sha256": original_manifest_sha256,
        }
    )
    atomic_write_json(root / "projection.json", document)
    validate_projection(root / "projection.json")
    return document
