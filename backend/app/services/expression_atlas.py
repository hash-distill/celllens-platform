"""Single-cell heatmap samples and full-population expression summaries."""

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from backend.app.services.figure_workspace import COLORS, archive_bound


class ExpressionAtlasSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    genes: list[str] = Field(min_length=1, max_length=20)
    cells_per_group: int = Field(default=150, ge=10, le=300)


def expression_atlas(workspace, kind, identifier, spec):
    result, directory, _, _ = workspace.source(kind, identifier)
    metadata, path = workspace.expression_metadata(kind, identifier, directory)
    if metadata is None or path is None:
        raise ValueError("此历史结果没有冻结的逐细胞表达，无法生成单细胞图谱")
    genes = list(dict.fromkeys(spec.genes))
    if any(not gene or len(gene) > 500 or gene not in metadata["genes"] for gene in genes):
        raise ValueError("请选择当前冻结表达面板内的基因")
    indices = [metadata["genes"].index(gene) for gene in genes]
    cells = metadata["cells"]
    archive_bound(path)
    if kind == "measured":
        from scipy.sparse import load_npz

        original = load_npz(path)
        if original.shape != (len(cells), len(metadata["genes"])):
            raise ValueError("逐细胞表达矩阵与身份记录不一致")
        matrix = original[:, indices].toarray().astype(float)
    else:
        matrix = np.full((len(cells), len(genes)), np.nan)
        with np.load(path, allow_pickle=False) as archive:
            for source in COLORS:
                positions = [i for i, cell in enumerate(cells) if cell["source"] == source]
                if positions:
                    original = archive[f"expression_{source}"]
                    if original.shape != (len(positions), len(metadata["genes"])):
                        raise ValueError("预测表达矩阵与身份记录不一致")
                    matrix[positions] = original[:, indices]
    if not np.isfinite(matrix).all():
        raise ValueError("逐细胞表达包含非有限数值，已停止绘图")
    groups, sampled = [], []
    for source in ("control", "observed", "predicted"):
        positions = [i for i, cell in enumerate(cells) if cell["source"] == source]
        if not positions:
            continue
        positions.sort(key=lambda i: cells[i]["cell_id"])
        selected = positions if len(positions) <= spec.cells_per_group else [
            positions[int(i)] for i in np.linspace(0, len(positions) - 1, spec.cells_per_group)
        ]
        values = matrix[positions]
        groups.append({
            "source": source, "count": len(positions), "displayed": len(selected),
            "genes": [{"gene": gene, "mean": float(values[:, j].mean()),
                       "median": float(np.median(values[:, j])),
                       "q25": float(np.quantile(values[:, j], .25)),
                       "q75": float(np.quantile(values[:, j], .75)),
                       "positive_fraction": float((values[:, j] > 0).mean())}
                      for j, gene in enumerate(genes)],
        })
        sampled.extend({**cells[i], "values": matrix[i].tolist()} for i in selected)
    return {
        "record_id": identifier, "kind": kind, "genes": genes, "units": metadata["units"],
        "provenance": result.get("provenance", {}), "groups": groups, "cells": sampled,
        "value_domain": [float(min(0, matrix.min())), float(max(0, matrix.max()))],
        "sampling": {"method": "cell-id-sorted-evenly-spaced", "cells_per_group": spec.cells_per_group,
                     "summary_population": "all-frozen-cells", "positive_threshold": 0},
    }
