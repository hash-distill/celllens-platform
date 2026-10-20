"""Read-only access to genuine measured perturbation comparisons."""

import csv
import io
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from backend.app.schemas import RunStatus
from backend.app.services.measured_comparison import (
    ComparisonUnavailable,
    comparison_examples,
    comparison_state,
    load_comparison,
    observation_status,
)

router = APIRouter(prefix="/runs", tags=["measured comparison"])


def _document(run_id: str, request: Request) -> dict:
    container = request.app.state.container
    try:
        record = container.store.get(run_id)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "RUN_NOT_FOUND"}) from exc
    if record.status != RunStatus.COMPLETED:
        raise HTTPException(409, detail={"code": "RUN_NOT_COMPLETED"})
    root = container.settings.project_root
    try:
        document = load_comparison(root, run_id)
        examples = []
        seen = set()
        for row in comparison_examples(root):
            key = (row["cell_line"], row["perturbation"])
            try:
                example = container.store.get(row["run_id"])
            except KeyError:
                continue
            if key not in seen and example.status == RunStatus.COMPLETED:
                examples.append(row)
                seen.add(key)
        if document is not None:
            return {**document, "examples": examples}
        obs = observation_status(root, record.request.cell_line, record.request.perturbation)
        known_zero = obs is not None and obs["status"] == "unavailable"
        state = comparison_state(root, run_id)
        preparing = bool(obs and obs["status"] == "available" and state and state["status"] == "preparing")
        failed = bool(state and state["status"] == "failed")
        reason = (
            "固定版本的官方数据集中没有该细胞背景与扰动的实测细胞，当前仅有模型预测。"
            if known_zero
            else "本次预测尚未生成匹配实测比较；不会生成或填补观测值。"
        )
        if preparing:
            reason = "真实观测已登记，实测比较正在准备；页面会自动重试，也可稍后刷新比较。"
        if failed:
            reason = "实测比较暂时不可用，原模型预测已保留；请联系维护人员检查比较任务。"
        source = obs.get("source") if obs else None
        return {
            "status": "preparing" if preparing else "unavailable",
            "run_id": run_id,
            "reason": reason,
            "cell_line": record.request.cell_line,
            "perturbation": record.request.perturbation,
            "available_measured_cells": obs.get("n_cells") if obs else None,
            "source": source,
            "examples": examples,
        }
    except (ComparisonUnavailable, OSError, ValueError, KeyError) as exc:
        raise HTTPException(
            409,
            detail={
                "code": "COMPARISON_SOURCE_CHANGED",
                "message": "实测比较来源缺失或哈希不一致，已停止展示。",
            },
        ) from exc


@router.get("/{run_id}/comparison")
def get_comparison(run_id: str, request: Request) -> dict:
    return _document(run_id, request)


@router.get("/{run_id}/comparison/download")
def download_comparison(run_id: str, request: Request, table: Literal["json", "genes", "tasks"] = "json"):
    doc = _document(run_id, request)
    if doc["status"] != "available":
        raise HTTPException(404, detail={"code": "MEASURED_COMPARISON_UNAVAILABLE"})
    if table == "json":
        content = json.dumps(doc, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
        extension, mime = "json", "application/json"
    else:
        stream = io.StringIO(newline="")
        fields = [
            "id",
            "control",
            "predicted",
            "observed",
            "predicted_delta",
            "observed_delta",
            "absolute_error",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(doc[table])
        content = ("\ufeff" + stream.getvalue()).encode("utf-8")
        extension, mime = "csv", "text/csv"
    return Response(
        content,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{run_id}_measured_comparison_{table}.{extension}"',
            "Cache-Control": "no-store",
        },
    )
