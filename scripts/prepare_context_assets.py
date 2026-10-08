"""Prepare pinned official ST-HVG models and measured controls for three new contexts.

No predictions are generated here. Only --register changes the live registry.
Existing K562 assets are never rewritten. Repeated downloads verify source hashes.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import pickle
import time
import tomllib
import urllib.request
from pathlib import Path
from typing import Any

import anndata as ad
import fsspec  # type: ignore[import-untyped]
import h5py
import numpy as np
import scipy.sparse as sp
import yaml

from scripts.extract_gene_list import _find_gene_sequence
from scripts.extract_replogle_k562 import (
    build_anndata,
    decode_categorical,
    decode_strings,
    load_to_sparse,
    select_registered_hvg,
)
from scripts.register_assets import _patch, sha256_of

ROOT = Path(__file__).resolve().parents[1]
MODEL_REPO = "arcinstitute/ST-HVG-Replogle"
MODEL_REVISION = "bb6a9562cbbf1fd152df14cc53b4cc7517c77175"
DATA_REPO = "arcinstitute/State-Replogle-Filtered"
DATA_REVISION = "d790193bb2c93726541a75ca3fa873a92ed44da5"
CONTEXTS = {"RPE1": "rpe1", "Jurkat": "jurkat", "HepG2": "hepg2"}
MODEL_FILES = (
    "checkpoints/final.ckpt",
    "config.yaml",
    "var_dims.pkl",
    "pert_onehot_map.pt",
    "batch_onehot_map.pkl",
    "cell_type_onehot_map.pkl",
)


def select_control_rows(
    cell_lines: np.ndarray, perturbations: np.ndarray, cell_line: str, *, max_cells: int, seed: int
) -> np.ndarray:
    if max_cells < 1:
        raise ValueError("max_cells must be positive")
    rows = np.flatnonzero((cell_lines == cell_line.lower()) & (perturbations == "non-targeting"))
    if not len(rows):
        raise ValueError(f"No {cell_line} non-targeting control cells")
    return np.sort(np.random.default_rng(seed).choice(rows, size=min(max_cells, len(rows)), replace=False))


def read_expression_rows(
    filesystem: Any, source_url: str, dataset: h5py.Dataset, rows: np.ndarray
) -> sp.csr_matrix:
    """Range-read only selected dense contiguous rows, with bounded parallel I/O."""
    offset = dataset.id.get_offset()
    if dataset.chunks is not None or offset is None:
        return load_to_sparse(dataset, rows)
    width = dataset.shape[1]
    row_bytes = width * dataset.dtype.itemsize

    def read_row(row: int) -> np.ndarray:
        start = offset + int(row) * row_bytes
        data = filesystem.cat_file(
            source_url, start=start, end=start + row_bytes, block_size=row_bytes, cache_type="none"
        )
        if len(data) != row_bytes:
            raise ValueError(f"Incomplete expression source range for row {row}")
        return np.frombuffer(data, dtype=dataset.dtype, count=width).copy()

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        values = []
        for index, values_row in enumerate(pool.map(read_row, rows), start=1):
            values.append(values_row)
            if index % 128 == 0:
                print(f"read measured expression rows {index}/{len(rows)}", flush=True)
    return sp.csr_matrix(np.stack(values))


def get_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def download_model_file(entry: dict[str, Any], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = entry.get("lfs", {}).get("oid")
    if target.is_file() and target.stat().st_size == entry["size"]:
        content_hash = (
            sha256_of(target)
            if expected
            else hashlib.sha1(f"blob {target.stat().st_size}\0".encode() + target.read_bytes()).hexdigest()
        )
        if content_hash == (expected or entry["oid"]):
            print(f"verified existing {entry['path']}", flush=True)
            return
        raise ValueError(f"Existing asset hash differs from pinned source: {target}")
    url = f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{entry['path']}"
    partial = target.with_name(target.name + ".partial")
    for attempt in range(3):
        try:
            total = 0
            digest = hashlib.sha256()
            with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as output:
                while chunk := response.read(4 * 1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
                    total += len(chunk)
                    if total % (64 * 1024 * 1024) == 0:
                        print(f"download {entry['path']} {total}/{entry['size']}", flush=True)
            if total != entry["size"]:
                raise ValueError(f"Wrong downloaded size: {entry['path']}: {total}")
            actual = (
                digest.hexdigest()
                if expected
                else hashlib.sha1(f"blob {total}\0".encode() + partial.read_bytes()).hexdigest()
            )
            if actual != (expected or entry["oid"]):
                raise ValueError(f"Pinned source hash mismatch: {entry['path']}")
            partial.replace(target)
            print(f"downloaded and verified {entry['path']}", flush=True)
            return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)


def prepare_models(contexts: list[str]) -> None:
    tree = json.loads(
        get_bytes(f"https://huggingface.co/api/models/{MODEL_REPO}/tree/{MODEL_REVISION}?recursive=true")
    )
    by_path = {entry["path"]: entry for entry in tree}
    jobs = []
    for context in contexts:
        slug = CONTEXTS[context]
        model_dir = ROOT / "models" / f"state-replogle-{slug}"
        for name in MODEL_FILES:
            jobs.append((by_path[f"fewshot/{slug}/{name}"], model_dir / name))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(download_model_file, entry, target) for entry, target in jobs]
        for future in futures:
            future.result()
    for context in contexts:
        slug = CONTEXTS[context]
        model_dir = ROOT / "models" / f"state-replogle-{slug}"
        with (model_dir / "var_dims.pkl").open("rb") as handle:
            genes = _find_gene_sequence(pickle.load(handle))
        if not genes or len(genes) != 2000 or len(set(genes)) != len(genes):
            raise ValueError(f"Invalid official gene panel for {context}")
        target = ROOT / "data" / "registry" / f"state_{slug}_genes.txt"
        target.write_text("\n".join(str(gene) for gene in genes) + "\n", encoding="utf-8")
        config = {
            "id": f"state-replogle-{slug}-fewshot-v1",
            "state_code_version": "0.11.1",
            "cell_line": context,
            "perturbation_type": "genetic",
            "perturbation_column": "gene",
            "cell_type_column": "cell_line",
            "embed_key": "X_hvg",
            "control_perturbation": "non-targeting",
            "output_space": "gene",
        }
        (ROOT / "configs" / "models" / f"state-replogle-{slug}.yaml").write_text(
            yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
        )
        files = {name: sha256_of(model_dir / name) for name in MODEL_FILES}
        (model_dir / "source_manifest.json").write_text(
            json.dumps(
                {
                    "repo": MODEL_REPO,
                    "revision": MODEL_REVISION,
                    "subdirectory": f"fewshot/{slug}",
                    "files": files,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def prepare_controls(contexts: list[str], max_cells: int, seed: int) -> None:
    url = f"hf://datasets/{DATA_REPO}@{DATA_REVISION}/replogle_concat.h5ad"
    shared_genes = (ROOT / "data" / "registry" / "state_k562_genes.txt").read_text().splitlines()
    filesystem = fsspec.filesystem("hf")
    print("opening pinned source for measured control extraction", flush=True)
    with filesystem.open(url, "rb", block_size=1024 * 1024) as handle, h5py.File(handle, "r") as h5:
        obs = h5["obs"]
        assert isinstance(obs, h5py.Group)
        lines = decode_categorical(obs["cell_line"])  # type: ignore[arg-type]
        print("read source cell backgrounds", flush=True)
        perts = decode_categorical(obs["gene"])  # type: ignore[arg-type]
        print("read source perturbation labels", flush=True)
        batches = np.asarray(obs["gem_group"])  # type: ignore[arg-type]
        print("read source batch labels", flush=True)
        genes = decode_strings(h5["var/gene_name_index"][:])  # type: ignore[index]
        matrix_source = h5["X"]
        assert isinstance(matrix_source, h5py.Dataset)
        print(f"expression layout {matrix_source.shape}, chunks={matrix_source.chunks}", flush=True)
        for context in contexts:
            slug = CONTEXTS[context]
            target_dir = ROOT / "data" / "raw" / f"replogle-{slug}"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / "control.h5ad"
            if target.exists():
                validate_control(target, context, shared_genes)
                print(f"verified existing control {context}", flush=True)
                continue
            rows = select_control_rows(lines, perts, context, max_cells=max_cells, seed=seed)
            print(f"reading {context} measured controls: {len(rows)}", flush=True)
            # Variable-length strings in HDF5 need many heap reads. Read the selected
            # source barcodes only, rather than all 643k entries across the atlas.
            barcodes = np.empty(len(lines), dtype=object)
            barcodes[rows] = decode_strings(obs["cell_barcode"][rows])  # type: ignore[index]
            print(f"read {context} selected source barcodes", flush=True)
            matrix = read_expression_rows(filesystem, url, matrix_source, rows)
            frame = build_anndata(
                matrix,
                select_registered_hvg(matrix, genes, shared_genes),
                genes,
                perts,
                lines,
                batches,
                barcodes,
                rows,
            )
            frame.obs["source_row"] = rows
            frame.uns["celllens_input_provenance"] = {
                "data_kind": "measured",
                "repo": DATA_REPO,
                "revision": DATA_REVISION,
                "source_file": "replogle_concat.h5ad",
                "matrix_slot": "X",
                "processing": "unchanged source expression; ordered HVG column selection only",
                "sampling_seed": seed,
            }
            partial = target.with_name("control.partial.h5ad")
            frame.write_h5ad(partial, compression="gzip")
            validate_control(partial, context, shared_genes)
            partial.replace(target)
            print(f"wrote measured control {context}: {frame.shape}", flush=True)


def validate_control(path: Path, context: str, genes: list[str]) -> None:
    frame = ad.read_h5ad(path)
    if set(frame.obs["cell_line"].astype(str)) != {context.lower()}:
        raise ValueError(f"Wrong background in {path}")
    if set(frame.obs["gene"].astype(str)) != {"non-targeting"}:
        raise ValueError(f"Perturbed cells in control input: {path}")
    expected = select_registered_hvg(sp.csr_matrix(frame.X), frame.var_names.to_numpy(), genes)
    if not np.isfinite(expected).all() or not np.array_equal(expected, frame.obsm["X_hvg"]):
        raise ValueError(f"Invalid ordered input prediction panel: {path}")


def register_contexts(contexts: list[str]) -> None:
    import torch

    audit = ROOT / "reports" / "context-integration-2026-10-08"
    audit.mkdir(parents=True, exist_ok=True)
    for filename in ("models.json", "datasets.json"):
        snapshot = audit / f"before-{filename}"
        if not snapshot.exists():
            snapshot.write_bytes((ROOT / "data" / "registry" / filename).read_bytes())
    for context in contexts:
        slug = CONTEXTS[context]
        model_dir = ROOT / "models" / f"state-replogle-{slug}"
        gene_path = ROOT / "data" / "registry" / f"state_{slug}_genes.txt"
        control = ROOT / "data" / "raw" / f"replogle-{slug}" / "control.h5ad"
        config_path = ROOT / "configs" / "models" / f"state-replogle-{slug}.yaml"
        genes = gene_path.read_text().splitlines()
        validate_control(control, context, genes)
        official_config = yaml.safe_load((model_dir / "config.yaml").read_text())
        kwargs = official_config["data"]["kwargs"]
        assert kwargs["embed_key"] == "X_hvg" and kwargs["pert_col"] == "gene"
        assert kwargs["cell_type_key"] == "cell_line" and kwargs["output_space"] == "gene"
        source = json.loads((model_dir / "source_manifest.json").read_text())
        for name, digest in source["files"].items():
            if sha256_of(model_dir / name) != digest:
                raise ValueError(f"Model companion hash mismatch: {context}/{name}")
        mapping = torch.load(model_dir / "pert_onehot_map.pt", map_location="cpu", weights_only=False)
        with (model_dir / "cell_type_onehot_map.pkl").open("rb") as handle:
            context_map = pickle.load(handle)
        if slug not in context_map:
            raise ValueError(f"Official model cannot encode {context}")
        split_bytes = get_bytes(
            f"https://huggingface.co/datasets/{DATA_REPO}/raw/{DATA_REVISION}/{slug}.toml"
        )
        tests = tomllib.loads(split_bytes.decode())["fewshot"][f"replogle.{slug}"]["test"]
        split = ROOT / "configs" / "splits" / f"replogle-{slug}-fewshot-v1.json"
        split.write_text(
            json.dumps(
                {
                    "version": f"replogle-{slug}-fewshot-v1",
                    "status": "frozen",
                    "cell_line": context,
                    "source": DATA_REPO,
                    "source_revision": DATA_REVISION,
                    "source_split_sha256": hashlib.sha256(split_bytes).hexdigest(),
                    "split_unit": "perturbation",
                    "development_groups": [],
                    "calibration_groups": [],
                    "test_groups": sorted(tests),
                    "decision_rule": (
                        "Online control-only input; no approved accuracy evaluation protocol yet."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        relative = lambda path: path.relative_to(ROOT).as_posix()  # noqa: E731
        model = {
            "id": f"state-replogle-{slug}-fewshot-v1",
            "cell_line": context,
            "code_version": "0.11.1",
            "model_dir": relative(model_dir),
            "checkpoint_path": relative(model_dir / "checkpoints/final.ckpt"),
            "checkpoint_sha256": sha256_of(model_dir / "checkpoints/final.ckpt"),
            "config_path": relative(config_path),
            "config_sha256": sha256_of(config_path),
            "gene_list_path": relative(gene_path),
            "gene_list_sha256": sha256_of(gene_path),
            "embed_key": "X_hvg",
            "perturbation_column": "gene",
            "cell_type_column": "cell_line",
            "control_perturbation": "non-targeting",
            "supported_perturbations": sorted(str(k).upper() for k in mapping),
            "license": "Arc State Model Non-Commercial License",
            "enabled": True,
        }
        dataset = {
            "id": f"replogle-{slug}-control-v1",
            "cell_line": context,
            "control_path": relative(control),
            "control_sha256": sha256_of(control),
            "split_path": relative(split),
            "split_sha256": sha256_of(split),
            "license": "See pinned State-Replogle-Filtered source and original Replogle/Nadig datasets",
            "enabled": True,
        }
        _patch(ROOT / "data/registry/models.json", "models", model)
        _patch(ROOT / "data/registry/datasets.json", "datasets", dataset)
        print(f"registered verified assets: {context}, {len(mapping)} perturbations", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contexts", nargs="+", choices=list(CONTEXTS), default=list(CONTEXTS))
    parser.add_argument("--phase", choices=["all", "models", "controls", "register"], default="all")
    parser.add_argument("--max-control", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.phase in {"all", "models"}:
        prepare_models(args.contexts)
    if args.phase in {"all", "controls"}:
        prepare_controls(args.contexts, args.max_control, args.seed)
    if args.phase == "register":
        register_contexts(args.contexts)


if __name__ == "__main__":
    main()
