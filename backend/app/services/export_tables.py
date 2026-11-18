"""Provenance-bound CSV exchange tables, including units and population selection."""

import csv
import io
import json
import math
from typing import Any

from backend.app.core.run_manifest import file_sha256
from backend.app.schemas import RunStatus
from backend.app.services.cell_state import CellStateUnavailable, _checked, _manifest
from backend.app.services.measured_comparison import _checked as _comparison_checked
from backend.app.services.measured_comparison import load_comparison

METADATA_COLUMNS = [
    "run_id",
    "cell_line",
    "perturbation",
    "population",
    "selection_id",
    "units",
    "aggregation",
    "n_control",
    "n_predicted",
    "n_observed",
    "model_id",
    "result_source",
    "database_version",
    "manifest_sha256",
    "comparison_sha256",
    "comparison_manifest_sha256",
    "observed_sha256",
    "source_revision",
    "protocol_status",
    "reference_selection_sha256",
    "diagnostics_sha256",
    "selection_json",
    "warnings_json",
    "metadata_url",
]


def _sources(container: Any, run_id: str):
    record = container.store.get(run_id)
    if record.status != RunStatus.COMPLETED:
        raise CellStateUnavailable("Run is not completed")
    root, manifest, sha = _manifest(container, run_id)
    request = manifest.get("request", {})
    if any(request.get(key) != getattr(record.request, key) for key in ("cell_line", "perturbation")):
        raise CellStateUnavailable("Export identity does not match the frozen run")
    return record, root, manifest, sha


def _file(root: Any, manifest: dict, name: str):
    return _checked(root / name, manifest.get("outputs", {}).get(name, {}).get("sha256"))


def _optional_json(root: Any, manifest: dict, name: str) -> dict:
    if name not in manifest.get("outputs", {}):
        return {}
    document = json.loads(_file(root, manifest, name).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise CellStateUnavailable(f"Invalid frozen JSON: {name}")
    return document


def table_metadata(container: Any, run_id: str, population: str = "original") -> dict[str, Any]:
    if population not in {"original", "comparison"}:
        raise CellStateUnavailable("Unknown export population")
    if population == "comparison" and getattr(container.settings, "deployment_mode", "local") == "public":
        raise CellStateUnavailable("Public mode cannot read private comparisons")
    api_prefix = getattr(container.settings, "api_prefix", "/api/v1")
    record, root, manifest, sha = _sources(container, run_id)
    contract = _optional_json(root, manifest, "expression_contract.json")
    trace = _optional_json(root, manifest, "task_trace.json")
    official = _optional_json(root, manifest, "official_completeness.json")
    summary = _optional_json(root, manifest, "summary.json")
    counts: dict[str, int | None] = {key: None for key in ("control", "predicted", "observed")}
    selected_counts = (contract.get("validation_population") or {}).get("selected_cells") or {}
    for key, value in selected_counts.items():
        if key not in counts or isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise CellStateUnavailable("Invalid frozen selected population counts")
        counts[key] = value
    outputs = manifest.get("outputs", {})
    if "metabolic_task_scores.csv" in outputs:
        path = _file(root, manifest, "metabolic_task_scores.csv")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            # Legacy task/source/score tables describe tasks rather than individual cells.
            if reader.fieldnames and "source" in reader.fieldnames and "score" not in reader.fieldnames:
                score_counts: dict[str, int] = {key: 0 for key in counts}
                for row in reader:
                    source = row["source"]
                    if source not in score_counts:
                        raise CellStateUnavailable("Unknown cell source in frozen task scores")
                    score_counts[source] += 1
                counts.update(score_counts)
    if counts["predicted"] is None:
        counts["predicted"] = contract.get("population_selection", {}).get("selected_prediction_cells")
    selection = {
        "population_selection": contract.get("population_selection"),
        "validation_population": contract.get("validation_population"),
    }
    comparison_sha = None
    comparison = {}
    warnings: list[str] = []
    if population == "comparison":
        comparison = load_comparison(container.settings.project_root, run_id)
        if not comparison:
            raise CellStateUnavailable("This run has no verified matched-observation comparison")
        comparison_path = (
            container.settings.project_root / "data/derived/comparisons" / run_id / "comparison.json"
        )
        comparison_sha = file_sha256(comparison_path)
        counts = comparison.get("parameters", {}).get("population_counts", counts)
        selection = comparison.get("parameters", {}).get("population_matching", {})
        # Older saved versions place population_matching under the expression block.
        if not selection:
            selection = comparison.get("population_matching") or comparison.get("parameters", {}).get(
                "batch_matching", {}
            )
        expression_units = (
            comparison.get("units", {}).get("expression")
            or contract.get("gene_units")
            or "unknown: comparison expression units not declared"
        )
        warnings = comparison.get("warnings", [])
    else:
        expression_units = contract.get("gene_units") or "unknown: legacy expression units not declared"
    database = trace.get("database_version") or official.get("database_version")
    assets = manifest.get("assets", {})
    return {
        "schema_version": 1,
        "run_id": run_id,
        "cell_line": record.request.cell_line,
        "perturbation": record.request.perturbation,
        "population": population,
        "selection_id": f"{population}:{(comparison_sha or sha)[:16]}",
        "aggregation": "mean_per_source",
        "units": {
            "genes": expression_units,
            "tasks": "mean(scCellFie task activity score)",
            "reactions": "mean(scCellFie reaction activity score)",
        },
        "counts": counts,
        "n_control": counts.get("control"),
        "n_predicted": counts.get("predicted"),
        "n_observed": counts.get("observed"),
        "selection": selection,
        "requested_prediction_cells": record.request.n_cells,
        "seed": record.request.seed,
        "model_id": assets.get("model_id"),
        "result_source": summary.get("result_kind") or manifest.get("source_type") or record.request.mode,
        "database_version": database,
        "manifest_sha256": sha,
        "comparison_sha256": comparison_sha,
        "comparison_manifest_sha256": comparison.get("comparison_manifest_sha256"),
        "observed_sha256": comparison.get("source", {}).get("observed_sha256"),
        "source_revision": comparison.get("source", {}).get("revision"),
        "protocol_status": comparison.get(
            "protocol_status",
            "original_population" if population == "original" else "matched_observation_diagnostic",
        ),
        "reference_selection_sha256": comparison.get("evaluation_protocol", {}).get(
            "reference_selection_sha256"
        ),
        "diagnostics_sha256": comparison.get("diagnostics_provenance", {}).get("diagnostics_sha256"),
        "evaluation_protocol": comparison.get("evaluation_protocol"),
        "batch_sensitivity": comparison.get("batch_sensitivity"),
        "task_coverage": comparison.get("task_coverage"),
        "selection_json": json.dumps(selection, ensure_ascii=False, separators=(",", ":")),
        "warnings_json": json.dumps([*warnings, *comparison.get("warnings_zh", [])], ensure_ascii=False),
        "metadata_url": f"{api_prefix}/runs/{run_id}/comparison/download?table=json"
        if population == "comparison"
        else f"{api_prefix}/research/results/prediction/{run_id}/export",
        "source_expression_scales": contract.get("source_scales", {}),
        "predicted_values_are_measured_counts": False,
        "warnings": warnings,
    }


def _number(value: Any, *, optional: bool = False) -> float | None:
    if value is None or value == "":
        if optional:
            return None
        raise CellStateUnavailable("Required numeric export value is missing")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise CellStateUnavailable("Non-finite numeric export value")
    return parsed


def _metabolic_rows(path: Any, coverage: dict[str, dict] | None = None):
    import numpy as np
    import pandas as pd

    frame = pd.read_csv(path, index_col=0)
    if "source" not in frame or "score" in frame.columns or not frame.index.is_unique:
        raise CellStateUnavailable("This historic table has no verified per-cell score contract")
    if not bool(frame["source"].isin(["control", "predicted", "observed"]).all()):
        raise CellStateUnavailable("Unknown cell source in frozen metabolic scores")
    numeric = frame.drop(columns="source").apply(pd.to_numeric, errors="raise")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise CellStateUnavailable("Frozen metabolic scores contain missing or non-finite values")
    means = numeric.groupby(frame["source"], observed=True).mean()
    if not {"control", "predicted"}.issubset(means.index):
        raise CellStateUnavailable("Frozen scores lack control or predicted populations")
    rows = []
    for identifier in means.columns:
        control, predicted = (
            float(means.loc["control", identifier]),
            float(means.loc["predicted", identifier]),
        )
        observed = float(means.loc["observed", identifier]) if "observed" in means.index else None
        row = {
            "id": str(identifier),
            "control": control,
            "predicted": predicted,
            "predicted_delta": predicted - control,
            "observed": observed,
            "observed_delta": None if observed is None else observed - control,
        }
        if coverage is not None:
            entry = coverage.get(str(identifier), {})
            row.update(
                coverage=_number(entry.get("gene_fraction"), optional=True),
                evidence_level=entry.get("evidence_level", ""),
            )
        rows.append(row)
    return rows


def export_table(container: Any, run_id: str, table: str, population: str = "original") -> tuple[bytes, str]:
    if table not in {"genes", "tasks", "reactions"}:
        raise CellStateUnavailable("Unknown export table")
    record, root, manifest, sha = _sources(container, run_id)
    metadata = table_metadata(container, run_id, population)
    if population == "comparison":
        comparison = load_comparison(container.settings.project_root, run_id)
        if not comparison:
            raise CellStateUnavailable("Matched comparison is unavailable")
        if table == "reactions":
            folder = container.settings.project_root / "data/derived/comparisons" / run_id
            comparison_manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            expected = comparison_manifest.get("outputs", {}).get("reaction_scores.csv")
            path = _comparison_checked(folder, "reaction_scores.csv", expected)
            rows = _metabolic_rows(path)
            _comparison_checked(folder, "reaction_scores.csv", expected)
        else:
            rows = comparison[table]
        columns = [
            "id",
            "control",
            "predicted",
            "observed",
            "predicted_delta",
            "observed_delta",
            "absolute_error",
        ]
        if table == "reactions":
            columns.remove("absolute_error")
        if table == "tasks":
            columns += [
                "coverage",
                "evidence_level",
                "missing_genes",
                "coverage_source",
                "input_scope",
                "score_structure_id",
                "same_score_structure_task_count",
            ]
    elif table == "genes":
        with _file(root, manifest, "gene_deltas.csv").open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            columns = reader.fieldnames or []
            if not {"gene", "control", "predicted", "predicted_delta"}.issubset(columns):
                raise CellStateUnavailable("Gene table has an unsupported schema")
            rows = list(reader)
    else:
        coverage = None
        if table == "tasks" and "metabolic_coverage.csv" in manifest.get("outputs", {}):
            with _file(root, manifest, "metabolic_coverage.csv").open(
                encoding="utf-8-sig", newline=""
            ) as stream:
                coverage = {row["task"]: row for row in csv.DictReader(stream)}
        rows = _metabolic_rows(
            _file(root, manifest, "metabolic_task_scores.csv" if table == "tasks" else "reaction_scores.csv"),
            coverage,
        )
        columns = ["id", "control", "predicted", "predicted_delta", "observed", "observed_delta"]
        if coverage is not None:
            columns += ["coverage", "evidence_level"]
    seen = set()
    for row in rows:
        identifier = str(row.get("gene", row.get("id", "")))
        if not identifier or identifier in seen:
            raise CellStateUnavailable("Missing or duplicate export identifier")
        seen.add(identifier)
        for key in ("control", "predicted", "predicted_delta"):
            _number(row.get(key))
        for key in ("observed", "observed_delta", "absolute_error"):
            if key in row:
                _number(row[key], optional=True)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(columns) + METADATA_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    extra = {key: metadata.get(key) for key in METADATA_COLUMNS}
    extra["units"] = metadata["units"][table]
    for row in rows:
        writer.writerow({**row, **extra})
    for name in (
        "expression_contract.json",
        "task_trace.json",
        "official_completeness.json",
        "summary.json",
        "gene_deltas.csv",
        "metabolic_task_scores.csv",
        "reaction_scores.csv",
        "metabolic_coverage.csv",
    ):
        if name in manifest.get("outputs", {}):
            _file(root, manifest, name)
    _checked(root / "manifest.json", sha)
    if population == "comparison":
        load_comparison(container.settings.project_root, run_id)
    filename = f"{run_id}_{population}_{table}_mean_per_source.csv"
    return ("\ufeff" + stream.getvalue()).encode("utf-8"), filename
