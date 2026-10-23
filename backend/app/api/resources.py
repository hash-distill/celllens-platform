"""User-triggered downloads of allowlisted inference resources, never arbitrary URLs."""

import asyncio
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/resources", tags=["resources"])
Cell = Literal["K562", "RPE1", "Jurkat", "HepG2"]


class DownloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted_license: bool


def same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(
            403, detail={"code": "RESOURCE_ORIGIN_REJECTED", "message": "请从当前服务页面发起操作"}
        )
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, detail={"code": "RESOURCE_ORIGIN_REJECTED"})


@router.get("")
async def list_resources(request: Request) -> JSONResponse:
    value = await asyncio.to_thread(request.app.state.resources.snapshot)
    return JSONResponse(value, headers={"Cache-Control": "no-store"})


@router.post("/{cell_line}/download", status_code=202)
async def start_download(cell_line: Cell, body: DownloadRequest, request: Request) -> JSONResponse:
    same_origin(request)
    try:
        value = await request.app.state.resources.start(cell_line, body.accepted_license)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "RESOURCE_NOT_ACCEPTED", "message": str(exc)}) from exc
    except RuntimeError as exc:
        raise HTTPException(409, detail={"code": "RESOURCE_BUSY", "message": str(exc)}) from exc
    return JSONResponse(value, status_code=202, headers={"Cache-Control": "no-store"})


@router.post("/{cell_line}/cancel")
async def cancel_download(cell_line: Cell, request: Request) -> JSONResponse:
    same_origin(request)
    try:
        await request.app.state.resources.cancel(cell_line)
    except RuntimeError as exc:
        raise HTTPException(409, detail={"code": "RESOURCE_OTHER_PROCESS", "message": str(exc)}) from exc
    return JSONResponse({"status": "cancelled"}, headers={"Cache-Control": "no-store"})
