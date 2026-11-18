"""Unified result reading, persistent findings and controlled measured intake."""

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.api.resources import same_origin
from backend.app.core.errors import CellLensError
from backend.app.services.controlled_import import capabilities, get_import, import_h5ad
from backend.app.services.h5ad_uploads import capabilities as upload_capabilities
from backend.app.services.research_findings import ResearchFindings
from backend.app.services.research_results import ResearchResults

router = APIRouter(prefix="/research", tags=["research"])
Kind = Literal["measured", "prediction"]
HEADERS = {"Cache-Control": "no-store"}


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gene_id: str | None = Field(default=None, min_length=1, max_length=500)
    task_id: str | None = Field(default=None, min_length=1, max_length=500)
    group_id: Literal["control", "predicted", "observed"] | None = None
    layer: Literal["expression", "function", "coverage", "structure"] | None = None
    projection_id: Literal["pca", "umap"] | None = None


class FindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_kind: Kind
    record_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    selection: Selection = Field(default_factory=Selection)
    note: str = Field("", max_length=4000)


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relative_path: str = Field(min_length=1, max_length=500)
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
        self.cell_line = self.cell_line.strip()
        if not self.cell_line:
            raise ValueError("细胞背景不能为空")
        if self.control_label == self.target_label or self.perturbation.lower() == "non-targeting":
            raise ValueError("目标扰动必须与对照条件不同")
        if self.expression_scale == "raw_counts" and not self.full_library and not self.total_counts_key:
            raise ValueError("raw_counts 需要完整基因矩阵声明或全库计数列")
        return self


def translate(exc):
    if isinstance(exc, KeyError):
        return HTTPException(404, detail="研究记录或导入版本不存在")
    if isinstance(exc, ImportError):
        return HTTPException(503, detail="所需科学分析依赖尚未安装")
    if isinstance(exc, OSError):
        return HTTPException(409, detail="研究文件不可用，请检查配置与文件权限")
    return HTTPException(409, detail=str(exc))


@router.get("/results/{record_kind}/{record_id}")
def result(record_kind: Kind, record_id: str, request: Request):
    try:
        return JSONResponse(
            ResearchResults(request.app.state.container).read(record_kind, record_id), headers=HEADERS
        )
    except (KeyError, ValueError, OSError) as exc:
        raise translate(exc) from exc


@router.get("/findings")
def findings(
    request: Request,
    record_kind: Kind | None = None,
    record_id: str | None = Query(None, max_length=80),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return JSONResponse(
        ResearchFindings(request.app.state.container).list(record_kind, record_id, limit, offset),
        headers=HEADERS,
    )


@router.get("/results/{record_kind}/{record_id}/projection")
def projection(
    record_kind: Kind, record_id: str, request: Request, embedding: Literal["pca", "umap"] = "pca"
):
    try:
        payload = ResearchResults(request.app.state.container).projection(record_kind, record_id, embedding)
        return JSONResponse(payload, headers=HEADERS)
    except (KeyError, ValueError, OSError, ImportError) as exc:
        raise translate(exc) from exc
    except (TypeError, AttributeError) as exc:
        raise HTTPException(409, detail="冻结表达投影文档结构不完整") from exc


@router.post("/findings", status_code=201)
def create_finding(body: FindingRequest, request: Request):
    same_origin(request)
    try:
        finding = ResearchFindings(request.app.state.container).create(
            body.record_kind, body.record_id, body.selection.model_dump(exclude_none=True), body.note
        )
        return JSONResponse(finding, status_code=201, headers=HEADERS)
    except (KeyError, ValueError, OSError) as exc:
        raise translate(exc) from exc


@router.get("/results/{record_kind}/{record_id}/export")
def export_result(record_kind: Kind, record_id: str, request: Request):
    container = request.app.state.container
    try:
        # Public exports never access the private annotation table, even for an allowlisted result.
        public = getattr(container.settings, "deployment_mode", "local") == "public"
        findings = [] if public else ResearchFindings(container).for_export(record_kind, record_id)
        payload = ResearchResults(container).export(record_kind, record_id, findings)
        if not isinstance(payload, dict) or not isinstance(result := payload.get("result"), dict):
            raise ValueError("研究导出缺少结果记录")
        provenance = result.get("provenance")
        if not isinstance(provenance, dict):
            raise ValueError("研究导出缺少来源记录")
        fingerprint = provenance.get("manifest_sha256")
        if not isinstance(fingerprint, str) or not fingerprint:
            raise ValueError("研究导出缺少清单指纹")
        return Response(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"),
            media_type="application/json",
            headers={
                **HEADERS,
                "Content-Disposition": f'attachment; filename="research-{record_id}.json"',
                "X-CellLens-Manifest-SHA256": fingerprint,
            },
        )
    except (KeyError, ValueError, OSError) as exc:
        raise translate(exc) from exc


@router.get("/imports/capabilities")
def import_capabilities(request: Request):
    return JSONResponse(capabilities(request.app.state.container.settings), headers=HEADERS)


@router.post("/imports", status_code=201)
async def create_import(body: ImportRequest, request: Request):
    same_origin(request)
    try:
        data = await asyncio.to_thread(import_h5ad, request.app.state.container.settings, body.model_dump())
        return JSONResponse(data, status_code=201, headers=HEADERS)
    except (KeyError, ValueError, OSError, ImportError, CellLensError, RuntimeError) as exc:
        raise translate(exc) from exc


@router.get("/imports/{import_id}")
def import_detail(import_id: str, request: Request):
    try:
        return JSONResponse(
            get_import(request.app.state.container.settings.project_root, import_id), headers=HEADERS
        )
    except (KeyError, ValueError, OSError) as exc:
        raise translate(exc) from exc


@router.post("/imports/{import_id}/analyses", status_code=202)
async def analyse_import(import_id: str, request: Request):
    same_origin(request)
    try:
        settings = request.app.state.container.settings
        if not (upload_capabilities(settings)["available"] or capabilities(settings)["available"]):
            raise ValueError("自有 H5AD 分析尚未启用")
        row = await request.app.state.measured.start({"import_id": import_id})
        return JSONResponse(row, status_code=202, headers=HEADERS)
    except (KeyError, ValueError, OSError, RuntimeError) as exc:
        raise translate(exc) from exc
