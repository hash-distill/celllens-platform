"""Public measured-data analysis; independent from model inference."""

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.api.resources import Cell, same_origin
from backend.app.services.measured_results import bundle_stream, csv_bytes, table_page
from backend.app.services.perturbation_catalog import normalize_target

router = APIRouter(prefix="/measured/analyses", tags=["measured"])
HEADERS = {"Cache-Control": "no-store"}
Table = Literal["genes", "tasks", "reactions"]


class MeasuredRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cell_line: Cell
    perturbation: str = Field(min_length=1, max_length=64)
    max_cells: int = Field(256, ge=1, le=4096)
    seed: int = Field(42, ge=0, le=2147483647)

    @field_validator("perturbation")
    @classmethod
    def target(cls, value):
        return normalize_target(value)


def translate(exc):
    if isinstance(exc, KeyError):
        return HTTPException(404, detail="未找到该实测分析")
    return HTTPException(409, detail=str(exc))


@router.get("")
def list_analyses(request: Request, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return JSONResponse(request.app.state.measured.list(limit, offset), headers=HEADERS)


@router.post("", status_code=202)
async def create(body: MeasuredRequest, request: Request):
    same_origin(request)
    try:
        row = await request.app.state.measured.start(body.model_dump())
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    return JSONResponse(row, status_code=202, headers=HEADERS)


@router.get("/{identifier}")
def detail(identifier: str, request: Request):
    try:
        return JSONResponse(request.app.state.measured.get(identifier), headers=HEADERS)
    except (KeyError, ValueError, OSError) as exc:
        raise translate(exc) from exc


@router.post("/{identifier}/cancel")
async def cancel(identifier: str, request: Request):
    same_origin(request)
    try:
        row = await request.app.state.measured.cancel(identifier)
    except (KeyError, ValueError, RuntimeError) as exc:
        raise translate(exc) from exc
    return JSONResponse(row, headers=HEADERS)


@router.get("/{identifier}/table")
def table(
    identifier: str,
    request: Request,
    kind: Table = "genes",
    query: str = Query("", max_length=500),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    try:
        directory, summary, _ = request.app.state.measured.result(identifier)
        return JSONResponse(table_page(directory, summary, kind, query, limit, offset), headers=HEADERS)
    except (KeyError, ValueError, OSError) as exc:
        raise translate(exc) from exc


@router.get("/{identifier}/projection")
def projection(identifier: str, request: Request, embedding: Literal["pca", "umap"] = "pca"):
    try:
        directory, _, _ = request.app.state.measured.result(identifier)
        path = directory / f"projection-{embedding}.json"
        if not path.is_file():
            raise ValueError("该投影不可用，请查看分析摘要中的原因")
        return JSONResponse(json.loads(path.read_text(encoding="utf-8")), headers=HEADERS)
    except (KeyError, ValueError, OSError) as exc:
        raise translate(exc) from exc


@router.get("/{identifier}/task-evidence")
def task_evidence(identifier: str, request: Request, task: str = Query(min_length=1, max_length=500)):
    from backend.app.services.measured_trace import measured_task_evidence

    try:
        directory, summary, _ = request.app.state.measured.result(identifier)
        if summary.get("analysis_id") != identifier:
            raise ValueError("任务证据与分析记录标识不一致")
        payload = measured_task_evidence(
            request.app.state.container.settings.project_root, directory, summary, task
        )
        _, digest = request.app.state.measured.store.get(identifier)
        payload["analysis_manifest_sha256"] = digest
        return JSONResponse(payload, headers=HEADERS)
    except (KeyError, ValueError, OSError) as exc:
        raise translate(exc) from exc


@router.get("/{identifier}/download")
async def download(
    identifier: str,
    request: Request,
    kind: Literal["bundle", "genes", "tasks", "reactions", "projection", "report"] = "bundle",
):
    try:
        directory, summary, manifest = await asyncio.to_thread(request.app.state.measured.result, identifier)
        if kind == "bundle":
            return StreamingResponse(
                bundle_stream(directory, manifest),
                media_type="application/zip",
                headers={**HEADERS, "Content-Disposition": f'attachment; filename="{identifier}.zip"'},
            )
        if kind == "report":
            return FileResponse(
                directory / "report.html",
                media_type="text/html",
                filename=f"{identifier}_report.html",
                headers=HEADERS,
            )
        if kind == "projection":
            payload = {
                name: json.loads(path.read_text(encoding="utf-8"))
                for name in ("pca", "umap")
                if (path := directory / f"projection-{name}.json").is_file()
            }
            return JSONResponse(
                payload,
                headers={
                    **HEADERS,
                    "Content-Disposition": f'attachment; filename="{identifier}_projection.json"',
                },
            )
        data = await asyncio.to_thread(csv_bytes, directory, summary, kind)
        return Response(
            data,
            media_type="text/csv; charset=utf-8",
            headers={**HEADERS, "Content-Disposition": f'attachment; filename="{identifier}_{kind}.csv"'},
        )
    except (KeyError, ValueError, OSError) as exc:
        raise translate(exc) from exc
