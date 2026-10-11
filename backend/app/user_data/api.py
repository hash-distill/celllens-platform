import importlib.util
import json
import logging
import uuid
from pathlib import Path
from typing import Annotated, NoReturn

from fastapi import APIRouter, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError

from backend.app.core.errors import ScientificContractError
from backend.app.core.run_manifest import file_sha256
from backend.app.user_data.datasets import inspect_hdf5, read_expression, state_compatibility
from backend.app.user_data.schemas import AnalysisRequest, UploadMetadata

router = APIRouter(tags=["user data"])
logger = logging.getLogger(__name__)


def fail(status: int, code: str, message: str) -> NoReturn:
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


@router.get("/data-capabilities")
def capabilities(request: Request) -> dict:
    settings = request.app.state.container.settings
    expression_ready = all(
        importlib.util.find_spec(package) is not None for package in ("anndata", "h5py", "scipy", "sklearn")
    )
    metabolic_ready = (
        expression_ready
        and importlib.util.find_spec("sccellfie") is not None
        and (settings.sccellfie_database_root / "manifest.json").is_file()
    )
    if metabolic_ready:
        try:
            root = settings.sccellfie_database_root.resolve()
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            required = {
                "Rxn-Info-Recon2-2.json",
                "Task-Info.csv",
                "Task_by_Rxn.csv",
                "Task_by_Gene.csv",
                "Rxn_by_Gene.csv",
                "Thresholds.csv",
            }
            metabolic_ready = bool(manifest.get("enabled") and required.issubset(manifest.get("files", {})))
            if metabolic_ready:
                for filename, digest in manifest["files"].items():
                    path = (root / filename).resolve()
                    if not path.is_relative_to(root) or not path.is_file() or file_sha256(path) != digest:
                        metabolic_ready = False
                        break
        except (OSError, ValueError, TypeError):
            metabolic_ready = False
    return {
        "worker_enabled": settings.data_worker_enabled,
        "expression_ready": expression_ready,
        "metabolism_ready": metabolic_ready,
        "formats": ["h5ad"],
        "organisms": ["human"],
        "tasks": ["explore", "metabolism"],
        "max_upload_bytes": settings.max_upload_bytes,
        "max_workspace_storage_bytes": settings.max_workspace_storage_bytes,
        "max_cells": settings.max_dataset_cells,
        "max_genes": settings.max_dataset_genes,
        "max_matrix_values": settings.max_matrix_values,
        "state_user_prediction_enabled": False,
        "access_mode": "shared_workspace",
        "max_pending_analyses": 3,
    }


def require_dataset(request: Request, dataset_id: str) -> dict:
    dataset = request.app.state.container.user_store.dataset(dataset_id, None)
    if dataset is None:
        fail(404, "DATASET_NOT_FOUND", "数据集不存在")
    return dataset


def require_analysis(request: Request, analysis_id: str) -> dict:
    analysis = request.app.state.container.user_store.analysis(analysis_id, None)
    if analysis is None:
        fail(404, "ANALYSIS_NOT_FOUND", "分析任务不存在")
    return analysis


@router.get("/datasets")
def datasets(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1_000_000),
    q: str = Query("", max_length=128),
) -> dict:
    return request.app.state.container.user_store.datasets(None, limit, offset, q)


@router.post("/datasets", status_code=201)
def upload_dataset(
    request: Request, file: UploadFile, metadata: Annotated[str, Form(max_length=5000)]
) -> dict:
    container = request.app.state.container
    settings = container.settings
    if not capabilities(request)["expression_ready"]:
        fail(503, "DEPENDENCIES_UNAVAILABLE", "请管理员安装 model 和 report 科学分析依赖")
    path: Path | None = None
    try:
        try:
            options = UploadMetadata.model_validate_json(metadata)
        except ValidationError:
            fail(422, "INVALID_METADATA", "请检查名称、表达尺度、矩阵来源和文库范围")
        filename = (file.filename or "").replace("\\", "/").split("/")[-1][:255]
        if not filename.lower().endswith(".h5ad"):
            fail(422, "INVALID_FORMAT", "仅支持 H5AD 文件")
        # Serialize shared uploads and storage quota checks across processes.
        with container.store.named_lock("celllens:upload:shared", timeout_seconds=10):
            used = container.user_store.used_bytes(None)
            settings.user_data_root.mkdir(parents=True, exist_ok=True)
            dataset_id = "ds_" + uuid.uuid4().hex
            source_path: Path = settings.user_data_root / (dataset_id + ".h5ad")
            path = source_path
            size = 0
            with source_path.open("xb") as target:
                while chunk := file.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.max_upload_bytes:
                        fail(413, "UPLOAD_TOO_LARGE", "文件超过上传大小上限")
                    if used + size > settings.max_workspace_storage_bytes:
                        fail(413, "STORAGE_QUOTA_EXCEEDED", "工作区源文件存储配额不足，请联系管理员")
                    target.write(chunk)
            inspect_hdf5(source_path, options, settings)
            data, summary = read_expression(source_path, options)
            summary["state_compatibility"] = state_compatibility(data, options, container.registry)
            result = container.user_store.add_dataset(
                owner_id=None,
                dataset_id=dataset_id,
                metadata=options.model_dump(),
                summary=summary,
                sha256=file_sha256(source_path),
                size_bytes=size,
                filename=filename,
            )
            path = None
            return result
    except HTTPException:
        raise
    except (ValueError, OSError, KeyError, TypeError, ScientificContractError) as exc:
        logger.info("User dataset validation rejected: %s", exc)
        fail(422, "INVALID_DATASET", f"数据校验失败：{str(exc)[:400]}")
    finally:
        file.file.close()
        if path is not None:
            path.unlink(missing_ok=True)


@router.get("/datasets/{dataset_id}")
def dataset_detail(dataset_id: str, request: Request) -> dict:
    return require_dataset(request, dataset_id)


@router.post("/datasets/{dataset_id}/archive")
def archive_dataset(dataset_id: str, request: Request) -> dict:
    require_dataset(request, dataset_id)
    request.app.state.container.user_store.archive(dataset_id, None)
    return require_dataset(request, dataset_id)


@router.get("/datasets/{dataset_id}/file")
def download_dataset(dataset_id: str, request: Request) -> FileResponse:
    dataset = require_dataset(request, dataset_id)
    path = request.app.state.container.settings.user_data_root / (dataset["id"] + ".h5ad")
    if not path.is_file() or file_sha256(path) != dataset["sha256"]:
        fail(409, "SOURCE_UNAVAILABLE", "源数据缺失或 SHA-256 校验失败")
    return FileResponse(
        path,
        filename=dataset["filename"],
        media_type="application/octet-stream",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/analyses")
def analyses(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1_000_000),
    dataset_id: str | None = Query(None, pattern=r"^ds_[a-f0-9]{32}$"),
    status: str | None = Query(None, pattern=r"^(queued|running|completed|failed)$"),
) -> dict:
    return request.app.state.container.user_store.analyses(None, limit, offset, dataset_id, status)


@router.post("/analyses", status_code=202)
def create_analysis(body: AnalysisRequest, request: Request) -> dict:
    dataset = require_dataset(request, body.dataset_id)
    if dataset["archived"]:
        fail(409, "DATASET_ARCHIVED", "数据集已归档；既有结果可以复查，不能再创建新任务")
    choices = dataset["summary"]["group_columns"]
    if body.group_key and body.group_key not in choices:
        fail(422, "INVALID_GROUP", "请选择完整、具有 2–40 个取值的 obs 分组列")
    if body.reference_group and (not body.group_key or body.reference_group not in choices[body.group_key]):
        fail(422, "INVALID_REFERENCE", "参考组不存在")
    ready = capabilities(request)
    if not ready["worker_enabled"]:
        fail(503, "DATA_WORKER_UNAVAILABLE", "请管理员启用 CPU 分析服务 CELLLENS_DATA_WORKER_ENABLED")
    if not ready["expression_ready"] or (body.kind == "metabolism" and not ready["metabolism_ready"]):
        fail(503, "ANALYSIS_UNAVAILABLE", "分析依赖或冻结 scCellFie 数据库未就绪")
    try:
        parameters = body.model_dump()
        parameters["name"] = (
            body.name or f"{dataset['name']} · {'代谢分析' if body.kind == 'metabolism' else '表达探索'}"
        )
        return request.app.state.container.user_store.create_analysis(None, parameters)
    except ScientificContractError as exc:
        fail(409, "DATASET_UNAVAILABLE", str(exc))
    except ValueError as exc:
        fail(429, "ANALYSIS_QUOTA", str(exc))


@router.get("/analyses/{analysis_id}")
def analysis_detail(analysis_id: str, request: Request) -> dict:
    return require_analysis(request, analysis_id)


def artifact_path(request: Request, analysis: dict, filename: str) -> Path:
    if analysis["status"] != "completed":
        fail(409, "RESULT_NOT_READY", "分析结果尚未生成")
    artifact = analysis["artifacts"].get(filename)
    if artifact is None:
        fail(404, "ARTIFACT_NOT_FOUND", "结果文件不存在")
    root = request.app.state.container.settings.user_analysis_root / analysis["id"]
    path = (root / filename).resolve()
    if (
        not path.is_relative_to(root.resolve())
        or not path.is_file()
        or file_sha256(path) != artifact["sha256"]
    ):
        fail(409, "ARTIFACT_CORRUPTED", "结果文件缺失或 SHA-256 校验失败")
    return path


@router.get("/analyses/{analysis_id}/report")
def analysis_report(analysis_id: str, request: Request, response: Response) -> dict:
    analysis = require_analysis(request, analysis_id)
    response.headers["Cache-Control"] = "no-store"
    return json.loads(artifact_path(request, analysis, "report.json").read_text(encoding="utf-8"))


@router.get("/analyses/{analysis_id}/files/{filename}")
def analysis_file(analysis_id: str, filename: str, request: Request) -> FileResponse:
    analysis = require_analysis(request, analysis_id)
    path = artifact_path(request, analysis, filename)
    return FileResponse(
        path,
        filename=filename,
        media_type="application/json" if filename.endswith(".json") else "text/csv",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
