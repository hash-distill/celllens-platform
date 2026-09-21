"""Extract K562 control and held-out perturbed subsets from the remote Replogle atlas.

The source is a single 30 GB `replogle_concat.h5ad` on Hugging Face. HDF5 supports
partial reads, so this script never downloads the whole file: it range-reads only the
obs columns it needs, then slices the requested row blocks out of /X.

Outputs (all under the paths the asset registry expects):

    data/raw/replogle-k562/control.h5ad    non-targeting K562 cells
    data/raw/replogle-k562/heldout.h5ad    held-out perturbed K562 cells
    configs/splits/replogle-v1.json        frozen split with real perturbation groups

Usage:
    uv run python scripts/extract_replogle_k562.py --dry-run
    uv run python scripts/extract_replogle_k562.py
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import anndata as ad
import fsspec  # type: ignore[import-untyped]
import h5py
import numpy as np
import pandas as pd
import scipy.sparse as sp

PROJECT_ROOT = Path(__file__).resolve().parents[1]
URL = "hf://datasets/arcinstitute/State-Replogle-Filtered/replogle_concat.h5ad"
CONTROL_OUT = PROJECT_ROOT / "data" / "raw" / "replogle-k562" / "control.h5ad"
HELDOUT_OUT = PROJECT_ROOT / "data" / "raw" / "replogle-k562" / "heldout.h5ad"
SPLIT_OUT = PROJECT_ROOT / "configs" / "splits" / "replogle-v1.json"
HVG_REGISTRY = PROJECT_ROOT / "data" / "registry" / "state_k562_genes.txt"
TOML_CANDIDATES = (
    PROJECT_ROOT.parent / "调研与方案" / "STATE_调研证据_2026-09-19" / "replogle_k562_split.toml",
    PROJECT_ROOT.parent / ".replogle-src" / "k562.toml",
)

CELL_LINE = "k562"
CONTROL_LABEL = "non-targeting"
MAX_CONTROL_CELLS = 3000
MAX_HELDOUT_CELLS = 3000
MAX_HELDOUT_PERTURBATIONS = 12
ROW_BLOCK = 20_000


# h5py's public type stubs are incomplete, so the openers below narrow the runtime
# types once and the rest of the module works with plain typed handles.
def open_dataset(parent: Any, name: str) -> h5py.Dataset:
    item = parent[name]
    if not isinstance(item, h5py.Dataset):
        raise TypeError(f"{name} is not an HDF5 dataset")
    return item


def open_group(parent: Any, name: str) -> h5py.Group:
    item = parent[name]
    if not isinstance(item, h5py.Group):
        raise TypeError(f"{name} is not an HDF5 group")
    return item


def decode_strings(values: Any) -> np.ndarray:
    return np.array(
        [value.decode() if isinstance(value, bytes) else str(value) for value in values], dtype=object
    )


def decode_categorical(group: h5py.Group, indices: np.ndarray | None = None) -> np.ndarray:
    categories = decode_strings(open_dataset(group, "categories")[:])
    codes_dataset = open_dataset(group, "codes")
    codes = np.asarray(codes_dataset[:] if indices is None else codes_dataset[indices])
    if categories.size == 0:
        return np.array([""] * codes.size, dtype=object)
    return np.where(codes >= 0, categories[np.clip(codes, 0, categories.size - 1)], "")


def read_rows(dataset: h5py.Dataset, rows: np.ndarray) -> np.ndarray:
    """Read a row subset in blocks to bound peak memory."""
    rows = np.sort(rows)
    blocks = [dataset[rows[start : start + ROW_BLOCK], :] for start in range(0, len(rows), ROW_BLOCK)]
    return np.vstack(blocks)


def load_to_sparse(dataset: h5py.Dataset, rows: np.ndarray) -> sp.csr_matrix:
    return sp.csr_matrix(read_rows(dataset, rows))


def select_registered_hvg(
    matrix: sp.csr_matrix,
    var_names: np.ndarray,
    registered_genes: list[str],
) -> np.ndarray:
    """Select STATE's registered HVGs from a full expression matrix in registry order."""
    canonical_names = [str(name).strip().upper() for name in var_names]
    if len(canonical_names) != len(set(canonical_names)):
        raise ValueError("duplicate gene symbols prevent unambiguous registered HVG selection")
    column_by_gene = {name: index for index, name in enumerate(canonical_names)}
    canonical_registered = [gene.strip().upper() for gene in registered_genes if gene.strip()]
    missing = [gene for gene in canonical_registered if gene not in column_by_gene]
    if missing:
        preview = ", ".join(missing[:10])
        raise ValueError(f"missing registered HVG genes: {preview}")
    columns = [column_by_gene[gene] for gene in canonical_registered]
    selected = matrix[:, columns]
    if sp.issparse(selected):
        selected = selected.toarray()
    return np.asarray(selected, dtype=np.float32)


def build_anndata(
    matrix: sp.csr_matrix,
    hvg_matrix: np.ndarray,
    var_names: np.ndarray,
    perturbations: np.ndarray,
    cell_lines: np.ndarray,
    gem_group: np.ndarray,
    barcodes: np.ndarray,
    rows: np.ndarray,
) -> ad.AnnData:
    obs = pd.DataFrame(
        {
            "gene": pd.Categorical(perturbations[rows]),
            "cell_line": pd.Categorical(cell_lines[rows]),
            "gem_group": np.asarray(gem_group[rows], dtype=np.int64),
            "cell_barcode": barcodes[rows],
        },
        index=pd.Index([f"cell_{index}" for index in range(len(rows))]),
    )
    var = pd.DataFrame(index=pd.Index([str(name) for name in var_names]))
    frame = ad.AnnData(X=matrix, obs=obs, var=var)
    frame.obsm["X_hvg"] = np.asarray(hvg_matrix, dtype=np.float32)
    return frame


def read_test_perturbations() -> set[str]:
    """Read the frozen test list from the local k562.toml companion file."""
    for candidate in TOML_CANDIDATES:
        if not candidate.is_file():
            continue
        text = candidate.read_text(encoding="utf-8")
        start = text.find("test = [")
        if start < 0:
            continue
        end = text.find("]", start)
        raw = text[start + len("test = [") : end]
        resolved = {item.strip().strip("'\"") for item in raw.split(",") if item.strip()}
        print(f"loaded {len(resolved)} test perturbations from {candidate.name}")
        return resolved
    print("WARNING: k562.toml not found; treating all observed perturbations as held out")
    return set()


def write_split(chosen: list[str], test_perts: set[str]) -> None:
    document = {
        "version": "replogle-v1",
        "status": "frozen",
        "source": "arcinstitute/State-Replogle-Filtered :: replogle_concat.h5ad",
        "split_unit": "perturbation",
        "cell_line": "K562",
        "development_groups": [],
        "calibration_groups": [],
        "test_groups": sorted(chosen),
        "frozen_test_group_count": len(test_perts),
        "decision_rule": (
            "Test groups are the K562 fewshot test perturbations declared in the upstream "
            "k562.toml. Calibration groups stay empty until a development split is chosen; "
            "the full test list must not be evaluated until then."
        ),
    }
    SPLIT_OUT.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {SPLIT_OUT.relative_to(PROJECT_ROOT)} with {len(chosen)} test groups")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report selection sizes only")
    parser.add_argument("--max-control", type=int, default=MAX_CONTROL_CELLS)
    parser.add_argument("--max-heldout", type=int, default=MAX_HELDOUT_CELLS)
    args = parser.parse_args()

    filesystem = fsspec.filesystem("hf")
    print(f"opening {URL} (remote, range reads only)")
    started = time.time()
    with filesystem.open(URL, "rb") as handle, h5py.File(handle, mode="r") as h5:
        obs = open_group(h5, "obs")
        var = open_group(h5, "var")
        barcodes = decode_strings(open_dataset(obs, "cell_barcode")[:])
        n_obs = barcodes.size
        var_names = decode_strings(open_dataset(var, "gene_name_index")[:])
        print(f"total cells={n_obs:,} genes={var_names.size:,}")

        cell_lines = decode_categorical(open_group(obs, "cell_line"))
        perturbations = decode_categorical(open_group(obs, "gene"))
        gem_group = np.asarray(open_dataset(obs, "gem_group")[:])

        is_k562 = cell_lines == CELL_LINE
        is_control = perturbations == CONTROL_LABEL
        print(f"K562 cells: {int(is_k562.sum()):,}  (of {n_obs:,})")
        print(f"non-targeting cells: {int(is_control.sum()):,}")

        control_idx = np.flatnonzero(is_k562 & is_control)
        k562_perturbed = np.flatnonzero(is_k562 & ~is_control)
        print(f"K562 control: {len(control_idx):,}   K562 perturbed: {len(k562_perturbed):,}")
        if len(control_idx) == 0:
            raise SystemExit("No K562 non-targeting control cells found")

        test_perts = read_test_perturbations()
        present = set(perturbations[k562_perturbed].tolist())
        available = sorted(test_perts & present)
        print(f"frozen test perturbations: {len(test_perts)}; present in K562 data: {len(available)}")
        if not available:
            raise SystemExit("No frozen test perturbations are present in the K562 data")
        chosen = available[:MAX_HELDOUT_PERTURBATIONS]
        print(f"selected held-out perturbations ({len(chosen)}): {chosen}")

        heldout_idx = np.flatnonzero(is_k562 & np.isin(perturbations, chosen))
        print(f"held-out cells matched: {len(heldout_idx):,}")

        rng = np.random.default_rng(42)
        control_take = np.sort(
            rng.choice(control_idx, size=min(args.max_control, len(control_idx)), replace=False)
        )
        heldout_take = np.sort(
            rng.choice(heldout_idx, size=min(args.max_heldout, len(heldout_idx)), replace=False)
        )
        print(f"writing {len(control_take):,} control and {len(heldout_take):,} held-out cells")
        print(f"obs read elapsed: {time.time() - started:.1f}s")

        if args.dry_run:
            print("\n--dry-run: no files written")
            return 0

        x_dataset = open_dataset(h5, "X")
        registered_hvgs = [
            line.strip() for line in HVG_REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        CONTROL_OUT.parent.mkdir(parents=True, exist_ok=True)
        for rows, target in ((control_take, CONTROL_OUT), (heldout_take, HELDOUT_OUT)):
            matrix = load_to_sparse(x_dataset, rows)
            frame = build_anndata(
                matrix,
                select_registered_hvg(matrix, var_names, registered_hvgs),
                var_names,
                perturbations,
                cell_lines,
                gem_group,
                barcodes,
                rows,
            )
            frame.write_h5ad(target, compression="gzip")
            print(f"wrote {target.relative_to(PROJECT_ROOT)} shape={frame.shape}")
            del frame
        print(f"matrix read elapsed: {time.time() - started:.1f}s")

    write_split(chosen, test_perts)
    print(f"total elapsed: {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
