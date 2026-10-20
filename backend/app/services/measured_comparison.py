"""Immutable measured-RNA comparisons attached to, rather than replacing, model runs."""

import json
import re
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.app.core.registry import AssetRegistry, RegistryEntry
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.schemas import CreateRunRequest


class ComparisonUnavailable(ValueError):
    pass


def validate_frozen_contract(model: RegistryEntry, dataset: RegistryEntry, assets: dict[str, Any]) -> None:
    expected = {
        "model_id": model.payload.get("id"),
        "dataset_id": dataset.payload.get("id"),
        "input_embed_key": model.payload.get("embed_key"),
        "expression_key": model.payload.get("expression_key") or model.payload.get("embed_key") or "X",
        "model_expression_scale": model.payload.get("expression_scale"),
        "dataset_expression_scale": dataset.payload.get("expression_scale"),
        "config_sha256": model.payload.get("config_sha256"),
        "checkpoint_sha256": model.payload.get("checkpoint_sha256"),
        "gene_list_sha256": model.payload.get("gene_list_sha256"),
    }
    if any(assets.get(key) != value for key, value in expected.items()):
        raise ComparisonUnavailable("Registry interpretation differs from frozen prediction contract")


def _write_state(root: Path, run_id: str, status: str, attempt_id: str = "") -> None:
    path = root / "data/derived/comparison_states" / f"{run_id}.json"
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.json")
    atomic_write_json(temporary, {"run_id": run_id, "status": status, "attempt_id": attempt_id})
    temporary.replace(path)


def mark_comparison_pending(root: Path, run_id: str) -> None:
    if not re.fullmatch(r"run_[A-Za-z0-9_]+", run_id):
        raise ComparisonUnavailable("Invalid run identity")
    _write_state(root, run_id, "preparing")


def comparison_state(root: Path, run_id: str) -> dict[str, Any] | None:
    if not re.fullmatch(r"run_[A-Za-z0-9_]+", run_id):
        raise ComparisonUnavailable("Invalid run identity")
    path = root / "data/derived/comparison_states" / f"{run_id}.json"
    return _read(path) if path.is_file() else None


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _path(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ComparisonUnavailable("Comparison source is outside the project")
    return path


def _checked(root: Path, name: str, expected: str) -> Path:
    path = _path(root, name)
    if not expected or not path.is_file() or file_sha256(path) != expected:
        raise ComparisonUnavailable(f"Comparison source hash mismatch: {path.name}")
    return path


def observation_status(root: Path, cell_line: str, perturbation: str) -> dict[str, Any] | None:
    catalog = root / "data/registry/observations.json"
    if not catalog.is_file():
        return None
    matches = [
        row
        for row in _read(catalog)["observations"]
        if row["cell_line"] == cell_line and row["perturbation"] == perturbation
    ]
    if len(matches) > 1:
        raise ComparisonUnavailable("Ambiguous measured observation identity")
    return matches[0] if matches else None


def observation_for(root: Path, cell_line: str, perturbation: str) -> dict[str, Any] | None:
    row = observation_status(root, cell_line, perturbation)
    if not row or row.get("status") != "available":
        return None
    if row.get("source", {}).get("kind") != "measured_rna":
        raise ComparisonUnavailable("Observation must have measured RNA provenance")
    _checked(root, row["path"], row["sha256"])
    return row


def comparable_perturbations(root: Path, cell_line: str, supported: list[str]) -> list[dict[str, Any]]:
    catalog = root / "data/registry/observations.json"
    if not catalog.is_file():
        return []
    output = []
    for row in _read(catalog)["observations"]:
        if row["cell_line"] != cell_line or row["perturbation"] not in supported:
            continue
        try:
            verified = observation_for(root, cell_line, row["perturbation"])
        except ComparisonUnavailable:
            continue
        if verified is not None:
            output.append({"perturbation": row["perturbation"], "measured_cells": verified["n_cells"]})
    return output


def paired_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    columns = ["control", "predicted", "observed", "predicted_delta", "observed_delta"]
    numeric = frame[columns].apply(pd.to_numeric, errors="coerce")
    numeric = numeric.loc[np.isfinite(numeric).all(axis=1)].copy()
    numeric["absolute_error"] = (numeric["predicted_delta"] - numeric["observed_delta"]).abs()
    return [
        {"id": str(name), **{key: float(value) for key, value in row.items()}}
        for name, row in numeric.iterrows()
    ]


def load_comparison(root: Path, run_id: str) -> dict[str, Any] | None:
    if not re.fullmatch(r"run_[A-Za-z0-9_]+", run_id):
        raise ComparisonUnavailable("Invalid run identity")
    bundle = root / "data/derived/comparisons" / run_id
    if not bundle.exists():
        return None
    try:
        manifest = _read(bundle / "manifest.json")
        if manifest["run_id"] != run_id:
            raise ComparisonUnavailable("Comparison run identity mismatch")
        original = _checked(
            root, f"data/derived/runs/{run_id}/manifest.json", manifest["source_manifest_sha256"]
        )
        for name, expected in manifest["inputs"].items():
            _checked(root, name, expected)
        for name, expected in manifest["outputs"].items():
            _checked(bundle, name, expected)
        report = _read(bundle / "comparison.json")
        request = _read(original)["request"]
        if (
            report["status"] != "available"
            or report["run_id"] != run_id
            or report["cell_line"] != request["cell_line"]
            or report["perturbation"] != request["perturbation"]
        ):
            raise ComparisonUnavailable("Comparison does not match original prediction")
        return report
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ComparisonUnavailable(str(exc)) from exc


def comparison_examples(root: Path) -> list[dict[str, str]]:
    examples = []
    for path in sorted((root / "data/derived/comparisons").glob("run_*/comparison.json")):
        # Fully verify a bundle only when opening it. The index is navigation, not metric evidence.
        try:
            row = _read(path)
            examples.append(
                {"run_id": row["run_id"], "cell_line": row["cell_line"], "perturbation": row["perturbation"]}
            )
        except (OSError, KeyError, ValueError):
            continue
    return examples


def _prepare_comparison(
    root: Path, run_id: str, registry: AssetRegistry | None, attempt_id: str
) -> dict[str, Any] | None:
    """CPU-only preparation, called by an explicit script or after a genuine online run."""
    existing = load_comparison(root, run_id)
    if existing is not None:
        return existing
    source_root = root / "data/derived/runs" / run_id
    original_hash = file_sha256(source_root / "manifest.json")
    original = _read(source_root / "manifest.json")
    request = CreateRunRequest.model_validate(original["request"])
    if request.mode not in {"online", "validation"} or original.get("source_type"):
        return None
    observation = observation_for(root, request.cell_line, request.perturbation)
    if observation is None:
        return None
    registry = registry or AssetRegistry(root, root / "data/registry")
    model = registry.model_for(request.cell_line)
    dataset = registry.dataset_for(request.cell_line)
    assets = original["assets"]
    validate_frozen_contract(model, dataset, assets)
    if observation.get("expression_scale") != assets["dataset_expression_scale"]:
        raise ComparisonUnavailable("Measured expression scale differs from the comparison contract")
    inputs = {
        f"data/derived/runs/{run_id}/predicted.h5ad": original["outputs"]["predicted.h5ad"]["sha256"],
        dataset.payload["control_path"]: assets["control_sha256"],
        model.payload["gene_list_path"]: assets["gene_list_sha256"],
        observation["path"]: observation["sha256"],
    }
    if model.payload.get("config_path"):
        inputs[model.payload["config_path"]] = assets["config_sha256"]
    contract_name = f"data/derived/runs/{run_id}/expression_contract.json"
    inputs[contract_name] = original["outputs"]["expression_contract.json"]["sha256"]
    for name, expected in inputs.items():
        _checked(root, name, expected)
    contract = _read(root / contract_name)
    if contract.get("analysis_version") != "expression-cp10k-v2" or contract.get(
        "population_selection", {}
    ).get("perturbation_column") != model.payload.get("perturbation_column"):
        raise ComparisonUnavailable("Prediction population interpretation changed")
    from backend.app.core.cache import code_fingerprint
    from backend.app.services.scientific_analysis import ScientificAnalysisService

    final = root / "data/derived/comparisons" / run_id
    partial = final.with_name(f"{run_id}.attempt-{attempt_id}.partial")
    partial.mkdir(parents=True, exist_ok=False)
    paired_dataset = RegistryEntry(
        {
            **dataset.payload,
            "observed_path": observation["path"],
            "observed_sha256": observation["sha256"],
            "validation_batch_key": "gem_group",
        },
        root,
    )
    analysis = ScientificAnalysisService(
        root / "data/registry/sccellfie/human", gene_identity_root=root / "data/registry/gene_identity"
    )
    result = analysis.run(
        run_id,
        request.model_copy(update={"mode": "validation"}),
        model,
        paired_dataset,
        source_root / "predicted.h5ad",
        partial,
    )
    metrics = _read(partial / "validation_metrics.json")
    genes = paired_rows(pd.read_csv(partial / "gene_deltas.csv", index_col=0))
    tasks = []
    if (partial / "metabolic_task_scores.csv").is_file():
        scores = pd.read_csv(partial / "metabolic_task_scores.csv", index_col=0)
        means = scores.drop(columns="source").groupby(scores["source"]).mean().T
        means["predicted_delta"] = means["predicted"] - means["control"]
        means["observed_delta"] = means["observed"] - means["control"]
        tasks = paired_rows(means)
    # DEG count error is not an error in response effect magnitude.
    de = metrics["differential_expression"].copy()
    de["deg_count_absolute_error"] = de.pop("effect_size_absolute_error", None)
    observed_source = {
        key: observation["source"][key]
        for key in ("kind", "repo", "revision", "file", "url")
        if key in observation["source"]
    }
    report = {
        "schema_version": 1,
        "status": "available",
        "run_id": run_id,
        "cell_line": request.cell_line,
        "perturbation": request.perturbation,
        "source": {
            **observed_source,
            "observed_sha256": observation["sha256"],
            "available_measured_cells": observation["n_cells"],
        },
        "expression": metrics["expression"],
        "differential_expression": de,
        "metabolic": metrics.get("metabolic"),
        "parameters": metrics["parameters"],
        "population_matching": metrics.get("population_matching"),
        "genes": genes,
        "tasks": tasks,
        "held_out_validation": False,
        "training_exclusion_verified": False,
        "protocol_status": "matched_observation_diagnostic",
        "units": {"expression": "mean(log1p(CP10K))", "tasks": "expression-derived scCellFie score"},
        "metric_sources": [
            {
                "label": "Arc Cell-Eval expression metrics",
                "url": "https://github.com/ArcInstitute/cell-eval",
                "scope": "delta Pearson, MSE and MAE; implemented on the same measured-control reference",
            },
            {
                "label": "Scanpy rank_genes_groups",
                "url": "https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.rank_genes_groups.html",
                "scope": "Wilcoxon, tie correction, BH-FDR 0.05; diagnostic only",
            },
        ],
        "warnings": [
            *metrics.get("warnings", []),
            *result.summary.get("warnings", []),
            "Evaluation uses the common recorded batches, with their original frequencies.",
            "scCellFie agreement is expression-derived task agreement, not measured flux.",
            "All finite paired genes, including zero changes, are evaluated; no observations are imputed.",
        ],
        "binding": {
            "prediction_manifest_sha256": original_hash,
            "prediction_sha256": original["outputs"]["predicted.h5ad"]["sha256"],
            "code_sha256": code_fingerprint(root),
        },
    }
    atomic_write_json(partial / "comparison.json", report)
    for name, expected in inputs.items():
        _checked(root, name, expected)
    _checked(root, f"data/derived/runs/{run_id}/manifest.json", original_hash)
    manifest = {
        "run_id": run_id,
        "source_manifest_sha256": report["binding"]["prediction_manifest_sha256"],
        "inputs": inputs,
        "outputs": {p.name: file_sha256(p) for p in partial.iterdir() if p.is_file()},
    }
    atomic_write_json(partial / "manifest.json", manifest)
    try:
        partial.rename(final)
    except OSError:
        if not final.is_dir():
            raise
        # Another completed attempt won publication. Its verified immutable bundle is authoritative.
        return load_comparison(root, run_id)
    return load_comparison(root, run_id)


def prepare_comparison(
    root: Path, run_id: str, registry: AssetRegistry | None = None
) -> dict[str, Any] | None:
    if not re.fullmatch(r"run_[A-Za-z0-9_]+", run_id):
        raise ComparisonUnavailable("Invalid run identity")
    attempt_id = uuid.uuid4().hex
    _write_state(root, run_id, "preparing", attempt_id)
    try:
        result = _prepare_comparison(root, run_id, registry, attempt_id)
        _write_state(root, run_id, "available" if result else "unavailable", attempt_id)
        return result
    except Exception as exc:
        partial = root / "data/derived/comparisons" / f"{run_id}.attempt-{attempt_id}.partial"
        if partial.is_dir():
            atomic_write_json(partial / "failure.json", {"error_type": type(exc).__name__})
        _write_state(root, run_id, "failed", attempt_id)
        raise
