"""Bounded H5AD validation; the uploaded source is immutable."""

import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.app.config import Settings
from backend.app.core.registry import AssetRegistry
from backend.app.services.expression_scale import linear_cp10k, prepare_log_expression
from backend.app.user_data.schemas import UploadMetadata


def inspect_hdf5(path: Path, metadata: UploadMetadata, settings: Settings) -> None:
    import h5py
    from h5py.h5o import get_info

    decoded = 0
    objects = 0
    visited: set[int] = set()
    with h5py.File(path, "r") as handle:

        def inspect(group: Any, depth: int = 0) -> None:
            nonlocal decoded, objects
            if depth > 32:
                raise ValueError("HDF5 结构嵌套过深")
            for name in group.keys():
                objects += 1
                if objects > 100_000:
                    raise ValueError("HDF5 对象数量超过上限")
                if not isinstance(group.get(name, getlink=True), h5py.HardLink):
                    raise ValueError("不接受 HDF5 外部链接或软链接")
                item: Any = group[name]
                address = get_info(item.id).addr
                if address in visited:
                    raise ValueError("不接受循环或共享 HDF5 硬链接")
                visited.add(address)
                if isinstance(item, h5py.Dataset):
                    count = int(item.size or 0)
                    if h5py.check_dtype(ref=item.dtype) is not None:
                        raise ValueError("不接受 HDF5 引用对象")
                    decoded += count * max(8, int(item.dtype.itemsize))
                    if count > settings.max_matrix_values or decoded > settings.max_decoded_bytes:
                        raise ValueError("文件解码后的数组超过资源上限")
                    if item.dtype.kind == "O" and item.size:
                        # Bound variable-length metadata, not only its pointer array.
                        values = item[()]
                        decoded += sum(
                            len(value) if isinstance(value, (bytes, str)) else 0
                            for value in np.asarray(values).ravel()
                        )
                        if decoded > settings.max_decoded_bytes:
                            raise ValueError("文件元数据超过资源上限")
                else:
                    inspect(item, depth + 1)

        inspect(handle)
        key = "X" if metadata.input_layer == "X" else "layers/" + metadata.input_layer
        if key not in handle:
            raise ValueError("声明的表达矩阵不存在")
        matrix = handle[key]
        shape = matrix.shape if isinstance(matrix, h5py.Dataset) else matrix.attrs.get("shape")
        if shape is None or len(shape) != 2:
            raise ValueError("表达矩阵必须是二维")
        if not 2 <= int(shape[0]) <= settings.max_dataset_cells:
            raise ValueError(f"细胞数必须在 2–{settings.max_dataset_cells} 之间")
        if not 2 <= int(shape[1]) <= settings.max_dataset_genes:
            raise ValueError(f"基因数必须在 2–{settings.max_dataset_genes} 之间")


def read_expression(path: Path, metadata: UploadMetadata) -> tuple[Any, dict[str, Any]]:
    import anndata as ad

    source: Any = ad.read_h5ad(path)
    if source.n_obs < 2 or source.n_vars < 2:
        raise ValueError("至少需要两个细胞和两个基因")
    if not source.obs_names.is_unique or not source.var_names.is_unique:
        raise ValueError("细胞或基因标识重复；请先在数据源中解决重复项")
    if any(not str(name).strip() for name in source.obs_names):
        raise ValueError("细胞标识不能为空")
    genes = source.var["gene_symbol"] if "gene_symbol" in source.var else source.var_names
    if any(pd.isna(gene) for gene in genes):
        raise ValueError("基因符号不能为空")
    names = [str(gene).strip().upper() for gene in genes]
    if any(not name or not re.fullmatch(r"[A-Z0-9_.:-]+", name) for name in names):
        raise ValueError("基因标识格式无效；请使用 gene_symbol 列或 var_names")
    if len(set(names)) != len(names):
        raise ValueError("gene_symbol 中存在重复基因")
    matrix = source.X if metadata.input_layer == "X" else source.layers.get(metadata.input_layer)
    if matrix is None:
        raise ValueError("声明的表达矩阵不存在")
    if matrix.dtype.kind not in 'biuf':
        raise ValueError('表达矩阵必须包含实数计数或实数表达值')
    if hasattr(matrix, 'check_format'):
        matrix.check_format(full_check=True)
    data: Any = ad.AnnData(X=matrix.copy(), obs=source.obs.copy(), var=source.var.copy())
    data.var_names = pd.Index(names)
    data.var["gene_symbol"] = names
    total_key = metadata.total_counts_key
    if (
        metadata.expression_scale == "raw_counts"
        and metadata.matrix_scope == "full_library"
        and not total_key
    ):
        total_key = "_celllens_full_library_total"
        data.obs[total_key] = np.asarray(matrix.sum(axis=1)).reshape(-1)
    data = prepare_log_expression(data, metadata.expression_scale, total_counts_key=total_key)
    # Reject a declared log scale whose inverse overflows before accepting the source.
    linear_cp10k(data)
    groups: dict[str, list[str]] = {}
    for column in source.obs.columns:
        series = source.obs[column]
        if series.isna().any():
            continue
        choices = sorted(set(series.astype(str)))
        if 2 <= len(choices) <= 40 and all(len(value) <= 256 for value in choices):
            groups[str(column)] = choices
    summary = {
        "n_cells": int(data.n_obs),
        "n_genes": int(data.n_vars),
        "obs_columns": [str(column) for column in source.obs.columns],
        "group_columns": groups,
        "normalization": data.uns["celllens_expression"],
        "gene_identifier_source": "var.gene_symbol" if "gene_symbol" in source.var else "var_names",
        "warnings": ["文件校验通过不代表生物学适用性或实验结论已获验证。"],
    }
    return data, summary


def state_compatibility(data: Any, metadata: UploadMetadata, registry: AssetRegistry) -> dict[str, Any]:
    report: dict[str, Any] = {
        "available_for_prediction": False,
        "message": "用户上传数据目前用于下游分析；STATE 在线预测使用登记的参考数据。",
        "registered_background": False,
        "missing_genes": [],
        "missing_columns": [],
    }
    for model in registry.models:
        if model.get("cell_line", "").lower() != metadata.cell_context.strip().lower():
            continue
        report["registered_background"] = True
        report["model_id"] = model["id"]
        report["model_enabled"] = model["enabled"]
        report["missing_columns"] = [
            model[key]
            for key in ("cell_type_column", "perturbation_column")
            if model.get(key) and model[key] not in data.obs
        ]
        try:
            entry = registry.model_for(model["cell_line"], require_enabled=False)
            registry.verify_entry(entry, "gene_list_path", "gene_list_sha256")
            genes = entry.path("gene_list_path").read_text().splitlines()
            missing = sorted(set(gene.strip().upper() for gene in genes) - set(data.var_names))
            report.update(
                required_genes=len(genes), matched_genes=len(genes) - len(missing), missing_genes=missing
            )
        except Exception:
            report["message"] += " 登记模型的基因面板未就绪，无法完成面板检查。"
        break
    return report
