from typing import Literal

from fastapi import APIRouter, Request

from backend.app.schemas import ContextItem
from backend.app.services.gene_education import categories_for, classify_gene, load_annotations
from backend.app.services.measured_comparison import comparable_perturbations

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/contexts", response_model=list[ContextItem])
def contexts(request: Request) -> list[ContextItem]:
    container = request.app.state.container
    registry = container.registry
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
        online_ready = (
            model_ready
            and dataset_ready
            and container.settings.worker_enabled
            and container.settings.gpu_available
        )
        reasons = []
        if not model_ready:
            reasons.append("model assets are disabled, missing, or have invalid hashes")
        if not dataset_ready:
            reasons.append("control dataset is disabled, missing, or has an invalid hash")
        if not container.settings.worker_enabled:
            reasons.append("analysis worker is disabled")
        if not container.settings.gpu_available:
            reasons.append("GPU is unavailable")
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
    mode: Literal["online", "precomputed", "validation"] = "online",
) -> dict[str, object]:
    container = request.app.state.container
    # Legacy modes remain readable in stored records, but cannot start experiments.
    items = container.registry.supported_perturbations(cell_line) if mode == "online" else []
    annotation_error = None
    try:
        annotations = load_annotations(container.settings.registry_root)
    except (OSError, ValueError, KeyError):
        annotations = None
        annotation_error = "功能分类快照未通过校验；扰动可用列表仍以模型登记为准"
    genes = [classify_gene(symbol, annotations) for symbol in items]
    return {
        "cell_line": cell_line,
        "mode": mode,
        "items": items,
        "measured_comparisons": comparable_perturbations(container.settings.project_root, cell_line, items),
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
