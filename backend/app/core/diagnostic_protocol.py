"""One shared gate for measured diagnostic discovery and execution."""

import json
from typing import Any

from backend.app.core.registry import RegistryEntry


def load_diagnostic_protocol(dataset: RegistryEntry, model: RegistryEntry) -> dict[str, Any]:
    if not dataset.asset_is_valid("validation_protocol_path", "validation_protocol_sha256"):
        raise ValueError("A hash-frozen measured diagnostic protocol is required")
    if not dataset.asset_is_valid("observed_path", "observed_sha256"):
        raise ValueError("The registered measured observations are missing or changed")
    document = json.loads(dataset.path("validation_protocol_path").read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Diagnostic protocol must be an object")
    if (
        document.get("schema_version") != 1
        or document.get("kind") != "matched_observation_diagnostic"
        or document.get("cell_line") != dataset.payload["cell_line"]
        or document.get("observed_sha256") != dataset.payload["observed_sha256"]
        or document.get("expression_scale") != dataset.payload.get("expression_scale")
        or document.get("batch_key") != dataset.payload.get("validation_batch_key")
        or document.get("held_out_validation") is not False
        or document.get("training_exclusion_verified") is not False
    ):
        raise ValueError("Diagnostic protocol does not match its measured dataset or scope")
    names = document.get("perturbations")
    supported = {str(gene).upper() for gene in model.payload.get("supported_perturbations", [])}
    if (
        not isinstance(names, list)
        or not names
        or any(not isinstance(name, str) or name != name.upper() or name not in supported for name in names)
        or len(set(names)) != len(names)
    ):
        raise ValueError("Diagnostic perturbations must be a nonempty supported unique list")
    return document
