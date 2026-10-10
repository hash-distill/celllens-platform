import csv
import html
import json
import math
import random
import shutil
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError

from backend.app.core.cache import build_cache_key, code_fingerprint
from backend.app.core.diagnostic_protocol import load_diagnostic_protocol
from backend.app.core.errors import AssetNotReadyError, CellLensError, RegistryError
from backend.app.core.precomputed import load_bundle
from backend.app.core.projection import validate_projection
from backend.app.core.run_manifest import atomic_write_json, file_sha256, manifest_hash
from backend.app.schemas import (
    CompletenessResponse,
    CreateRunRequest,
    CreateRunResponse,
    RunListResponse,
    RunRecord,
    RunStatus,
    RunSummary,
    TaskTraceResponse,
)
from backend.app.services.cell_state import CellStateUnavailable, cell_state_document
from backend.app.services.cell_state_figure import render_cell_state
from backend.app.services.pipeline import _artifact_kind, _mime_type, _render_report

router = APIRouter(prefix="/runs", tags=["runs"])


def _cell_state(run_id: str, request: Request, feature_kind: str, feature_id: str) -> dict[str, Any]:
    # Check existence/status before reconstruction; no model inference or result mutation.
    get_run(run_id, request)
    if request.app.state.container.store.get(run_id).status != RunStatus.COMPLETED:
        raise HTTPException(status_code=409, detail={"code": "RUN_NOT_COMPLETED"})
    try:
        return cell_state_document(request.app.state.container, run_id, feature_kind, feature_id)
    except (CellStateUnavailable, CellLensError, OSError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=409, detail={"code": "CELL_STATE_UNAVAILABLE", "message": str(exc)}
        ) from exc
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "CELL_STATE_DEPENDENCY", "message": "Install model and report dependencies"},
        ) from exc


@router.get("/{run_id}/cell-state")
def get_cell_state(
    run_id: str,
    request: Request,
    feature_kind: Literal["gene", "task"] = "gene",
    feature_id: str = Query(default="", max_length=500),
) -> dict[str, Any]:
    return _cell_state(run_id, request, feature_kind, feature_id)


@router.get("/{run_id}/cell-state/figure")
def get_cell_state_figure(
    run_id: str,
    request: Request,
    feature_kind: Literal["gene", "task"] = "gene",
    feature_id: str = Query(default="", max_length=500),
    file_format: Literal["svg", "pdf", "png"] = "svg",
) -> Response:
    document = _cell_state(run_id, request, feature_kind, feature_id)
    try:
        content = render_cell_state(document, file_format)
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "CELL_STATE_DEPENDENCY", "message": "Install report dependencies"},
        ) from exc
    mime = {"svg": "image/svg+xml", "pdf": "application/pdf", "png": "image/png"}[file_format]
    return Response(
        content,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{run_id}_cell_state.{file_format}"',
            "X-CellLens-Manifest-SHA256": document["provenance"]["manifest_sha256"],
        },
    )


@router.get("", response_model=RunListResponse)
def list_runs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str = Query(default="", max_length=128),
    status: Literal["all", "active", "completed", "failed"] = "all",
    mode: Literal["online", "precomputed", "validation"] | None = None,
) -> RunListResponse:
    items, total = request.app.state.container.store.list_runs(
        limit=limit, offset=offset, query=q, status=status, mode=mode
    )
    return RunListResponse(
        items=[_record_source(item, request) for item in items], total=total, limit=limit, offset=offset
    )


@router.post("", response_model=CreateRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_run(payload: CreateRunRequest, request: Request) -> CreateRunResponse:
    container = request.app.state.container
    if payload.mode == "precomputed":
        return _create_precomputed_run(payload, container)

    try:
        model = container.registry.model_for(payload.cell_line)
        dataset = container.registry.dataset_for(payload.cell_line)
    except AssetNotReadyError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": str(exc)}) from exc
    except RegistryError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc
    supported = {str(item).upper() for item in model.payload.get("supported_perturbations", [])}
    if payload.perturbation not in supported:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "UNSUPPORTED_PERTURBATION",
                "message": f"{payload.perturbation} is not registered for {payload.cell_line}",
                "supported_alternatives": sorted(supported)[:20],
            },
        )
    if payload.mode == "validation":
        try:
            protocol = load_diagnostic_protocol(dataset, model)
            if payload.perturbation not in protocol["perturbations"]:
                raise ValueError("This perturbation has no registered measured diagnostic")
        except (OSError, ValueError, RegistryError) as exc:
            raise HTTPException(
                status_code=422, detail={"code": "DIAGNOSTIC_UNAVAILABLE", "message": str(exc)}
            ) from exc
    if not container.settings.worker_enabled:
        raise HTTPException(
            status_code=503,
            detail={"code": "WORKER_UNAVAILABLE", "message": "The analysis worker is disabled"},
        )
    if not container.settings.gpu_available:
        raise HTTPException(
            status_code=503,
            detail={"code": "GPU_UNAVAILABLE", "message": "STATE inference is disabled on this host"},
        )
    try:
        asset_hashes = {
            "model_contract_sha256": manifest_hash(model.payload),
            "dataset_contract_sha256": manifest_hash(dataset.payload),
            "checkpoint_sha256": container.registry.verify_entry(
                model, "checkpoint_path", "checkpoint_sha256"
            ),
            "control_sha256": container.registry.verify_entry(dataset, "control_path", "control_sha256"),
        }
        for entry, path_field, hash_field in (
            (model, "gene_list_path", "gene_list_sha256"),
            (model, "config_path", "config_sha256"),
            (dataset, "split_path", "split_sha256"),
        ):
            if entry.payload.get(path_field):
                asset_hashes[hash_field] = container.registry.verify_entry(entry, path_field, hash_field)
        if payload.mode == "validation":
            asset_hashes["validation_protocol_sha256"] = container.registry.verify_entry(
                dataset, "validation_protocol_path", "validation_protocol_sha256"
            )
            asset_hashes["observed_sha256"] = container.registry.verify_entry(
                dataset, "observed_path", "observed_sha256"
            )
    except (AssetNotReadyError, RegistryError) as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": str(exc)}) from exc

    database_manifest = container.settings.sccellfie_database_root / "manifest.json"
    identity_manifest = container.settings.gene_identity_root / "manifest.json"
    if identity_manifest.is_file():
        asset_hashes["gene_identity_manifest_sha256"] = file_sha256(identity_manifest)
        asset_hashes["gene_identity_mapping_sha256"] = file_sha256(identity_manifest.parent / "human.json")
    cache_key = build_cache_key(
        payload,
        asset_hashes,
        code_hash=code_fingerprint(container.settings.project_root),
        database_hash=file_sha256(database_manifest) if database_manifest.is_file() else None,
    )
    if cached_run_id := container.store.get_cached_run(cache_key):
        cached = container.store.get(cached_run_id)
        try:
            validate_projection(container.settings.derived_root / cached_run_id / "projection.json")
        except (OSError, ValueError):
            pass  # An incomplete cached run must not bypass the completion contract.
        else:
            return CreateRunResponse(run_id=cached.run_id, status=cached.status, cache_hit=True)

    run_id = container.pipeline.allocate_run_id()
    record = container.store.create(run_id, payload, cache_key=cache_key)
    await container.queue.submit(run_id)
    return CreateRunResponse(run_id=record.run_id, status=record.status, cache_hit=False)


def _create_precomputed_run(payload: CreateRunRequest, container: Any) -> CreateRunResponse:
    source = container.settings.demo_root / payload.cell_line / payload.perturbation
    summary_source = source / "summary.json"
    source_manifest = source / "manifest.json"
    if not summary_source.is_file() or not source_manifest.is_file():
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PRECOMPUTED_NOT_FOUND",
                "message": f"No precomputed result for {payload.cell_line}/{payload.perturbation}",
            },
        )
    try:
        template, manifest = load_bundle(source, payload.cell_line, payload.perturbation)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "INVALID_PRECOMPUTED_RESULT", "message": str(exc)},
        ) from exc
    if template.result_kind != "frozen_model_result" and not container.settings.allow_synthetic_results:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "SYNTHETIC_RESULT_DISABLED",
                "message": "Result replay requires saved real model results",
            },
        )
    run_id = container.pipeline.allocate_run_id()
    container.store.create(run_id, payload)
    destination = container.settings.derived_root / run_id
    destination.mkdir(parents=True, exist_ok=False)
    for relative_name in manifest["files"]:
        if relative_name in {"summary.json", "manifest.json"}:
            continue
        target = destination / relative_name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative_name, target)
    summary = template.model_copy(update={"run_id": run_id})
    frozen = summary.result_kind == "frozen_model_result"
    if frozen:
        for name in ("task_trace.json", "official_completeness.json", "expression_contract.json"):
            path = destination / name
            document = _json_artifact(path)
            document["run_id"] = run_id
            atomic_write_json(path, document)
        report = _render_report(summary)
        notice = (
            "<aside><strong>真实结果回放（本次未重新计算）</strong>"
            f"<p>原始运行：{html.escape(str(manifest['source_run_id']))}。"
            "实测比较属于样本诊断，尚未核实训练排除，不能视为独立留出验收。</p></aside>"
        )
        (destination / "report.html").write_text(
            report.replace("<body>", "<body>" + notice, 1), encoding="utf-8"
        )
    atomic_write_json(destination / "summary.json", summary.model_dump(mode="json"))
    atomic_write_json(
        destination / "manifest.json",
        {
            "request": payload.model_dump(mode="json"),
            "source": str(source.relative_to(container.settings.project_root)),
            "source_type": "frozen_precomputed" if frozen else "synthetic_precomputed",
            "source_run_id": manifest.get("source_run_id"),
            "original_manifest_sha256": manifest.get("source_manifest_sha256") if frozen else None,
            "source_manifest_sha256": file_sha256(source_manifest),
            "bundle_files": manifest["files"],
            "assets": _json_artifact(destination / "source_manifest.json").get("assets", {})
            if frozen
            else {},
            "outputs": {
                p.name: {"sha256": file_sha256(p), "size_bytes": p.stat().st_size}
                for p in destination.iterdir()
                if p.is_file()
            },
        },
    )
    validate_projection(destination / "projection.json")
    for path in destination.iterdir():
        if not path.is_file():
            continue
        container.store.register_artifact(
            run_id,
            _artifact_kind(path),
            str(path.relative_to(container.settings.project_root)),
            file_sha256(path),
            path.stat().st_size,
            _mime_type(path),
        )
    record = container.store.transition(
        run_id,
        RunStatus.COMPLETED,
        100,
        warnings=summary.warnings,
        message="precomputed result with required single-cell projection materialized",
    )
    return CreateRunResponse(run_id=run_id, status=record.status, cache_hit=False)


@router.get("/{run_id}", response_model=RunRecord)
def get_run(run_id: str, request: Request) -> RunRecord:
    try:
        return _record_source(request.app.state.container.store.get(run_id), request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"}) from exc


def _record_source(record: RunRecord, request: Request) -> RunRecord:
    if record.request.mode == "precomputed":
        path = request.app.state.container.settings.derived_root / record.run_id / "summary.json"
        if path.is_file():
            record.result_kind = (
                RunSummary.model_validate(_json_artifact(path)).result_kind or "synthetic_demo"
            )
    return record


@router.get("/{run_id}/summary", response_model=RunSummary)
def get_summary(run_id: str, request: Request) -> RunSummary:
    container = request.app.state.container
    try:
        record = container.store.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"}) from exc
    summary_path: Path = container.settings.derived_root / run_id / "summary.json"
    if not summary_path.is_file():
        return RunSummary(
            run_id=run_id,
            status=record.status,
            stage_progress=record.stage_progress,
            cell_line=record.request.cell_line,
            perturbation=record.request.perturbation,
            warnings=record.warnings,
            error_code=record.error_code,
        )
    summary = RunSummary.model_validate(json.loads(summary_path.read_text(encoding="utf-8")))
    if (
        record.request.mode != "precomputed"
        and not (summary_path.parent / "expression_contract.json").is_file()
    ):
        summary.warnings.append("历史分析结果尚未按 expression-cp10k-v2 重算；请使用对应的新版本运行。")
    return summary


@router.get("/{run_id}/projection")
def get_projection(run_id: str, request: Request) -> dict[str, Any]:
    path = _artifact_path(run_id, "projection.json", request)
    document = json.loads(path.read_text(encoding="utf-8"))
    points = document.get("points", [])
    if not isinstance(points, list):
        raise HTTPException(status_code=500, detail={"code": "INVALID_ARTIFACT"})
    budget = request.app.state.container.settings.max_projection_points
    if len(points) > budget:
        document["points"] = _stratified_points(points, budget, int(document.get("seed", 0)))
    return document


@router.get("/{run_id}/genes")
def get_genes(
    run_id: str,
    request: Request,
    limit: int = Query(default=2000, ge=1, le=10_000),
) -> dict[str, Any]:
    return _csv_artifact(run_id, "gene_deltas.csv", request, limit)


@router.get("/{run_id}/completeness", response_model=CompletenessResponse)
def get_completeness(run_id: str, request: Request) -> CompletenessResponse:
    path = _artifact_path(run_id, "official_completeness.json", request)
    container = request.app.state.container
    registered = [item for item in container.store.artifacts(run_id) if item.kind == "official_completeness"]
    try:
        if len(registered) != 1 or registered[0].sha256 != file_sha256(path):
            raise ValueError("Completeness artifact is not registered or has changed")
        document = CompletenessResponse.model_validate(_json_artifact(path))
        genes = _artifact_path(run_id, "gene_deltas.csv", request)
        if document.run_id != run_id or document.source_gene_sha256 != file_sha256(genes):
            raise ValueError("Completeness does not match the run gene panel")
        return document
    except (OSError, ValueError, ValidationError) as exc:
        raise HTTPException(status_code=500, detail={"code": "INVALID_COMPLETENESS"}) from exc


@router.get("/{run_id}/metabolic-tasks")
def get_metabolic_tasks(
    run_id: str,
    request: Request,
    limit: int = Query(default=1000, ge=1, le=10_000),
    scope: Literal["top", "all"] = "top",
) -> dict[str, Any]:
    if scope == "all":
        root = request.app.state.container.settings.derived_root / run_id
        if (root / "metabolic_task_scores.csv").is_file() and (root / "metabolic_coverage.csv").is_file():
            scores_path = _artifact_path(run_id, "metabolic_task_scores.csv", request)
            coverage_path = _artifact_path(run_id, "metabolic_coverage.csv", request)
            try:
                import pandas as pd

                scores = pd.read_csv(scores_path, index_col=0)
                coverage = pd.read_csv(coverage_path, index_col=0)
                # Legacy demo CSVs use task/source/score rows and separate labels;
                # their validated summary is the supported display contract.
                if (
                    scores.index.name == "task"
                    and {"source", "score"}.issubset(scores.columns)
                    and get_run(run_id, request).request.mode == "precomputed"
                ):
                    return _top_metabolic_tasks(run_id, request, limit)
                numeric = scores.drop(columns=["source"]).apply(pd.to_numeric, errors="coerce")
                grouped = numeric.groupby(scores["source"], observed=True).mean()
                delta = grouped.loc["predicted"] - grouped.loc["control"]
                trace_tasks = _optional_trace_tasks(run_id, request)
                items = []
                for task in delta.abs().sort_values(ascending=False).index:
                    value = float(delta[task])
                    if not math.isfinite(value):
                        continue
                    observed = (
                        float(grouped.loc["observed", task] - grouped.loc["control", task])
                        if "observed" in grouped.index
                        else None
                    )
                    entry = coverage.loc[str(task)]
                    items.append(
                        {
                            "id": str(task),
                            "label": (trace_tasks or {}).get(str(task), {}).get("label", str(task)),
                            "category": (trace_tasks or {}).get(str(task), {}).get("category"),
                            "subcategory": (trace_tasks or {}).get(str(task), {}).get("subcategory"),
                            "trace_available": str(task) in trace_tasks if trace_tasks is not None else None,
                            "control": float(grouped.loc["control", task]),
                            "predicted": float(grouped.loc["predicted", task]),
                            "predicted_delta": value,
                            "observed_delta": observed
                            if observed is not None and math.isfinite(observed)
                            else None,
                            "coverage": float(entry["gene_fraction"]),
                            "evidence_level": str(entry["evidence_level"]),
                            "determinant_genes": [],
                        }
                    )
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise HTTPException(status_code=500, detail={"code": "INVALID_ARTIFACT"}) from exc
            return {
                "items": items[:limit],
                "limit": limit,
                "truncated": len(items) > limit,
                "total": len(items),
                "scope": "all",
                "excluded_count": len(delta) - len(items),
                "reactions_available": (root / "reaction_scores.csv").is_file(),
                "completeness_available": (root / "official_completeness.json").is_file(),
            }
    return _top_metabolic_tasks(run_id, request, limit)


def _top_metabolic_tasks(run_id: str, request: Request, limit: int) -> dict[str, Any]:
    summary = get_summary(run_id, request)
    items = [item.model_dump(mode="json") for item in summary.metabolic_tasks[:limit]]
    trace_tasks = _optional_trace_tasks(run_id, request)
    for item in items:
        item["trace_available"] = item["id"] in trace_tasks if trace_tasks is not None else None
    root = request.app.state.container.settings.derived_root / run_id
    return {
        "items": items,
        "limit": limit,
        "truncated": len(summary.metabolic_tasks) > limit,
        "total": len(summary.metabolic_tasks),
        "scope": "top",
        "reactions_available": (root / "reaction_scores.csv").is_file(),
        "completeness_available": (root / "official_completeness.json").is_file(),
    }


def _optional_trace_tasks(run_id: str, request: Request) -> dict[str, Any] | None:
    """Missing traces are known unavailable; invalid traces retain an explicit error path."""
    try:
        return _load_task_trace(run_id, request)["tasks"]
    except HTTPException as exc:
        if isinstance(exc.detail, dict) and exc.detail.get("code") == "TASK_TRACE_UNAVAILABLE":
            return {}
        # Optional labels must not hide independently valid score files. None tells
        # clients to try the trace endpoint, which still rejects untrusted artifacts.
        return None


def _load_task_trace(run_id: str, request: Request) -> dict[str, Any]:
    try:
        path = _artifact_path(run_id, "task_trace.json", request)
    except HTTPException as exc:
        if (
            exc.status_code == 404
            and isinstance(exc.detail, dict)
            and exc.detail.get("code") == "ARTIFACT_NOT_FOUND"
        ):
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "TASK_TRACE_UNAVAILABLE",
                    "message": "This run has no frozen task trace; a new analysis is required.",
                },
            ) from exc
        raise
    container = request.app.state.container
    root = (container.settings.derived_root / run_id).resolve()
    registered = [item for item in container.store.artifacts(run_id) if item.kind == "task_trace"]
    if not path.is_relative_to(root) or len(registered) != 1 or registered[0].sha256 != file_sha256(path):
        raise HTTPException(status_code=500, detail={"code": "INVALID_TASK_TRACE"})
    document = _json_artifact(path)
    if (
        document.get("run_id") != run_id
        or document.get("schema_version") != 1
        or not isinstance(document.get("tasks"), dict)
        or not isinstance(document.get("reactions"), dict)
        or not isinstance(document.get("genes"), dict)
    ):
        raise HTTPException(status_code=500, detail={"code": "INVALID_TASK_TRACE"})
    return document


@router.get("/{run_id}/task-trace", response_model=TaskTraceResponse)
def get_task_trace(
    run_id: str,
    request: Request,
    task_id: str = Query(min_length=1, max_length=512),
    reaction_limit: int = Query(default=30, ge=1, le=100),
    gene_limit: int = Query(default=30, ge=1, le=100),
    scope: Literal["top", "all"] = "top",
) -> TaskTraceResponse:
    document = _load_task_trace(run_id, request)
    if task_id not in document["tasks"]:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND"})
    try:
        task = dict(document["tasks"][task_id])
        reaction_ids = task.pop("reaction_ids")
        reactions = []
        for reaction_id in reaction_ids if scope == "all" else reaction_ids[:reaction_limit]:
            reaction = dict(document["reactions"][reaction_id])
            gene_ids = reaction.pop("gene_ids")
            reaction.update(
                {
                    "genes": [
                        document["genes"][gene]
                        for gene in (gene_ids if scope == "all" else gene_ids[:gene_limit])
                    ],
                    "total_genes": len(gene_ids),
                    "truncated": scope != "all" and len(gene_ids) > gene_limit,
                }
            )
            reactions.append(reaction)
        result = {key: value for key, value in document.items() if key not in {"tasks", "reactions", "genes"}}
        result.update(
            {
                "task": task,
                "scope": scope,
                "reactions": reactions,
                "total_reactions": len(reaction_ids),
                "truncated": scope != "all" and len(reaction_ids) > reaction_limit,
            }
        )
        return TaskTraceResponse.model_validate(result)
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise HTTPException(status_code=500, detail={"code": "INVALID_TASK_TRACE"}) from exc


@router.get("/{run_id}/reactions")
def get_reactions(
    run_id: str,
    request: Request,
    limit: int = Query(default=1000, ge=1, le=10_000),
) -> dict[str, Any]:
    path = _artifact_path(run_id, "reaction_scores.csv", request)
    try:
        import pandas as pd

        table = pd.read_csv(path, index_col=0)
        if "source" not in table:
            return _csv_artifact(run_id, "reaction_scores.csv", request, min(limit, 100))
        sources = table.pop("source")
        numeric = table.apply(pd.to_numeric, errors="coerce")
        grouped = numeric.groupby(sources, observed=True).mean()
        if "control" not in grouped.index or "predicted" not in grouped.index:
            raise ValueError("reaction scores lack control or predicted sources")
        delta = grouped.loc["predicted"] - grouped.loc["control"]
        selected = delta.abs().nlargest(limit).index
        items = [
            {
                "reaction": str(reaction),
                "control": float(grouped.loc["control", reaction]),
                "predicted": float(grouped.loc["predicted", reaction]),
                "predicted_delta": float(delta[reaction]),
            }
            for reaction in selected
        ]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "INVALID_ARTIFACT", "message": str(exc)},
        ) from exc
    return {"items": items, "limit": limit, "truncated": len(delta) > limit}


@router.get("/{run_id}/report", response_class=FileResponse)
def get_report(run_id: str, request: Request) -> FileResponse:
    path = _artifact_path(run_id, "report.html", request)
    return FileResponse(path, media_type="text/html", filename=f"celllens-{run_id}.html")


@router.get("/{run_id}/provenance")
def get_provenance(run_id: str, request: Request) -> dict[str, Any]:
    path = _artifact_path(run_id, "manifest.json", request)
    document = _json_artifact(path)
    record = request.app.state.container.store.get(run_id)
    allowed_assets = {
        "model_id",
        "dataset_id",
        "checkpoint_sha256",
        "gene_list_sha256",
        "config_sha256",
        "control_sha256",
        "observed_sha256",
        "split_sha256",
        "model_expression_scale",
        "dataset_expression_scale",
        "validation_protocol_sha256",
    }
    assets = document.get("assets", {})
    return {
        "run_id": run_id,
        "source_type": document.get("source_type", "synthetic_precomputed")
        if record.request.mode == "precomputed"
        else record.request.mode,
        "source_run_id": document.get("source_run_id"),
        "original_manifest_sha256": document.get("original_manifest_sha256"),
        "created_at": record.created_at.isoformat(),
        "completed_at": record.updated_at.isoformat(),
        "manifest_sha256": file_sha256(path),
        "code_sha256": document.get("code_sha256"),
        "source_manifest_sha256": document.get("source_manifest_sha256"),
        "prediction_reused": document.get("prediction_reused", False),
        "reanalysis_of": document.get("reanalysis_of"),
        "analysis_script_sha256": document.get("analysis_script_sha256"),
        "assets": {key: value for key, value in assets.items() if key in allowed_assets}
        if isinstance(assets, dict)
        else {},
    }


@router.get("/{run_id}/validation")
def get_validation(run_id: str, request: Request) -> dict[str, Any]:
    path = _artifact_path(run_id, "validation_metrics.json", request)
    document = _json_artifact(path)
    keys = (
        "spearman",
        "mae",
        "direction_agreement",
        "top_k_overlap",
        "valid_task_count",
        "excluded_task_count",
    )
    return {
        "run_id": run_id,
        "metrics": {key: document.get(key) for key in keys},
        "metric_scope": "metabolic_task_delta",
        "expression": document.get("expression"),
        "differential_expression": document.get("differential_expression"),
        "parameters": document.get("parameters"),
        "held_out_validation": document.get("held_out_validation", False),
        "protocol_status": document.get("protocol_status", "unconfirmed"),
        "warnings": document.get(
            "warnings",
            ["Matched observations alone do not establish an approved validation split or protocol."],
        ),
    }


def _json_artifact(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("JSON artifact must contain an object")
        return document
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail={"code": "INVALID_ARTIFACT"}) from exc


def _artifact_path(run_id: str, filename: str, request: Request) -> Path:
    container = request.app.state.container
    try:
        record = container.store.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"}) from exc
    if record.status != RunStatus.COMPLETED:
        raise HTTPException(status_code=409, detail={"code": "RUN_NOT_COMPLETED"})
    path = (container.settings.derived_root / run_id / filename).resolve()
    root = container.settings.derived_root.resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail={"code": "ARTIFACT_NOT_FOUND"})
    return path


def _csv_artifact(run_id: str, filename: str, request: Request, limit: int) -> dict[str, Any]:
    path = _artifact_path(run_id, filename, request)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        items = []
        truncated = False
        for index, row in enumerate(reader):
            if index >= limit:
                truncated = True
                break
            items.append(dict(row))
    return {"items": items, "limit": limit, "truncated": truncated}


def _stratified_points(points: list[dict[str, Any]], budget: int, seed: int) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for point in points:
        groups.setdefault(str(point.get("source", "unknown")), []).append(point)
    rng = random.Random(seed)
    selected: list[dict[str, Any]] = []
    remaining = budget
    for index, key in enumerate(sorted(groups)):
        group = groups[key]
        slots = remaining if index == len(groups) - 1 else max(1, round(budget * len(group) / len(points)))
        take = min(slots, len(group), remaining)
        selected.extend(rng.sample(group, take) if take < len(group) else group)
        remaining -= take
    return selected[:budget]
