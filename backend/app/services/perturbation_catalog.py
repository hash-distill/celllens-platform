"""Read-only fixed-source coverage. Missing cache is uncertainty, never zero cells."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from backend.app.core.run_manifest import file_sha256, manifest_hash

CONTEXTS = ("HepG2", "Jurkat", "K562", "RPE1")
CONTROL = "NON-TARGETING"
SOURCE = {
    "kind": "measured_rna",
    "repo": "arcinstitute/State-Replogle-Filtered",
    "revision": "d790193bb2c93726541a75ca3fa873a92ed44da5",
    "file": "replogle_concat.h5ad",
    "url": "https://huggingface.co/datasets/arcinstitute/State-Replogle-Filtered/tree/"
    "d790193bb2c93726541a75ca3fa873a92ed44da5",
}


def normalize_context(value: str) -> str:
    for context in CONTEXTS:
        if value.casefold() == context.casefold():
            return context
    raise ValueError("Unsupported cell background; choose HepG2, Jurkat, K562 or RPE1")


def normalize_target(value: str, *, allow_control: bool = False) -> str:
    target = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9_.-]{0,63}", target):
        raise ValueError("Invalid perturbation symbol")
    if target == CONTROL and not allow_control:
        raise ValueError("Non-targeting controls are not perturbation targets")
    return target


def seal_document(document: dict[str, Any]) -> dict[str, Any]:
    payload = {key: value for key, value in document.items() if key != "manifest_sha256"}
    return {**payload, "manifest_sha256": manifest_hash(payload)}


def _signature(path: Path) -> tuple[int, ...]:
    value = path.stat()
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


@lru_cache(maxsize=8)
def _read_verified(path: Path, signature: tuple[int, ...]) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("manifest_sha256") != seal_document(document)["manifest_sha256"]:
        raise ValueError("Source coverage cache hash differs")
    if document.get("schema_version") != 1 or document.get("metadata_complete") is not True:
        raise ValueError("Source coverage cache is incomplete")
    if any(document.get("source", {}).get(key) != value for key, value in SOURCE.items()):
        raise ValueError("Source identity differs from the fixed revision")
    metadata = document["metadata"]
    if metadata.get("columns") != ["obs.cell_line", "obs.gene"]:
        raise ValueError("Source coverage columns differ")
    if not re.fullmatch(r"[0-9a-f]{64}", metadata.get("sha256", "")):
        raise ValueError("Missing complete metadata digest")
    totals: dict[str, int] = {}
    seen = set()
    for row in document["counts"]:
        context = normalize_context(row["cell_line"])
        target = normalize_target(row["perturbation"], allow_control=True)
        key = (context, target)
        if key in seen or type(row["cell_count"]) is not int or row["cell_count"] <= 0:
            raise ValueError("Invalid or duplicate source count")
        seen.add(key)
        totals[context] = totals.get(context, 0) + row["cell_count"]
    if totals != document["context_totals"] or sum(totals.values()) != metadata["n_obs"]:
        raise ValueError("Source totals do not match the complete obs input")
    if not totals or _signature(path) != signature:
        raise ValueError("Source cache changed during verification")
    return document


def catalog_document(root: Path) -> dict[str, Any]:
    path = root / "data/registry/perturbation_catalog.json"
    try:
        return {**_read_verified(path, _signature(path)), "source_verified": True}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {"source": SOURCE, "source_verified": False, "counts": [], "official_splits": {}}


def _same_source(value: dict[str, Any]) -> bool:
    return all(value.get(key) == SOURCE[key] for key in ("kind", "repo", "revision", "file"))


@lru_cache(maxsize=32)
def _verify_local(
    path: Path, signature: tuple[int, ...], expected: str, count: int, context: str, target: str
) -> bool:
    """Hash and metadata only; never materialize X or import the model engine."""
    import h5py

    def labels(node: Any) -> list[str]:
        def decode(value: Any) -> str:
            return value.decode() if isinstance(value, bytes) else str(value)

        if isinstance(node, h5py.Group):
            categories = [decode(value) for value in cast(h5py.Dataset, node["categories"])[:]]
            codes = cast(h5py.Dataset, node["codes"])[:]
            if any(int(code) < 0 or int(code) >= len(categories) for code in codes):
                raise ValueError("Missing local observation label")
            return [categories[int(code)] for code in codes]
        return [decode(value) for value in node[:]]

    try:
        if not expected or file_sha256(path) != expected:
            return False
        with h5py.File(path, "r") as handle:
            obs = cast(h5py.Group, handle["obs"])
            lines, targets = labels(obs["cell_line"]), labels(obs["gene"])
            valid = (
                len(lines) == len(targets) == count
                and count > 0
                and all(normalize_context(line) == context for line in lines)
                and all(normalize_target(item) == target for item in targets)
            )
        return valid and _signature(path) == signature
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _local_observations(root: Path) -> dict[tuple[str, str], int]:
    try:
        rows = json.loads((root / "data/registry/observations.json").read_text(encoding="utf-8"))[
            "observations"
        ]
        if not isinstance(rows, list):
            return {}
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    output = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            if row.get("status") != "available" or not _same_source(row.get("source", {})):
                continue
            context, target = normalize_context(row["cell_line"]), normalize_target(row["perturbation"])
            count = row["n_cells"]
            if type(count) is not int or count <= 0:
                continue
            path = (root / row["path"]).resolve()
            if not path.is_relative_to(root.resolve()):
                continue
            if _verify_local(path, _signature(path), row["sha256"], count, context, target):
                output[(context, target)] = count
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    return output


def _supported(container: Any) -> dict[str, set[str]]:
    registered = {row["cell_line"] for row in container.registry.models}
    return {
        context: {
            normalize_target(target)
            for target in container.registry.supported_perturbations(context)
            if str(target).upper() != CONTROL
        }
        if context in registered
        else set()
        for context in CONTEXTS
    }


def _snapshot(
    container: Any,
) -> tuple[dict[str, Any], dict[str, set[str]], dict[tuple[str, str], int], dict[tuple[str, str], int]]:
    root = container.settings.project_root
    document = catalog_document(root)
    counts = {(row["cell_line"], row["perturbation"]): row["cell_count"] for row in document["counts"]}
    return document, _supported(container), counts, _local_observations(root)


def _row(
    context: str,
    target: str,
    document: dict[str, Any],
    supported: dict[str, set[str]],
    counts: dict[tuple[str, str], int],
    local: dict[tuple[str, str], int],
) -> dict[str, Any]:
    verified = document["source_verified"]
    count = counts.get((context, target), 0) if verified else None
    model_supported = target in supported[context]
    local_count = local.get((context, target), 0)
    split = document.get("official_splits", {}).get(context)
    official_split = (
        (
            "test"
            if target in split.get("test", [])
            else "val"
            if target in split.get("val", [])
            else "not_declared_held_out"
        )
        if split
        else "unknown"
    )
    action = (
        "check_source"
        if count is None
        else "measured"
        if count > 0
        else "predict_exploratory"
        if model_supported
        else "unsupported"
    )
    return {
        "cell_line": context,
        "perturbation": target,
        "source_cell_count": count,
        "source_status": "unknown" if count is None else "measured" if count else "not_in_source",
        "local_verified": bool(local_count),
        "local_measured_cells": local_count,
        "model_supported": model_supported,
        "official_split": official_split,
        "training_exclusion_verified": False,
        "generalization_verified": False,
        "recommended_action": action,
    }


def pair_detail(container: Any, cell_line: str, perturbation: str) -> dict[str, Any]:
    context, target = normalize_context(cell_line), normalize_target(perturbation)
    return _row(context, target, *_snapshot(container))


def query_pairs(
    container: Any,
    *,
    cell_line: str | None = None,
    query: str = "",
    availability: str = "all",
    model_supported: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    if availability not in {"all", "measured", "missing", "unknown"}:
        raise ValueError("Invalid availability filter")
    if not 1 <= limit <= 100000 or offset < 0 or len(query) > 64:
        raise ValueError("Invalid catalog pagination or search length")
    context = normalize_context(cell_line) if cell_line else None
    document, supported, counts, local = _snapshot(container)
    targets = sorted((set().union(*supported.values()) | {key[1] for key in counts}) - {CONTROL})
    rows = [_row(line, target, document, supported, counts, local) for line in CONTEXTS for target in targets]
    measured = [row for row in rows if row["source_status"] == "measured"]
    missing = [row for row in rows if row["model_supported"] and row["source_status"] == "not_in_source"]
    summary = {
        "pairs": len(rows),
        "measured_pairs": len(measured),
        "model_supported_pairs": sum(row["model_supported"] for row in rows),
        "model_supported_unmeasured_pairs": len(missing) if document["source_verified"] else None,
        "unknown_pairs": sum(row["source_status"] == "unknown" for row in rows),
        "local_verified_pairs": len(local),
        "contexts": [
            {
                "cell_line": line,
                "source_total_cells": document.get("context_totals", {}).get(line)
                if document["source_verified"]
                else None,
                "measured_pairs": sum(row["cell_line"] == line for row in measured),
                "model_supported_pairs": len(supported[line]),
                "model_supported_unmeasured_pairs": sum(row["cell_line"] == line for row in missing)
                if document["source_verified"]
                else None,
            }
            for line in CONTEXTS
        ],
    }
    term = query.strip().upper()
    items = [
        row
        for row in rows
        if (not context or row["cell_line"] == context)
        and term in row["perturbation"]
        and (model_supported is None or row["model_supported"] is model_supported)
        and (
            availability == "all"
            or row["source_status"]
            == {"measured": "measured", "missing": "not_in_source", "unknown": "unknown"}.get(availability)
        )
    ]
    source = {
        **SOURCE,
        "scope": "Only this fixed filtered revision; absence is not global absence",
        "manifest_sha256": document.get("manifest_sha256"),
        "metadata_sha256": document.get("metadata", {}).get("sha256"),
        "official_splits": {
            line: {key: value for key, value in split.items() if key not in {"test", "val"}}
            for line, split in document.get("official_splits", {}).items()
        },
    }
    return {
        "items": items[offset : offset + limit],
        "total": len(items),
        "summary": summary,
        "source": source,
        "source_verified": document["source_verified"],
    }
