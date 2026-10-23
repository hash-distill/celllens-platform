"""Read-only exchange files assembled from verified, completed experiment results."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from backend.app.core.errors import CellLensError
from backend.app.services.cell_state import CellStateUnavailable
from backend.app.services.export_tables import export_table
from backend.app.services.measured_comparison import ComparisonUnavailable

router = APIRouter(prefix="/runs", tags=["exports"])


def _unavailable(exc: Exception):
    if isinstance(exc, ImportError):
        return HTTPException(
            503, detail={"code": "EXPORT_DEPENDENCY", "message": "导出组件暂不可用，请联系维护人员。"}
        )
    return HTTPException(
        409,
        detail={
            "code": "EXPORT_UNAVAILABLE",
            "message": "本次结果未提供所选导出，或来源校验未通过。请检查实验状态及来源文件。",
        },
    )


def _require_run(request: Request, run_id: str):
    try:
        request.app.state.container.store.get(run_id)
    except KeyError as exc:
        raise HTTPException(
            404, detail={"code": "EXPORT_SOURCE_NOT_FOUND", "message": "未找到该实验。"}
        ) from exc


@router.get("/{run_id}/export/table")
def get_export_table(
    run_id: str,
    request: Request,
    table: Literal["genes", "tasks", "reactions"] = "genes",
    population: Literal["original", "comparison"] = "original",
) -> Response:
    _require_run(request, run_id)
    try:
        content, filename = export_table(request.app.state.container, run_id, table, population)
    except (
        CellStateUnavailable,
        ComparisonUnavailable,
        CellLensError,
        OSError,
        KeyError,
        ValueError,
        ImportError,
    ) as exc:
        raise _unavailable(exc) from exc
    return Response(
        content,
        media_type="text/csv;charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/{run_id}/export")
def get_export_bundle(
    run_id: str,
    request: Request,
    package: Literal["analysis", "single-cell", "network", "ranking"] = "analysis",
    task_id: str = Query(default="", max_length=512),
) -> Response:
    _require_run(request, run_id)
    try:
        from backend.app.services.export_bundle import build_export_bundle

        content, filename = build_export_bundle(request.app.state.container, run_id, package, task_id=task_id)
    except (
        CellStateUnavailable,
        ComparisonUnavailable,
        CellLensError,
        OSError,
        KeyError,
        ValueError,
        ImportError,
    ) as exc:
        raise _unavailable(exc) from exc
    return Response(
        content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
