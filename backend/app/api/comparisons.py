"""Read-only access to genuine measured perturbation comparisons."""

import json
import threading
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from backend.app.api.resources import same_origin
from backend.app.schemas import RunStatus
from backend.app.services.cell_state import CellStateUnavailable
from backend.app.services.export_tables import export_table
from backend.app.services.measured_comparison import (
    ComparisonUnavailable,
    comparison_examples,
    comparison_state,
    load_comparison,
    observation_status,
)

router = APIRouter(prefix="/runs", tags=["measured comparison"])
_diagnostics_lock = threading.Lock()


def _document(run_id: str, request: Request) -> dict:
    container = request.app.state.container
    if getattr(container.settings, "deployment_mode", "local") == "public":
        raise HTTPException(403, detail={"code": "PRIVATE_COMPARISON_DISABLED"})
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


@router.post("/{run_id}/comparison/diagnostics/prepare")
def prepare_comparison_diagnostics(run_id: str, request: Request) -> dict:
    same_origin(request)
    document = _document(run_id, request)
    if document["status"] != "available":
        raise HTTPException(409, detail={"code": "MEASURED_COMPARISON_UNAVAILABLE"})
    if not _diagnostics_lock.acquire(blocking=False):
        raise HTTPException(
            409, detail={"code": "DIAGNOSTICS_BUSY", "message": "另一个诊断正在准备，请稍后重试。"}
        )
    try:
        from backend.app.services.comparison_diagnostics import prepare_diagnostics

        prepare_diagnostics(request.app.state.container.settings.project_root, run_id)
        return _document(run_id, request)
    except (ComparisonUnavailable, OSError, ValueError, KeyError, ImportError) as exc:
        raise HTTPException(
            409,
            detail={"code": "DIAGNOSTICS_UNAVAILABLE", "message": f"诊断未能完成；原冻结结果保持不变：{exc}"},
        ) from exc
    finally:
        _diagnostics_lock.release()


@router.get("/{run_id}/comparison/download")
def download_comparison(run_id: str, request: Request, table: Literal["json", "genes", "tasks"] = "json"):
    doc = _document(run_id, request)
    if doc["status"] != "available":
        raise HTTPException(404, detail={"code": "MEASURED_COMPARISON_UNAVAILABLE"})
    if table == "json":
        content = json.dumps(doc, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
        extension, mime = "json", "application/json"
    else:
        try:
            content, _ = export_table(request.app.state.container, run_id, table, "comparison")
        except (CellStateUnavailable, ComparisonUnavailable, OSError, ValueError, KeyError) as exc:
            raise HTTPException(
                409,
                detail={
                    "code": "COMPARISON_EXPORT_UNAVAILABLE",
                    "message": "实测比较导出来源未通过校验，请检查冻结文件。",
                },
            ) from exc
        extension, mime = "csv", "text/csv"
    return Response(
        content,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{run_id}_measured_comparison_{table}.{extension}"',
            "Cache-Control": "no-store",
        },
    )
