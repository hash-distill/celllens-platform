"""Attach the registered STATE HVG matrix to existing Replogle H5AD assets."""

from __future__ import annotations

import argparse
from pathlib import Path

import anndata as ad
import scipy.sparse as sp

from scripts.extract_replogle_k562 import HVG_REGISTRY, PROJECT_ROOT, select_registered_hvg

DEFAULT_INPUTS = (
    PROJECT_ROOT / "data" / "raw" / "replogle-k562" / "control.h5ad",
    PROJECT_ROOT / "data" / "raw" / "replogle-k562" / "heldout.h5ad",
)


def attach_hvg(path: Path, registered_genes: list[str]) -> None:
    frame = ad.read_h5ad(path)
    matrix = sp.csr_matrix(frame.X)
    frame.obsm["X_hvg"] = select_registered_hvg(matrix, frame.var_names.to_numpy(), registered_genes)

    temporary = path.with_name(f"{path.stem}.tmp.h5ad")
    try:
        frame.write_h5ad(temporary, compression="gzip")
        verified = ad.read_h5ad(temporary, backed="r")
        try:
            shape = verified.obsm["X_hvg"].shape
            expected = (frame.n_obs, len(registered_genes))
            if shape != expected:
                raise ValueError(f"X_hvg shape mismatch after write: {shape} != {expected}")
        finally:
            verified.file.close()
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path, default=list(DEFAULT_INPUTS))
    args = parser.parse_args()
    registered_genes = [
        line.strip() for line in HVG_REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    for path in args.paths:
        resolved = path if path.is_absolute() else PROJECT_ROOT / path
        attach_hvg(resolved, registered_genes)
        print(f"updated {resolved.relative_to(PROJECT_ROOT)} with X_hvg ({len(registered_genes)} genes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
