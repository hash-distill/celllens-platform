"""Acquire only real, fixed-source populations for a measured analysis."""

import json
from pathlib import Path
from typing import Any

from backend.app.core.errors import CellLensError
from backend.app.core.registry import AssetRegistry
from backend.app.core.run_manifest import file_sha256
from backend.app.services.measured_analysis import checked_frame
from backend.app.services.perturbation_catalog import SOURCE
from backend.app.services.resource_downloads import safe_target


def source_identity() -> dict:
    return dict(SOURCE)


def registered_inputs(root: Path, cell: str, target: str) -> dict:
    registry = AssetRegistry(root, root / "data/registry")
    source = source_identity()
    groups = {}
    try:
        dataset = registry.dataset_for(cell)
        if registry.asset_is_valid_cached(dataset, "control_path", "control_sha256"):
            groups["control"] = {
                "path": str(dataset.path("control_path")),
                "sha256": dataset.payload["control_sha256"],
                "expression_scale": dataset.payload.get("expression_scale"),
                "origin": "registered_control",
                "dataset_id": dataset.payload["id"],
                "source_revision_verified": False,
                "note": "旧登记对照按路径和摘要核验；不补造文件中未记录的来源 revision",
            }
    except (CellLensError, ValueError):
        pass
    catalog = root / "data/registry/observations.json"
    if catalog.is_file():
        rows = [
            row
            for row in json.loads(catalog.read_text(encoding="utf-8")).get("observations", [])
            if row["cell_line"] == cell and row["perturbation"] == target and row["status"] == "available"
        ]
        if len(rows) > 1:
            raise ValueError("同一实测组合登记了多个来源，请先核对来源")
        if rows:
            row = rows[0]
            if all(row.get("source", {}).get(key) == source[key] for key in ("repo", "revision", "file")):
                path = safe_target(root, row["path"])
                if path.is_file() and file_sha256(path) == row.get("sha256"):
                    groups["observed"] = {
                        "path": str(path),
                        "sha256": row["sha256"],
                        "expression_scale": row.get("expression_scale"),
                        "origin": "registered_observation",
                        "source": source,
                    }
    return groups


def _descriptor(path: Path, source: dict) -> dict:
    return {
        "path": str(path),
        "sha256": file_sha256(path),
        "expression_scale": "log1p_cp10k",
        "origin": "fixed_source_range_extraction",
        "source": source,
    }


def _extract_missing(root: Path, request: dict, groups: dict, staging: Path, report: Any) -> None:
    import anndata as ad
    import fsspec
    import h5py
    import numpy as np
    import pandas as pd

    from scripts.extract_replogle_k562 import decode_categorical, decode_strings, open_dataset, open_group
    from scripts.prepare_context_assets import read_expression_rows

    source = source_identity()
    fs = fsspec.filesystem("hf")
    url = f"hf://datasets/{source['repo']}@{source['revision']}/{source['file']}"
    report(10, "从固定官方版本按需读取所选实测组合")
    with fs.open(url, "rb", block_size=1 << 20) as handle, h5py.File(handle, "r") as atlas:
        obs = open_group(atlas, "obs")
        lines = decode_categorical(open_group(obs, "cell_line"))
        perts = decode_categorical(open_group(obs, "gene"))
        batches = open_dataset(obs, "gem_group")[:]
        var = open_group(atlas, "var")
        key = var.attrs["_index"]
        if isinstance(key, bytes):
            key = key.decode()
        genes = decode_strings(open_dataset(var, str(key))[:])
        index_key = obs.attrs["_index"]
        if isinstance(index_key, bytes):
            index_key = index_key.decode()
        ids = open_dataset(obs, str(index_key))
        matrix = open_dataset(atlas, "X")
        for group, label, cap in (
            ("control", "non-targeting", 1024),
            ("observed", request["perturbation"], request["max_cells"]),
        ):
            if group in groups:
                continue
            available = np.flatnonzero((lines == request["cell_line"].lower()) & (perts == label))
            if group == "observed" and len(available) != request["source_cell_count"]:
                raise ValueError("实际源观测人数与冻结覆盖目录不符，请重新核对数据源")
            if not len(available):
                raise ValueError("固定数据源没有匹配的真实细胞；未使用模型生成替代数据")
            rows = np.sort(
                np.random.default_rng(request["seed"]).choice(
                    available,
                    size=min(cap, len(available)),
                    replace=False,
                )
            )
            report(15 if group == "control" else 22, f"范围提取 {len(rows)} 个真实 {group} 细胞")
            frame = ad.AnnData(
                read_expression_rows(fs, url, matrix, rows),
                obs=pd.DataFrame(
                    {
                        "cell_line": request["cell_line"].lower(),
                        "gene": label,
                        "gem_group": batches[rows],
                        "source_row": rows,
                        "cell_barcode": decode_strings(ids[rows]),
                    },
                    index=pd.Index([f"source_{i}" for i in rows]),
                ),
                var=pd.DataFrame(index=pd.Index(genes)),
            )
            frame.uns["celllens_provenance"] = {
                **source,
                "expression_scale": "log1p_cp10k",
                "sampling_seed": request["seed"],
                "sampling_limit": cap,
                "observations_generated": False,
                "selection": "fixed random source rows without replacement; unchanged source expression",
            }
            path = staging / "inputs" / f"{group}.h5ad"
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.write_h5ad(path, compression="gzip")
            groups[group] = _descriptor(path, source)


def prepare_inputs(root: Path, request: dict, staging: Path, report: Any) -> dict:
    import numpy as np

    if not isinstance(request.get("source_cell_count"), int) or request["source_cell_count"] <= 0:
        raise ValueError("需要已核验且存在真实观测的数据组合")
    if request.get("source", source_identity()) != source_identity():
        raise ValueError("任务冻结的源版本与当前固定目录不一致，请核对后重试")
    groups = registered_inputs(root, request["cell_line"], request["perturbation"])
    if "observed" in groups:
        entry = groups["observed"]
        frame = checked_frame(entry, request["cell_line"], request["perturbation"])
        required = min(request["max_cells"], request["source_cell_count"])
        if frame.n_obs < required:
            del groups["observed"]  # A smaller local subset is not the whole source.
        elif frame.n_obs > required:
            rows = np.sort(
                np.random.default_rng(request["seed"]).choice(frame.n_obs, size=required, replace=False)
            )
            subset = frame[rows].copy()
            path = staging / "inputs/observed.h5ad"
            path.parent.mkdir(parents=True, exist_ok=True)
            subset.write_h5ad(path, compression="gzip")
            groups["observed"] = _descriptor(path, source_identity()) | {
                "origin": "sampled_registered_observation",
                "sampling_seed": request["seed"],
                "source_reference": {
                    "path": Path(entry["path"]).relative_to(root).as_posix(),
                    "sha256": entry["sha256"],
                },
            }
    if len(groups) < 2:
        _extract_missing(root, request, groups, staging, report)
    # Validate labels and full real expression even when every asset was reused.
    for group, label in (("control", "non-targeting"), ("observed", request["perturbation"])):
        checked_frame(groups[group], request["cell_line"], label)
    return {
        "source": source_identity(),
        "source_cell_count": request["source_cell_count"],
        "source_catalog_sha256": request.get("source_catalog_sha256"),
        "sampling": {
            "max_observed_cells": request["max_cells"],
            "seed": request["seed"],
            "with_replacement": False,
        },
        "groups": groups,
    }
