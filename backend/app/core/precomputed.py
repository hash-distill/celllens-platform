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
    return template, manifest


def available_bundles(demo_root: Path, cell_line: str) -> list[str]:
    root = demo_root / cell_line
    if not root.is_dir():
        return []
    available = []
    for source in root.iterdir():
        if not source.is_dir() or source.is_symlink():
            continue
        try:
            load_bundle(source, cell_line, source.name)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        available.append(source.name)
    return sorted(available)
