"""Serve existing expression coordinates; never fit, reconstruct or publish on GET."""

import hashlib
import json
import math
from collections import Counter

from backend.app.services.measured_results import confined

METHODS = {"pca": "control-reference-pca", "umap": "joint-umap"}


def read_json(path, expected):
    if not expected or not path.is_file():
        raise ValueError("未找到有清单摘要的现成表达投影")
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("表达投影文件超过读取上限")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("表达投影文件与冻结清单不符")
    document = json.loads(data)
    if not isinstance(document, dict):
        raise ValueError("表达投影必须是对象格式")
    return document


def projection_payload(document, kind, embedding, provenance):
    if embedding not in METHODS or document.get("method") != METHODS[embedding]:
        raise ValueError("历史坐标未记录可信的 PCA/UMAP 方法；不会以随机投影替代")
    units = document.get("expression_units", document.get("input_units"))
    if units != "log1p(CP10K)":
        raise ValueError("现成表达投影未记录受支持的表达尺度")
    points = document.get("points")
    if not isinstance(points, list) or not points or len(points) > 100000:
        raise ValueError("表达投影坐标为空或超过读取上限")
    required = {"control", "observed"} if kind == "measured" else {"control", "predicted"}
    allowed = required if kind == "measured" else required | {"observed"}
    seen = set()
    coordinates = []
    for point in points:
        if not isinstance(point, dict):
            raise ValueError("表达投影坐标记录格式无效")
        source = point.get("source")
        if source not in allowed:
            raise ValueError("表达投影含有未知或不属于该研究的群体")
        for axis in ("x", "y"):
            value = point.get(axis)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("表达投影坐标必须是有限数值")
        identity = point.get("cell_id", point.get("cell_index"))
        if identity is None or isinstance(identity, bool) or (source, str(identity)) in seen:
            raise ValueError("表达投影缺少唯一细胞记录身份")
        seen.add((source, str(identity)))
        # Feature color is intentionally absent: a saved default gene is not the UI's selected gene.
        coordinates.append(
            {key: point[key] for key in ("x", "y", "source", "cell_id", "cell_index") if key in point}
        )
    displayed = dict(Counter(point["source"] for point in coordinates))
    if not required.issubset(displayed):
        raise ValueError("表达投影缺少所需的对照或目标群体")
    counts = document.get("counts") or {
        source: values.get("n") for source, values in document.get("distributions", {}).items()
    }
    if not isinstance(counts, dict):
        raise ValueError("表达投影的群体数记录格式无效")
    recorded_counts = counts
    counts: dict[str, int | None] = {}
    for source in displayed:
        count = recorded_counts.get(source)
        if count is not None and (
            isinstance(count, bool) or not isinstance(count, int) or count < displayed[source]
        ):
            raise ValueError("表达投影的群体数与已保存坐标不一致")
        counts[source] = count
    known_counts = [count for count in counts.values() if count is not None]
    variance = document.get("explained_variance_ratio")
    if variance is not None and (
        not isinstance(variance, list)
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= 1
            for value in variance
        )
    ):
        raise ValueError("冻结投影的解释方差记录无效")
    parameters = document.get("parameters", document.get("embedding_parameters"))
    # Small explicit method fields only; never expose a saved default feature or
    # private path through arbitrary embedding metadata.
    parameter_keys = (
        "n_components",
        "n_neighbors",
        "min_dist",
        "metric",
        "random_state",
        "n_jobs",
        "init",
        "fit_sources",
        "preprocessing",
        "package_versions",
    )
    parameters = (
        {key: parameters[key] for key in parameter_keys if key in parameters}
        if isinstance(parameters, dict)
        else None
    )
    preprocessing = document.get("embedding_preprocessing")
    preprocessing = (
        {
            key: preprocessing[key]
            for key in ("feature_count", "input_units", "scaling", "missing_policy")
            if key in preprocessing
        }
        if isinstance(preprocessing, dict)
        else None
    )
    return {
        "available": True,
        "method": METHODS[embedding],
        "embedding": embedding,
        "source_kind": "measured" if kind == "measured" else "prediction",
        "points": coordinates,
        "counts": counts,
        "displayed_counts": displayed,
        "total_cells": sum(known_counts) if len(known_counts) == len(counts) else None,
        "displayed_cells": len(coordinates),
        "gene_count": document.get("gene_count"),
        "input_units": units,
        "fit_source": document.get("fit_source"),
        "explained_variance_ratio": variance,
        "parameters": parameters,
        "preprocessing": preprocessing,
        "coordinates_are_physical_positions": False,
        "provenance": provenance,
        "limitations": document.get("limitations", [])
        + [
            "仅展示冻结坐标；切换基因不会重新拟合坐标，也不把默认基因颜色当作当前选择的表达。",
            "投影不代表细胞形态、物理位置、运动轨迹或统计显著性。",
        ],
    }


def prediction_projection(container, identifier, embedding):
    from backend.app.services.cell_state import frozen_inputs
    from backend.app.services.cell_state_preparation import prepared_manifest

    inputs = frozen_inputs(container, identifier)
    bundle = prepared_manifest(container, inputs)
    if bundle is not None:
        root, manifest = bundle
        name = f"expression_{embedding}.json"
        if f"expression_{embedding}" not in manifest.get("figures", {}):
            raise ValueError("此结果未冻结所选表达投影；读取操作不会现场生成")
        digest = manifest["outputs"].get(name)
        document = read_json(confined(root, name), digest)
        if (
            document.get("run_id") != identifier
            or document.get("embedding_space") != "expression"
            or document.get("provenance", {}).get("manifest_sha256") != inputs["manifest_sha256"]
        ):
            raise ValueError("表达投影身份或来源清单不匹配")
        prepared_bytes = (root / "prepared.json").read_bytes()
        prepared_sha = hashlib.sha256(prepared_bytes).hexdigest()
        expected_prepared = [
            item.sha256
            for item in container.store.artifacts(identifier)
            if getattr(item, "kind", None) == "cell_state_preparation"
        ]
        if expected_prepared != [prepared_sha]:
            raise ValueError("读取期间表达投影清单改变")
        return projection_payload(
            document,
            "prediction",
            embedding,
            {
                "manifest_sha256": inputs["manifest_sha256"],
                "prepared_manifest_sha256": prepared_sha,
                "projection_sha256": digest,
                "source_run_id": inputs["source_run_id"],
                "artifact": f"cell_state/{name}",
            },
        )
    # Only a genuinely fitted, explicitly scaled, hash-bound original projection qualifies.
    root = container.settings.derived_root / identifier
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    expected = manifest.get("outputs", {}).get("projection.json", {}).get("sha256")
    document = read_json(confined(root, "projection.json"), expected)
    return projection_payload(
        document,
        "prediction",
        embedding,
        {
            "manifest_sha256": inputs["manifest_sha256"],
            "projection_sha256": expected,
            "source_run_id": inputs["source_run_id"],
            "artifact": "projection.json",
        },
    )
