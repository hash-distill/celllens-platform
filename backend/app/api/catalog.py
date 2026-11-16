import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.app.schemas import ContextItem
from backend.app.services.control_metadata import control_cell_count
from backend.app.services.gene_education import categories_for, classify_gene, load_annotations
from backend.app.services.measured_comparison import comparable_perturbations
from backend.app.services.perturbation_catalog import query_pairs
from backend.app.services.worker_status import prediction_ready

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/data-summary")
def data_summary(request: Request) -> JSONResponse:
    """Registry and verified obs metadata; never load weights or expression matrices."""
    registry = request.app.state.container.registry
    observation_path = registry.registry_root / "observations.json"
    observations = (
        json.loads(observation_path.read_text(encoding="utf-8")).get("observations", [])
        if observation_path.is_file()
        else []
    )
    output = []
    for model in registry.models:
        if not model.get("enabled"):
            continue
        entry = registry.model_for(model["cell_line"])
        verified = bool(model.get("gene_list_path")) and registry.asset_is_valid_cached(
            entry, "gene_list_path", "gene_list_sha256"
        )
        panel = (
            [
                gene.strip()
                for gene in entry.path("gene_list_path").read_text(encoding="utf-8").splitlines()
                if gene.strip()
            ]
            if verified
            else []
        )
        verified = verified and bool(panel) and len(set(panel)) == len(panel)
        dataset = next((row for row in registry.datasets if row.get("cell_line") == model["cell_line"]), {})
        control_count = control_cell_count(registry, model["cell_line"])
        output.append(
            {
                "cell_line": model["cell_line"],
                "model_id": model["id"],
                "model_version": model.get("code_version"),
                "expression_scale": model.get("expression_scale"),
                "expression_gene_count": len(panel) if verified else None,
                "expression_genes": panel if verified else [],
                "panel_verified": verified,
                "panel_sha256": model.get("gene_list_sha256") if verified else None,
                "perturbation_count": len(registry.supported_perturbations(model["cell_line"])),
                "dataset_id": dataset.get("id"),
                "control_registered": bool(dataset.get("enabled") and dataset.get("control_path")),
                "control_cell_count": control_count,
                "control_metadata_verified": control_count is not None,
                "registered_observations": [
                    {"perturbation": row["perturbation"], "cell_count": row.get("n_cells")}
                    for row in observations
                    if row.get("cell_line") == model["cell_line"]
                    and row.get("status") == "available"
                    and row.get("source", {}).get("kind") == "measured_rna"
                ],
            }
        )
    return JSONResponse(
        {"contexts": output, "observation_scope": "registered_metadata"},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/contexts", response_model=list[ContextItem])
def contexts(request: Request) -> list[ContextItem]:
    container = request.app.state.container
    registry = container.registry
    worker_ready = prediction_ready(container)
    output: list[ContextItem] = []
    for row in registry.models:
        dataset = next(
            (item for item in registry.datasets if item.get("cell_line") == row.get("cell_line")),
            None,
        )
        model_entry = registry.model_for(row["cell_line"], require_enabled=False)
        model_ready = bool(row.get("enabled")) and registry.asset_is_valid_cached(
            model_entry, "checkpoint_path", "checkpoint_sha256"
        )
        model_ready = model_ready and registry.model_companions_valid_cached(model_entry)
        if row.get("gene_list_path"):
            model_ready = model_ready and registry.asset_is_valid_cached(
                model_entry, "gene_list_path", "gene_list_sha256"
            )
        if row.get("config_path"):
            model_ready = model_ready and registry.asset_is_valid_cached(
                model_entry, "config_path", "config_sha256"
            )
        dataset_ready = False
        if dataset:
            dataset_entry = registry.dataset_for(row["cell_line"], require_enabled=False)
            dataset_ready = bool(dataset.get("enabled")) and registry.asset_is_valid_cached(
                dataset_entry, "control_path", "control_sha256"
            )
            if dataset.get("split_path"):
                dataset_ready = dataset_ready and registry.asset_is_valid_cached(
                    dataset_entry, "split_path", "split_sha256"
                )
        online_ready = model_ready and dataset_ready and worker_ready
        reasons = []
        if not model_ready:
            reasons.append("model assets are disabled, missing, or have invalid hashes")
        if not dataset_ready:
            reasons.append("control dataset is disabled, missing, or has an invalid hash")
        if not worker_ready:
            reasons.append("no live prediction worker with a verified CUDA/runtime capability")
        output.append(
            ContextItem(
                cell_line=row["cell_line"],
                online_ready=online_ready,
                validation_ready=False,
                precomputed_ready=False,
                model_id=row.get("id"),
                disabled_reason=None if model_ready else row.get("disabled_reason"),
                readiness_reasons=reasons,
            )
        )
    return output


@router.get("/perturbations")
def perturbations(
    cell_line: str,
    request: Request,
    mode: Literal["online", "measured", "precomputed", "validation"] = "online",
) -> dict[str, object]:
    container = request.app.state.container
    if mode == "measured":
        # The measured selector follows verified source coverage, independently of model readiness/vocabulary.
        try:
            result = query_pairs(container, cell_line=cell_line, availability="measured", limit=100000)
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        items = [row["perturbation"] for row in result["items"]]
    else:
        # Legacy modes remain readable in stored records, but cannot start experiments.
        items = container.registry.supported_perturbations(cell_line) if mode == "online" else []
    annotation_error = None
    try:
        annotations = load_annotations(container.settings.registry_root)
    except (OSError, ValueError, KeyError):
        annotations = None
        source = "实测数据覆盖" if mode == "measured" else "模型登记"
        annotation_error = f"功能分类快照未通过校验；扰动可用列表仍以{source}为准"
    genes = [classify_gene(symbol, annotations) for symbol in items]
    return {
        "cell_line": cell_line,
        "mode": mode,
        "items": items,
        "measured_comparisons": comparable_perturbations(container.settings.project_root, cell_line, items)
        if mode == "online"
        else [],
        "genes": genes,
        "categories": categories_for(genes, annotations),
        "classification": {
            "available": annotations is not None,
            "multi_label": True,
            "method": "PANTHER Protein Class / HGNC identity",
            "provenance": annotations["provenance"] if annotations else None,
            "warning": annotation_error,
        },
    }
