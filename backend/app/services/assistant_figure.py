"""Small, numeric figure summaries; never forward cell coordinates or identifiers."""

import math
from typing import Any


def figure_summary(document: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "method",
        "embedding_space",
        "fit_source",
        "feature",
        "gene_count",
        "explained_variance_ratio",
        "embedding_parameters",
        "total_cells",
        "displayed_cells",
        "limitations",
    )
    summary = {key: document[key] for key in keys if key in document}
    preprocessing = document.get("embedding_preprocessing") or {}
    summary["embedding_preprocessing"] = {
        key: preprocessing[key]
        for key in ("feature_count", "input_units", "scaling", "missing_policy")
        if key in preprocessing
    }
    distributions = document.get("distributions", {})
    control_mean = (distributions.get("control") or {}).get("mean")
    groups = {}
    for source in ("control", "predicted", "observed"):
        group = distributions.get(source)
        if not isinstance(group, dict):
            continue
        values = {
            key: group.get(key) for key in ("n", "n_valid", "n_displayed", "mean", "median", "q25", "q75")
        }
        mean = values["mean"]
        values["mean_delta_vs_control"] = (
            mean - control_mean
            if isinstance(mean, (float, int))
            and isinstance(control_mean, (float, int))
            and math.isfinite(mean)
            and math.isfinite(control_mean)
            else None
        )
        groups[source] = values
    summary["distributions"] = groups
    summary["reading_scope"] = (
        "仅提供当前图表的方法与分布统计，没有发送图像、点坐标或逐细胞数值。"
        "可以解释 A 群体投影、B 指标着色、C 累积分布的读法；"
        "不能据此判断实际点云重叠、分离、聚类、密度或曲线的局部形状。"
        "均值差根据所有有效细胞计算，图中展示的细胞可能经过抽样。"
    )
    return summary
