"""Bounded single-file H5AD intake for local/private measured analysis only.

The configured root is an allowlist, never a directory browsing endpoint. Imported
expression is canonicalized before alignment/cropping and copied to a new version.
"""

import json
import re
import shutil
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from backend.app.core.errors import ScientificContractError
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.expression_scale import prepare_log_expression, validate_expression
from backend.app.services.measured_results import confined
from backend.app.services.resource_downloads import ResourceLease

MAX_CELLS = 20000
MAX_GENES = 60000
MAX_ELEMENTS = 12_000_000
MAX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024


def capabilities(settings):
    public = getattr(settings, "deployment_mode", "local") == "public"
    enabled = bool(
        getattr(settings, "controlled_import_enabled", False)
        and getattr(settings, "controlled_import_root", None)
        and not public
    )
    if enabled and not Path(settings.controlled_import_root).is_dir():
        enabled = False
    try:
        import anndata  # noqa: F401
        import h5py  # noqa: F401
    except ImportError:
        enabled = False
        reason = "缺少 H5AD 分析依赖"
    else:
        reason = None if enabled else "管理员尚未启用受控本地 H5AD 目录，或目录不存在"
    if public:
        reason = "公开部署仅提供冻结案例，不接受自有数据导入"
    return {
        "available": enabled,
        "reason": reason,
        "mode": "single-local-h5ad",
        "path_format": "受控目录内的相对文件路径，例如 experiment.h5ad；不接受绝对路径或 ../",
        "path_example": "experiment.h5ad",
        # Only authenticated local/private users reach this endpoint. Public mode
        # never returns the server path, even when called outside HTTP middleware.
        "import_directory": str(Path(settings.controlled_import_root).resolve()) if enabled else None,
        "scales": ["raw_counts", "cp10k", "log1p_cp10k"],
        "max_bytes": getattr(settings, "controlled_import_max_bytes", 268435456),
        "max_cells": MAX_CELLS,
        "max_genes": MAX_GENES,
        "max_matrix_elements": MAX_ELEMENTS,
        "raw_counts_requires": "full_library=true or explicit total_counts_key",
        "outputs": ["descriptive_measured_expression", "expression_derived_function_if_available"],
        "custom_prediction_available": False,
    }


def _h5_preflight(path):
    """Reject HDF links/virtual storage before AnnData can read outside the file."""
    import h5py
    import h5py.h5o as h5o
    import numpy as np

    total_bytes = 0
    visited = set()
    objects = 0
    with h5py.File(path, "r") as handle:

        def visit(group: h5py.Group):
            nonlocal total_bytes, objects
            for name in group:
                link = group.get(name, getlink=True)
                if not isinstance(link, h5py.HardLink):
                    raise ValueError("H5AD 不允许外部链接或软链接")
                value = group[name]
                if not isinstance(value, (h5py.Group, h5py.Dataset)):
                    raise ValueError("H5AD 只接受分组与数据集，不接受命名数据类型")
                address = h5o.get_info(value.id).addr
                if address in visited:
                    raise ValueError("H5AD 不允许循环或复用的 HDF 硬链接")
                visited.add(address)
                objects += 1
                if objects > 20000:
                    raise ValueError("H5AD 元数据对象超过上限")
                if isinstance(value, h5py.Group):
                    visit(value)
                else:
                    if value.is_virtual or value.external:
                        raise ValueError("H5AD 不允许虚拟或外部存储数据集")
                    if value.size is None:
                        raise ValueError("H5AD 不接受未定义形状的数据集")
                    size = int(value.size)
                    if size > MAX_ELEMENTS * 3:
                        raise ValueError("H5AD 数据集超过内存上限")
                    total_bytes += size * max(int(value.dtype.itemsize), 8)
                    if total_bytes > MAX_UNCOMPRESSED_BYTES:
                        raise ValueError("H5AD 解压后数据超过内存上限")

        visit(handle)
        if "X" not in handle:
            raise ValueError("H5AD 缺少 X 表达矩阵")
        matrix = handle["X"]
        if not isinstance(matrix, (h5py.Group, h5py.Dataset)):
            raise ValueError("H5AD X 必须是数据集或稀疏矩阵分组")
        values = matrix.get("data") if isinstance(matrix, h5py.Group) else matrix
        if not isinstance(values, h5py.Dataset) or values.dtype.kind not in "biuf":
            raise ValueError("H5AD X 必须是数值表达矩阵")
        shape = matrix.attrs.get("shape") if isinstance(matrix, h5py.Group) else matrix.shape
        if shape is None or len(shape) != 2:
            raise ValueError("H5AD X 必须是二维表达矩阵")
        rows, cols = (int(value) for value in np.asarray(shape))
        if not 2 <= rows <= MAX_CELLS or not 1 <= cols <= MAX_GENES or rows * cols > MAX_ELEMENTS:
            raise ValueError("H5AD 细胞数、基因数或矩阵尺寸超过受控资源上限")


def _resolve_source(settings, relative):
    if not capabilities(settings)["available"]:
        raise ValueError("受控 H5AD 导入尚未启用")
    if not relative or Path(relative).is_absolute() or re.match(r"^[A-Za-z]:|^[/\\]", relative):
        raise ValueError("仅接受受控目录内的相对 H5AD 文件名")
    root = Path(settings.controlled_import_root).resolve()
    path = confined(root, relative)
    if path.suffix.lower() != ".h5ad" or not path.is_file():
        raise ValueError("受控目录中没有指定的单个 H5AD 文件")
    if path.stat().st_size > settings.controlled_import_max_bytes:
        raise ValueError("H5AD 文件超过大小上限")
    return path


def import_h5ad(settings, request):
    source = _resolve_source(settings, request["relative_path"])
    return _import_h5ad_source(
        settings,
        request,
        source,
        source_filename=source.name,
        max_bytes=settings.controlled_import_max_bytes,
    )


def _import_h5ad_source(settings, request, source, *, source_filename, max_bytes):
    """Freeze a service-resolved source; never expose this path override in request JSON."""
    import anndata as ad
    import numpy as np
    import pandas as pd
    from scipy import sparse

    root = settings.project_root.resolve()
    base = root / "data/imports"
    base.mkdir(parents=True, exist_ok=True)
    with closing(ResourceLease(base / "import.lock")):
        identifier = "import_" + uuid4().hex[:24]
        staging = base / ("." + identifier + ".partial")
        final = base / identifier
        staging.mkdir()
        try:
            snapshot = staging / "source.h5ad"
            source_digest = file_sha256(source)
            shutil.copyfile(source, snapshot)
            if snapshot.stat().st_size > max_bytes:
                raise ValueError("H5AD 文件超过大小上限")
            if file_sha256(snapshot) != source_digest or file_sha256(source) != source_digest:
                raise ValueError("导入期间源文件改变，请重新导入")
            _h5_preflight(snapshot)
            frame = ad.read_h5ad(snapshot, backed="r")
            try:
                genes = frame.var_names.astype(str)
                if not genes.is_unique or not frame.obs_names.is_unique:
                    raise ValueError("基因 ID 和细胞 ID 必须唯一；不会自动合并或改名")
                if any(not gene.strip() or gene != gene.strip() for gene in genes):
                    raise ValueError("基因 ID 不得为空或包含首尾空格")
                if len({gene.upper() for gene in genes}) != len(genes):
                    raise ValueError("基因 ID 经大小写规范化后重复")
                key = request["group_key"]
                labels = frame.obs[key] if key in frame.obs else None
                if not isinstance(labels, pd.Series) or labels.isna().any():
                    raise ValueError("分组列缺失或存在空标签")
                labels = labels.astype(str)
                control_label, target_label = request["control_label"], request["target_label"]
                if control_label == target_label:
                    raise ValueError("对照与目标分组不能相同")
                selected = {
                    "control": np.flatnonzero(labels == control_label),
                    "observed": np.flatnonzero(labels == target_label),
                }
                counts = {name: len(rows) for name, rows in selected.items()}
                if not all(counts.values()):
                    raise ValueError("所选对照或目标组没有细胞")
                background_status = "user_declared_no_source_background"
                if "cell_line" in frame.obs:
                    source_background = frame.obs.iloc[np.concatenate(list(selected.values()))]["cell_line"]
                    if source_background.isna().any() or set(
                        source_background.astype(str).str.strip().str.lower()
                    ) != {request["cell_line"].strip().lower()}:
                        raise ValueError("所选群体的原始 cell_line 与声明背景不符；单文件导入不混合多个背景")
                    background_status = "verified_obs_cell_line"
                scale = request["expression_scale"]
                total_key = request.get("total_counts_key")
                if scale == "raw_counts" and not total_key and not request.get("full_library"):
                    raise ValueError("raw_counts 必须声明完整基因矩阵或提供全库总计数列")
                if total_key and total_key not in frame.obs:
                    raise ValueError("指定的全库总计数列不存在")
                # Validate all expression, including unused groups, without materializing the full file.
                full_totals = np.zeros(frame.n_obs, dtype=float)
                source_matrix = frame.X
                if source_matrix is None:
                    raise ValueError("H5AD 缺少 X 表达矩阵")
                for start in range(0, frame.n_obs, 256):
                    block = source_matrix[start : start + 256]
                    matrix = (
                        block
                        if isinstance(
                            block, (sparse.csr_matrix, sparse.csc_matrix, sparse.csr_array, sparse.csc_array)
                        )
                        else np.asarray(block)
                    )
                    try:
                        validate_expression(matrix)
                    except ScientificContractError as exc:
                        raise ValueError("表达矩阵必须是有限非负数；检测到 NaN、Inf 或负值") from exc
                    values = matrix if isinstance(matrix, np.ndarray) else matrix.data
                    if scale == "raw_counts" and not np.allclose(values, np.rint(values), atol=1e-5, rtol=0):
                        raise ValueError("raw_counts 包含非整数表达")
                    if scale == "log1p_cp10k" and np.any(values > np.log1p(10000.1)):
                        raise ValueError("声明的 log1p_cp10k 超过单基因 CP10K 范围")
                    if scale in {"cp10k", "log1p_cp10k"}:
                        linear = matrix.copy()
                        if scale == "log1p_cp10k":
                            if not isinstance(linear, np.ndarray):
                                linear.data = np.expm1(linear.data)
                            else:
                                linear = np.expm1(linear)
                        if np.any(np.asarray(linear.sum(axis=1)).reshape(-1) > 10001):
                            raise ValueError("声明的 CP10K 每细胞表达总和超过 10000 容差")
                    full_totals[start : start + 256] = np.asarray(matrix.sum(axis=1)).reshape(-1)
                if scale == "raw_counts":
                    denominators = np.asarray(frame.obs[total_key], dtype=float) if total_key else full_totals
                    if not np.isfinite(denominators).all() or np.any(denominators <= 0):
                        raise ValueError("全库总计数必须为有限正数")
                    if np.any(full_totals > denominators + 1e-5):
                        raise ValueError("全库总计数小于矩阵表达计数")
                    if not np.allclose(denominators, np.rint(denominators), atol=1e-5, rtol=0):
                        raise ValueError("原始全库总计数必须为整数")
                    if request.get("full_library") and not np.allclose(
                        full_totals, denominators, atol=1e-5, rtol=0
                    ):
                        raise ValueError("完整基因矩阵声明与所提供全库计数不一致")
                else:
                    denominators = None
                groups = {}
                for name, rows in selected.items():
                    if len(rows) > request["max_cells"]:
                        rows = np.sort(
                            np.random.default_rng(request["seed"]).choice(
                                rows, request["max_cells"], replace=False
                            )
                        )
                    obs = pd.DataFrame(index=frame.obs_names[rows].copy())
                    obs["cell_line"] = request["cell_line"].lower()
                    obs["gene"] = "non-targeting" if name == "control" else request["perturbation"]
                    obs["source_row"] = rows
                    obs["source_group_label"] = labels.iloc[rows].to_numpy()
                    if request.get("batch_key"):
                        batch_key = request["batch_key"]
                        batches = frame.obs[batch_key] if batch_key in frame.obs else None
                        if not isinstance(batches, pd.Series) or batches.isna().any():
                            raise ValueError("批次列缺失或包含空标签")
                        obs["gem_group"] = batches.iloc[rows].astype(str).to_numpy()
                    if denominators is not None:
                        obs["full_library_total_counts"] = denominators[rows]
                    subset = ad.AnnData(source_matrix[rows, :], obs=obs, var=pd.DataFrame(index=genes.copy()))
                    canonical = prepare_log_expression(
                        subset,
                        scale,
                        total_counts_key="full_library_total_counts" if denominators is not None else None,
                    )
                    path = staging / f"{name}.h5ad"
                    canonical.write_h5ad(path, compression="gzip")
                    groups[name] = {
                        "path": (final / path.name).relative_to(root).as_posix(),
                        "sha256": file_sha256(path),
                        "expression_scale": "log1p_cp10k",
                        "origin": "controlled_private_h5ad",
                        "selected_cells": len(rows),
                    }
                manifest = {
                    "schema_version": "controlled-h5ad-v1",
                    "import_id": identifier,
                    "source_kind": "measured",
                    "source_sha256": source_digest,
                    "source_filename": source_filename,
                    "source_cells": int(frame.n_obs),
                    "gene_count": int(frame.n_vars),
                    "group_counts": counts,
                    "selected_counts": {name: value["selected_cells"] for name, value in groups.items()},
                    "cell_line": request["cell_line"],
                    "background_validation": background_status,
                    "perturbation": request["perturbation"],
                    "contract": {key: value for key, value in request.items() if key != "relative_path"},
                    "normalization": {
                        "input_scale": scale,
                        "output_scale": "log1p_cp10k",
                        "denominator": total_key
                        or ("all source X genes" if scale == "raw_counts" else "upstream declared CP10K"),
                        "before_gene_crop": True,
                    },
                    "groups": groups,
                    "custom_prediction_available": False,
                    "limitations": [
                        "仅进行描述性实测比较；细胞记录不等于独立生物学重复。",
                        "表达尺度和完整基因声明由输入者负责，未依据数值猜测尺度。",
                    ],
                }
            finally:
                frame.file.close()
            atomic_write_json(staging / "manifest.json", manifest)
            staging.replace(final)
            return get_import(root, identifier)
        except BaseException:
            # Staging is a direct child of our own import directory, never caller-derived.
            if staging.resolve().parent == base.resolve() and staging.exists():
                shutil.rmtree(staging)
            raise


def get_import(root, identifier):
    if not re.fullmatch(r"import_[a-f0-9]{24}", identifier):
        raise KeyError(identifier)
    directory = root.resolve() / "data/imports" / identifier
    path = directory / "manifest.json"
    if not path.is_file():
        raise KeyError(identifier)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("import_id") != identifier:
        raise ValueError("导入清单身份不匹配")
    for entry in manifest["groups"].values():
        item = confined(root, entry["path"])
        if not item.is_relative_to(directory) or not item.is_file() or file_sha256(item) != entry["sha256"]:
            raise ValueError("导入数据版本已改变")
    source = directory / "source.h5ad"
    if not source.is_file() or file_sha256(source) != manifest["source_sha256"]:
        raise ValueError("导入源快照已改变")
    return {**manifest, "manifest_sha256": file_sha256(path)}


def import_analysis_request(root, request):
    """Called by measured job submission; freeze the import version in request_json."""
    manifest = get_import(root, request["import_id"])
    return {
        **request,
        "cell_line": manifest["cell_line"],
        "perturbation": manifest["perturbation"],
        "source_cell_count": manifest["group_counts"]["observed"],
        "max_cells": manifest["contract"]["max_cells"],
        "seed": manifest["contract"]["seed"],
        "import_manifest_sha256": manifest["manifest_sha256"],
        "source": {
            "kind": "controlled_private_h5ad",
            "import_id": manifest["import_id"],
            "source_sha256": manifest["source_sha256"],
        },
    }


def prepare_import_inputs(root, request, staging, report):
    manifest = get_import(root, request["import_id"])
    if manifest["manifest_sha256"] != request.get("import_manifest_sha256"):
        raise ValueError("任务冻结的导入版本与当前数据不一致")
    report(20, "核验受控 H5AD 的冻结实测群体")
    groups = {}
    for name, entry in manifest["groups"].items():
        groups[name] = {
            **entry,
            "path": str(confined(root, entry["path"])),
            "source_reference": {
                "path": f"data/imports/{manifest['import_id']}/source.h5ad",
                "sha256": manifest["source_sha256"],
            },
        }
    return {
        "source": request["source"],
        "source_cell_count": request["source_cell_count"],
        "import_manifest_sha256": manifest["manifest_sha256"],
        "normalization": manifest["normalization"],
        "input_contract": manifest["contract"],
        "background_validation": manifest.get("background_validation", "unknown"),
        "sampling": {
            "max_cells_per_group": manifest["contract"]["max_cells"],
            "seed": manifest["contract"]["seed"],
            "with_replacement": False,
        },
        "groups": groups,
    }
