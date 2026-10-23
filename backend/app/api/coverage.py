"""Read-only coverage catalogue for current models or a saved input panel."""

import csv
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from backend.app.api.runs import _artifact_path, get_completeness, get_provenance
from backend.app.core.errors import CellLensError
from backend.app.core.run_manifest import file_sha256
from backend.app.services.catalog_snapshot import model_catalog_response
from backend.app.services.coverage_catalog import cached_completeness, coverage_catalog
from backend.app.services.gene_education import TASK_GUIDES, categories_for, classify_gene, load_annotations
from backend.app.services.gene_identity import GeneIdentityAdapter
from backend.app.services.scientific_analysis import _load_frozen_database

router = APIRouter(prefix="/coverage", tags=["coverage"])


@router.get("")
def get_coverage(
    request: Request,
    cell_line: str | None = Query(default=None, max_length=128),
    run_id: str | None = Query(default=None, pattern=r"^run_[a-zA-Z0-9_-]{1,56}$"),
) -> JSONResponse:
    if run_id is not None or set(request.query_params) - {"cell_line", "run_id"}:
        return _build_coverage(request, cell_line, run_id)
    container = request.app.state.container
    if not (container.settings.sccellfie_database_root / 'manifest.json').is_file():
        return _build_coverage(request, cell_line, run_id)
    try:
        return model_catalog_response(
            container.settings.project_root, cell_line, container.registry.models,
            lambda: _build_coverage(request, cell_line, run_id),
        )
    except (OSError, ValueError, TypeError, ImportError) as exc:
        raise HTTPException(
            503, detail={"code": "COVERAGE_UNAVAILABLE", "message": "覆盖来源发生变化或暂不可用，请重试"}
        ) from exc


def _build_coverage(request: Request, cell_line: str | None, run_id: str | None) -> JSONResponse:
    if set(request.query_params) - {"cell_line", "run_id"}:
        raise HTTPException(
            422, detail={"code": "INVALID_COVERAGE_SOURCE", "message": "不支持的覆盖来源参数"}
        )
    if cell_line is not None and run_id is not None:
        raise HTTPException(
            422, detail={"code": "COVERAGE_SOURCE_CONFLICT", "message": "请只选择一种覆盖来源"}
        )
    container = request.app.state.container
    settings = container.settings
    models = [
        {
            "id": row["id"],
            "cell_line": row["cell_line"],
            "panel_sha256": str(row["gene_list_sha256"]).lower()
            if container.registry.asset_is_valid_cached(
                container.registry.model_for(row["cell_line"]), "gene_list_path", "gene_list_sha256"
            )
            else None,
        }
        for row in container.registry.models
        if row.get("enabled") and row.get("gene_list_path")
    ]
    try:
        database, _ = _load_frozen_database(settings.sccellfie_database_root)
        identity = (
            GeneIdentityAdapter.load(settings.gene_identity_root, settings.sccellfie_database_root)
            if settings.gene_identity_root.exists()
            else None
        )
        source: dict[str, Any]
        if run_id:
            report = get_completeness(run_id, request).model_dump(mode="json")
            path = _artifact_path(run_id, "gene_deltas.csv", request)
            with path.open(encoding="utf-8", newline="") as stream:
                panel = [row["gene"].upper() for row in csv.DictReader(stream)]
            provenance = get_provenance(run_id, request)
            record = container.store.get(run_id)
            source = {
                "kind": "run",
                "id": run_id,
                "title": f"{record.request.cell_line} / {record.request.perturbation}",
                "panel_sha256": file_sha256(path),
                "model_id": provenance.get("assets", {}).get("model_id"),
            }
        else:
            selected = next(
                (row for row in models if cell_line is None or row["cell_line"] == cell_line), None
            )
            if selected is None:
                raise HTTPException(
                    404,
                    detail={"code": "COVERAGE_MODEL_UNAVAILABLE", "message": "未找到该背景的已注册基因面板"},
                )
            model = container.registry.model_for(selected["cell_line"])
            if not model.asset_is_valid("gene_list_path", "gene_list_sha256"):
                raise ValueError("Registered gene panel failed hash validation")
            raw = model.path("gene_list_path").read_text(encoding="utf-8").splitlines()
            panel = [
                identity.resolve(gene)["analysis_symbol"] if identity else gene.strip().upper()
                for gene in raw
                if gene.strip()
            ]
            report = cached_completeness(
                tuple(panel),
                str(settings.sccellfie_database_root),
                database["_celllens_provenance"]["manifest_sha256"],
            )
            source = {
                "kind": "model",
                **selected,
                "title": selected["cell_line"],
                "panel_sha256": model.payload["gene_list_sha256"],
            }
        if (
            report["database_provenance"]["manifest_sha256"]
            != database["_celllens_provenance"]["manifest_sha256"]
        ):
            raise HTTPException(
                409,
                detail={
                    "code": "COVERAGE_DATABASE_CHANGED",
                    "message": "保存结果使用不同版本的数据库，请从该实验下载原始覆盖报告",
                },
            )
        content = {**coverage_catalog(panel, database, report, identity), "source": source, "models": models}
        annotations = load_annotations(settings.registry_root)
        content["genes"] = [
            {**gene, **classify_gene(gene["symbol"], annotations, gene["hgnc_id"])}
            for gene in content["genes"]
        ]
        content["gene_categories"] = categories_for(
            [gene for gene in content["genes"] if gene["in_panel"]], annotations
        )
        content["classification"] = {
            "available": annotations is not None,
            "method": "PANTHER Protein Class / HGNC identity",
            "multi_label": True,
            "provenance": annotations["provenance"] if annotations else None,
        }
        content["tasks"] = [{**task, "guide": TASK_GUIDES.get(task["id"])} for task in content["tasks"]]
        return JSONResponse(content, headers={"Cache-Control": "no-store"})
    except HTTPException:
        raise
    except (OSError, ValueError, KeyError, TypeError, ImportError, CellLensError) as exc:
        raise HTTPException(
            503,
            detail={
                "code": "COVERAGE_UNAVAILABLE",
                "message": "覆盖目录暂不可用：模型面板或冻结数据库未通过校验",
            },
        ) from exc
