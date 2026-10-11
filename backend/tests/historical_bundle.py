"""Fixture importer for historical bundles; no application route imports this module."""

import html
import shutil
from typing import Any

from fastapi import HTTPException

from backend.app.api.runs import _json_artifact
from backend.app.core.precomputed import load_bundle
from backend.app.core.projection import validate_projection
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.schemas import CreateRunRequest, CreateRunResponse, RunStatus
from backend.app.services.pipeline import _artifact_kind, _mime_type, _render_report


def _create_precomputed_run(payload: CreateRunRequest, container: Any) -> CreateRunResponse:
    """Seed historical records for read-only compatibility tests, bypassing new-run HTTP."""
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
