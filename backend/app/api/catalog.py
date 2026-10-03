from typing import Literal

from fastapi import APIRouter, Request

from backend.app.core.precomputed import available_bundles
from backend.app.schemas import ContextItem

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
        model_ready = bool(row.get("enabled")) and model_entry.asset_is_valid(
            "checkpoint_path", "checkpoint_sha256"
        )
        if row.get("gene_list_path"):
            model_ready = model_ready and model_entry.asset_is_valid("gene_list_path", "gene_list_sha256")
        if row.get("config_path"):
            model_ready = model_ready and model_entry.asset_is_valid("config_path", "config_sha256")
        dataset_ready = False
        validation_ready = False
        if dataset:
            dataset_entry = registry.dataset_for(row["cell_line"], require_enabled=False)
            dataset_ready = bool(dataset.get("enabled")) and dataset_entry.asset_is_valid(
                "control_path", "control_sha256"
            )
            if dataset.get("split_path"):
                dataset_ready = dataset_ready and dataset_entry.asset_is_valid("split_path", "split_sha256")
            validation_ready = (
                model_ready
                and dataset_ready
                and dataset_entry.asset_is_valid("observed_path", "observed_sha256")
            )
        online_ready = (
            model_ready
            and dataset_ready
            and container.settings.worker_enabled
            and container.settings.gpu_available
        )
        validation_ready = validation_ready and online_ready
        precomputed_ready = bool(available_bundles(container.settings.demo_root, row["cell_line"]))
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
                validation_ready=validation_ready,
                precomputed_ready=precomputed_ready,
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
    if mode == "precomputed":
        items = available_bundles(container.settings.demo_root, cell_line)
    elif mode == "validation":
        # No approved development validation protocol/list is registered yet.
        items = []
    else:
        items = container.registry.supported_perturbations(cell_line)
    return {"cell_line": cell_line, "mode": mode, "items": items}
