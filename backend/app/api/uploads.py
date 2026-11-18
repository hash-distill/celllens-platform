"""Browser H5AD intake without multipart buffering or client-selected server paths."""

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.requests import ClientDisconnect

from backend.app.api.research import ImportRequest, translate
from backend.app.api.resources import same_origin
from backend.app.core.errors import CellLensError
from backend.app.services.h5ad_uploads import (
    UploadTooLarge,
    UploadUnavailable,
    _thread_complete,
    capabilities,
    delete_upload,
    get_upload,
    import_upload,
    receive_upload,
)

router = APIRouter(prefix="/research/uploads", tags=["research uploads"])
HEADERS = {"Cache-Control": "no-store"}


class UploadImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression_scale: Literal["raw_counts", "cp10k", "log1p_cp10k"]
    full_library: bool = False
    total_counts_key: str | None = Field(None, min_length=1, max_length=100)
    group_key: str = Field(min_length=1, max_length=100)
    control_label: str = Field(min_length=1, max_length=200)
    target_label: str = Field(min_length=1, max_length=200)
    cell_line: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_. -]+$")
    perturbation: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    batch_key: str | None = Field(None, min_length=1, max_length=100)
    max_cells: int = Field(256, ge=2, le=4096)
    seed: int = Field(42, ge=0, le=2147483647)

    @model_validator(mode="after")
    def check_contract(self):
        validated = ImportRequest.model_validate({"relative_path": "source.h5ad", **self.model_dump()})
        self.cell_line = validated.cell_line
        return self


def upload_error(exc):
    if isinstance(exc, UploadTooLarge):
        return HTTPException(413, detail=str(exc))
    if isinstance(exc, UploadUnavailable):
        return HTTPException(403, detail=str(exc))
    if isinstance(exc, TimeoutError):
        return HTTPException(408, detail="上传超时，请重新选择文件上传")
    if isinstance(exc, ClientDisconnect):
        return HTTPException(400, detail="上传连接已中断，临时文件已清理")
    if isinstance(exc, (ValueError, TypeError, AttributeError)):
        return HTTPException(422, detail=str(exc))
    return translate(exc)


async def upload_client_disconnected(request: Request) -> bool:
    """Probe only after the body has ended, including through BaseHTTPMiddleware.

    Starlette's immediate-cancellation probe can stop at a middleware checkpoint
    before receiving an already queued disconnect. A bounded receive allows those
    checkpoints without waiting indefinitely for a still-connected client.
    """
    if await request.is_disconnected():
        return True
    try:
        message = await asyncio.wait_for(request.receive(), timeout=0.05)
    except TimeoutError:
        return False
    return message["type"] == "http.disconnect"


@router.get("/capabilities")
def upload_capabilities(request: Request):
    return JSONResponse(capabilities(request.app.state.container.settings), headers=HEADERS)


@router.post("", status_code=201)
async def upload_file(request: Request, filename: str = Query(min_length=1, max_length=200)):
    same_origin(request)
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/octet-stream":
        raise HTTPException(415, detail="请以 application/octet-stream 上传原始 H5AD 文件")
    try:
        length = request.headers.get("content-length")
        if length is not None and (not length.isascii() or not length.isdecimal()):
            raise ValueError("无效的 Content-Length")

        async def is_disconnected():
            return await upload_client_disconnected(request)

        metadata = await receive_upload(
            request.app.state.container.settings,
            filename,
            request.stream(),
            int(length) if length is not None else None,
            is_disconnected=is_disconnected,
        )
        return JSONResponse(metadata, status_code=201, headers=HEADERS)
    except (ValueError, OSError, ImportError, RuntimeError, TimeoutError, TypeError, AttributeError) as exc:
        raise upload_error(exc) from exc
    except ClientDisconnect as exc:
        raise upload_error(exc) from exc


@router.get("/{upload_id}")
def upload_detail(upload_id: str, request: Request):
    try:
        return JSONResponse(get_upload(request.app.state.container.settings, upload_id), headers=HEADERS)
    except (KeyError, ValueError, OSError, ImportError, RuntimeError) as exc:
        raise upload_error(exc) from exc


@router.delete("/{upload_id}", status_code=204)
def remove_upload(upload_id: str, request: Request):
    same_origin(request)
    try:
        delete_upload(request.app.state.container.settings, upload_id)
        return Response(status_code=204, headers=HEADERS)
    except (KeyError, ValueError, OSError, ImportError, RuntimeError) as exc:
        raise upload_error(exc) from exc


@router.post("/{upload_id}/imports", status_code=201)
async def create_upload_import(upload_id: str, body: UploadImportRequest, request: Request):
    same_origin(request)
    try:
        imported = await _thread_complete(
            import_upload,
            request.app.state.container.settings,
            upload_id,
            body.model_dump(),
        )
        return JSONResponse(imported, status_code=201, headers=HEADERS)
    except (KeyError, ValueError, OSError, ImportError, CellLensError, RuntimeError) as exc:
        raise upload_error(exc) from exc
