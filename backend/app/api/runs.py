import csv
import json
import math
import random
import shutil
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from backend.app.core.cache import build_cache_key, code_fingerprint
from backend.app.core.errors import AssetNotReadyError, RegistryError
from backend.app.core.precomputed import load_bundle
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.schemas import CreateRunRequest, CreateRunResponse, RunRecord, RunStatus, RunSummary

router = APIRouter(prefix="/runs", tags=["runs"])


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
            asset_hashes["observed_sha256"] = container.registry.verify_entry(
                dataset, "observed_path", "observed_sha256"
            )
    except (AssetNotReadyError, RegistryError) as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": str(exc)}) from exc

    database_manifest = container.settings.sccellfie_database_root / "manifest.json"
    cache_key = build_cache_key(
        payload,
        asset_hashes,
        code_hash=code_fingerprint(container.settings.project_root),
        database_hash=file_sha256(database_manifest) if database_manifest.is_file() else None,
    )
    if cached_run_id := container.store.get_cached_run(cache_key):
        cached = container.store.get(cached_run_id)
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
    atomic_write_json(destination / "summary.json", summary.model_dump(mode="json"))
    atomic_write_json(
        destination / "manifest.json",
        {
            "request": payload.model_dump(mode="json"),
            "source": str(source.relative_to(container.settings.project_root)),
            "source_type": "synthetic_precomputed",
            "source_manifest_sha256": file_sha256(source_manifest),
            "bundle_files": manifest["files"],
        },
    )
    record = container.store.transition(
        run_id,
        RunStatus.COMPLETED,
        100,
        warnings=summary.warnings,
        message="precomputed result materialized",
    )
    for kind, filename in (("summary", "summary.json"), ("manifest", "manifest.json")):
        path = destination / filename
        container.store.register_artifact(
            run_id,
            kind,
            str(path.relative_to(container.settings.project_root)),
            file_sha256(path),
            path.stat().st_size,
            "application/json",
        )
    return CreateRunResponse(run_id=run_id, status=record.status, cache_hit=False)


@router.get("/{run_id}", response_model=RunRecord)
def get_run(run_id: str, request: Request) -> RunRecord:
    try:
        return request.app.state.container.store.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"}) from exc


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
    return RunSummary.model_validate(json.loads(summary_path.read_text(encoding="utf-8")))


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
                numeric = scores.drop(columns=["source"]).apply(pd.to_numeric, errors="coerce")
                grouped = numeric.groupby(scores["source"], observed=True).mean()
                delta = grouped.loc["predicted"] - grouped.loc["control"]
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
                            "label": str(task),
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
            }
    summary = get_summary(run_id, request)
    items = [item.model_dump(mode="json") for item in summary.metabolic_tasks[:limit]]
    return {
        "items": items,
        "limit": limit,
        "truncated": len(summary.metabolic_tasks) > limit,
        "total": len(summary.metabolic_tasks),
        "scope": "top",
    }


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
    }
    assets = document.get("assets", {})
    return {
        "run_id": run_id,
        "source_type": "synthetic_precomputed"
        if record.request.mode == "precomputed"
        else record.request.mode,
        "created_at": record.created_at.isoformat(),
        "completed_at": record.updated_at.isoformat(),
        "manifest_sha256": file_sha256(path),
        "code_sha256": document.get("code_sha256"),
        "source_manifest_sha256": document.get("source_manifest_sha256"),
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
        "protocol_status": "unconfirmed",
        "warnings": ["Matched observations alone do not establish an approved validation split or protocol."],
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
