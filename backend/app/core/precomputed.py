"""Validate the same bundle contract for catalog discovery and materialization."""

import json
from pathlib import Path
from typing import Any

from backend.app.core.projection import validate_projection
from backend.app.core.run_manifest import file_sha256
from backend.app.schemas import RunSummary


def load_bundle(source: Path, cell_line: str, perturbation: str) -> tuple[RunSummary, dict[str, Any]]:
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    files = manifest["files"]
    if not isinstance(files, dict) or "summary.json" not in files:
        raise ValueError("Precomputed manifest must hash summary.json")
    if "projection.json" not in files:
        raise ValueError("Precomputed manifest must include a hashed projection.json")
    for relative_name, expected in files.items():
        artifact = (source / relative_name).resolve()
        if not artifact.is_relative_to(source.resolve()) or not artifact.is_file():
            raise ValueError(f"Invalid precomputed artifact path: {relative_name}")
        if file_sha256(artifact).lower() != str(expected).lower():
            raise ValueError(f"Precomputed artifact hash mismatch: {relative_name}")
    template = RunSummary.model_validate_json((source / "summary.json").read_text(encoding="utf-8"))
    validate_projection(source / "projection.json")
    if template.cell_line != cell_line or template.perturbation.upper() != perturbation.upper():
        raise ValueError("Summary context does not match request")
    kind = manifest.get("kind", "synthetic_demo")
    if kind == "frozen_model_result":
        required = {
            "source_manifest.json",
            "expression_contract.json",
            "gene_deltas.csv",
            "metabolic_task_scores.csv",
            "metabolic_coverage.csv",
            "reaction_scores.csv",
            "task_trace.json",
            "official_completeness.json",
        }
        if not required.issubset(files):
            raise ValueError("Frozen real bundle lacks its original manifest or required results")
        if file_sha256(source / "source_manifest.json") != manifest.get("source_manifest_sha256"):
            raise ValueError("Original real manifest hash differs")
        original = json.loads((source / "source_manifest.json").read_text(encoding="utf-8"))
        request = original["request"]
        if (
            request.get("mode") not in {"online", "validation"}
            or request.get("cell_line") != cell_line
            or request.get("perturbation") != perturbation
            or template.run_id != manifest.get("source_run_id")
            or template.status != "completed"
        ):
            raise ValueError("Frozen bundle does not identify a completed matching real run")
        if request["mode"] == "validation" and "validation_metrics.json" not in files:
            raise ValueError("Real diagnostic replay must preserve validation metrics")
        for name, digest in files.items():
            if name != "source_manifest.json" and original["outputs"].get(name, {}).get("sha256") != digest:
                raise ValueError(f"Frozen result differs from original manifest: {name}")
    elif kind != "synthetic_demo":
        raise ValueError("Unknown precomputed result kind")
    return template.model_copy(update={"result_kind": kind}), manifest


def available_bundles(
    demo_root: Path, cell_line: str, *, allow_synthetic: bool = False
) -> list[str]:
    root = demo_root / cell_line
    if not root.is_dir():
        return []
    available = []
    for source in root.iterdir():
        if not source.is_dir() or source.is_symlink():
            continue
        try:
            template, _ = load_bundle(source, cell_line, source.name)
            if template.result_kind != "frozen_model_result" and not allow_synthetic:
                continue
        except (OSError, ValueError, KeyError, TypeError):
            continue
        available.append(source.name)
    return sorted(available)
