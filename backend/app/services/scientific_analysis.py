import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.app.core.errors import InsufficientCoverageError, ScientificContractError
from backend.app.core.registry import RegistryEntry
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.engines.evidence_engine import compare_task_deltas
from backend.app.engines.metabolic_engine import ScCellFieEngine
from backend.app.schemas import CreateRunRequest
from backend.app.services.completeness import compute_official_completeness
from backend.app.services.expression_scale import (
    ANALYSIS_VERSION,
    linear_cp10k,
    mark_cp10k,
    prepare_log_expression,
    require_scale,
    validate_expression,
)
from backend.app.services.expression_validation import build_expression_validation
from backend.app.services.gene_identity import GeneIdentityAdapter
from backend.app.services.task_trace import build_task_trace, task_metadata


@dataclass(frozen=True)
class AnalysisResult:
    summary: dict[str, Any]
    artifacts: list[Path]


class ScientificAnalysisService:
    def __init__(
        self,
        database_root: Path,
        metabolic_engine: ScCellFieEngine | None = None,
        *,
        max_projection_points: int = 12_000,
        gene_identity_root: Path | None = None,
    ):
        self.database_root = database_root
        self.metabolic_engine = metabolic_engine or ScCellFieEngine()
        self.max_projection_points = max_projection_points
        self.gene_identity_root = gene_identity_root

    def run(
        self,
        run_id: str,
        request: CreateRunRequest,
        model: RegistryEntry,
        dataset: RegistryEntry,
        predicted_path: Path,
        output_dir: Path,
    ) -> AnalysisResult:
        try:
            import anndata as ad
        except ImportError as exc:
            raise ScientificContractError("Install the 'model' extra to analyse AnnData") from exc

        control = ad.read_h5ad(dataset.path("control_path"))
        predicted = ad.read_h5ad(predicted_path)
        predicted, population_selection = _select_prediction_population(
            predicted, model.payload.get("perturbation_column"), request.perturbation
        )
        observed = None
        if request.mode == "validation":
            observed = ad.read_h5ad(dataset.path("observed_path"))
            perturbation_column = model.payload.get("perturbation_column")
            if perturbation_column and perturbation_column in observed.obs:
                mask = observed.obs[perturbation_column].astype(str).str.upper() == request.perturbation
                observed = observed[mask].copy()
            if observed.n_obs == 0:
                raise ScientificContractError(
                    "Validation dataset has no cells for the requested perturbation"
                )

        control_scale = require_scale(dataset.payload.get("expression_scale"))
        predicted_scale = require_scale(model.payload.get("expression_scale"))
        total_counts_key = dataset.payload.get("total_counts_key")
        # Convert the full source before selecting HVGs; counts denominators must
        # describe the full library, not the retained prediction panel.
        control = prepare_log_expression(control, control_scale, total_counts_key=total_counts_key)
        predicted = prepare_log_expression(
            predicted, predicted_scale, total_counts_key=model.payload.get("total_counts_key")
        )
        if observed is not None:
            observed = prepare_log_expression(observed, control_scale, total_counts_key=total_counts_key)

        # STATE writes gene-space predictions into obsm[embed_key] when the model is
        # registered with an embed_key, leaving .X untouched. Without this the predicted
        # matrix would silently equal the control matrix and every delta would be zero.
        embed_key = model.payload.get("expression_key") or model.payload.get("embed_key")
        strict_expression_slot = bool(model.payload.get("expression_key"))
        gene_list_path = model.path("gene_list_path") if model.payload.get("gene_list_path") else None
        control = _expression_view(control, embed_key, gene_list_path, strict=strict_expression_slot)
        predicted = _expression_view(predicted, embed_key, gene_list_path, strict=bool(embed_key))
        observed = _expression_view(observed, embed_key, gene_list_path, strict=strict_expression_slot)
        for source in (control, predicted, observed):
            if source is not None:
                validate_expression(source.X)
        validation_population = None
        if observed is not None:
            control, predicted, observed, validation_population = _match_validation_batches(
                control, predicted, observed, dataset.payload.get("validation_batch_key")
            )

        # obsm may hold the model's expression rather than .X. Canonicalize that
        # slot too; the active ST-HVG contract already uses log1p_cp10k.
        if embed_key and embed_key != "X":
            for source, scale in (
                (control, control_scale),
                (predicted, predicted_scale),
                (observed, control_scale),
            ):
                if source is not None and scale != "log1p_cp10k":
                    raise ScientificContractError("obsm expression requires log1p_cp10k; adapt it explicitly")

        identity_path = None
        if self.gene_identity_root is not None:
            adapter = GeneIdentityAdapter.load(self.gene_identity_root, self.database_root)
            control, control_identity = adapter.adapt(control)
            predicted, predicted_identity = adapter.adapt(predicted)
            identity_reports = {"control": control_identity, "predicted": predicted_identity}
            if observed is not None:
                observed, observed_identity = adapter.adapt(observed)
                identity_reports["observed"] = observed_identity
            identity_path = output_dir / "gene_identity.json"
            atomic_write_json(
                identity_path, {"schema_version": 1, "run_id": run_id, "sources": identity_reports}
            )

        aligned, genes, original_control_gene_count = _align_sources(control, predicted, observed)
        control, predicted, observed = aligned
        control_mean = _normalized_gene_mean(control)
        predicted_mean = _normalized_gene_mean(predicted)
        observed_mean = _normalized_gene_mean(observed) if observed is not None else None
        gene_table = pd.DataFrame(
            {
                "control": control_mean,
                "predicted": predicted_mean,
                "predicted_delta": predicted_mean - control_mean,
            },
            index=pd.Index(genes, dtype="object"),
        )
        if observed_mean is not None:
            gene_table["observed"] = observed_mean
            gene_table["observed_delta"] = observed_mean - control_mean
        gene_table.index.name = "gene"
        gene_path = output_dir / "gene_deltas.csv"
        gene_table.to_csv(gene_path)

        contract_path = output_dir / "expression_contract.json"
        atomic_write_json(
            contract_path,
            {
                "analysis_version": ANALYSIS_VERSION,
                "run_id": run_id,
                "source_scales": {
                    "control": control_scale,
                    "predicted": predicted_scale,
                    "observed": control_scale if observed is not None else None,
                },
                "gene_units": "mean(log1p(CP10K))",
                "metabolic_units": "CP10K, inverse log1p without panel renormalization",
                "predicted_values_are_measured_counts": False,
                "gene_count": len(genes),
                "population_selection": population_selection,
                "validation_population": validation_population,
            },
        )

        top_genes = []
        delta_values = gene_table["predicted_delta"].to_numpy(dtype=float)
        top_positions = np.argsort(np.abs(delta_values))[-20:][::-1]
        for position in top_positions:
            gene = gene_table.index[int(position)]
            row = gene_table.iloc[int(position)]
            top_genes.append(
                {
                    "id": str(gene),
                    "label": str(gene),
                    "predicted_delta": float(row["predicted_delta"]),
                    "observed_delta": _optional_float(row.get("observed_delta")),
                    "coverage": 1.0,
                    "evidence_level": "supported",
                    "determinant_genes": [str(gene)],
                }
            )

        projection_path = output_dir / "projection.json"
        projection_sources = [
            ("control", _dense_matrix(control.X)),
            ("predicted", _dense_matrix(predicted.X)),
        ]
        if observed is not None:
            projection_sources.append(("observed", _dense_matrix(observed.X)))
        projection = _projection_document(
            projection_sources,
            seed=request.seed,
            max_points=self.max_projection_points,
            input_scale="log1p_cp10k",
        )
        projection["population_selection"] = population_selection
        atomic_write_json(projection_path, projection)

        warnings: list[str] = []
        artifacts = [gene_path, projection_path, contract_path]
        validation = None
        if observed is not None:
            validation, validation_artifacts = build_expression_validation(
                control, predicted, observed, output_dir
            )
            artifacts.extend(validation_artifacts)
            validation["population_matching"] = validation_population
        if identity_path is not None:
            artifacts.append(identity_path)
        coverage_summary = None
        metabolic_tasks: list[dict[str, Any]] = []
        try:
            database, database_version = _load_frozen_database(self.database_root)
            official = compute_official_completeness(genes, database, database_version)
            official.update(run_id=run_id, source_gene_sha256=file_sha256(gene_path))
            official_path = output_dir / "official_completeness.json"
            atomic_write_json(official_path, official)
            artifacts.append(official_path)
            completeness = _task_completeness(database, genes)
            coverage_path = output_dir / "metabolic_coverage.csv"
            completeness.to_csv(coverage_path, index=True)
            artifacts.append(coverage_path)
            combined = _combine_sources(
                ad,
                linear_cp10k(control),
                linear_cp10k(predicted),
                linear_cp10k(observed) if observed is not None else None,
            )
            mark_cp10k(combined)  # AnnData concat drops uns by default.
            if _contains_negative(combined.X):
                raise ScientificContractError("scCellFie requires non-negative count-like expression values")
            result = self.metabolic_engine.run(
                combined,
                database=database,
                database_version=database_version,
                completeness=completeness,
            )
            task_scores = result.task_scores.copy()
            task_scores["source"] = combined.obs.loc[task_scores.index, "celllens_source"].astype(str)
            task_path = output_dir / "metabolic_task_scores.csv"
            task_scores.to_csv(task_path)
            reaction_path = output_dir / "reaction_scores.csv"
            reaction_scores = result.reaction_scores.copy()
            reaction_scores["source"] = combined.obs.loc[reaction_scores.index, "celllens_source"].astype(str)
            reaction_scores.to_csv(reaction_path)
            artifacts.extend([task_path, reaction_path])
            metabolic_tasks = _summarize_tasks(task_scores, completeness, observed is not None, database)
            trace_path = output_dir / "task_trace.json"
            atomic_write_json(
                trace_path,
                build_task_trace(
                    run_id,
                    database,
                    database_version,
                    task_scores,
                    reaction_scores,
                    gene_table,
                    completeness,
                ),
            )
            artifacts.append(trace_path)
            coverage_summary = _coverage_summary(
                len(genes) / original_control_gene_count,
                database,
                completeness,
                genes,
            )
            if observed is not None:
                metrics = _validation_metrics(task_scores)
                assert validation is not None
                validation.update(metrics)  # Preserve legacy task metrics; label their scope explicitly.
                validation["metabolic"] = metrics
        except (FileNotFoundError, ValueError, ScientificContractError, InsufficientCoverageError) as exc:
            warnings.append(f"Metabolic analysis unavailable: {exc}")

        if validation is not None:
            metrics_path = output_dir / "validation_metrics.json"
            atomic_write_json(metrics_path, validation)
            artifacts.append(metrics_path)

        summary = {
            "run_id": run_id,
            "status": "completed",
            "stage_progress": 100,
            "cell_line": request.cell_line,
            "perturbation": request.perturbation,
            "coverage": coverage_summary,
            "top_genes": top_genes,
            "metabolic_tasks": metabolic_tasks,
            "warnings": warnings,
            "error_code": None,
        }
        return AnalysisResult(summary=summary, artifacts=artifacts)


def _select_prediction_population(
    predicted: Any, perturbation_column: str | None, perturbation: str
) -> tuple[Any, dict[str, Any]]:
    """STATE may emit simulated controls alongside targets; analyse only the requested target."""
    input_count = predicted.n_obs
    metadata: dict[str, Any] = {
        "version": 1,
        "status": "unconfigured",
        "perturbation_column": perturbation_column,
        "perturbation": perturbation,
        "input_prediction_cells": input_count,
    }
    if perturbation_column:
        if perturbation_column not in predicted.obs:
            raise ScientificContractError("Prediction is missing the registered perturbation column")
        labels = predicted.obs[perturbation_column].astype(str).str.strip().str.upper()
        mask = labels == perturbation.strip().upper()
        if not mask.any():
            raise ScientificContractError("Prediction has no cells for the requested perturbation")
        predicted = predicted[mask].copy()
        metadata["status"] = "matched"
    metadata["selected_prediction_cells"] = predicted.n_obs
    metadata["excluded_prediction_cells"] = input_count - predicted.n_obs
    return predicted, metadata


def _expression_view(
    adata: Any | None,
    embed_key: str | None,
    gene_list_path: Path | None = None,
    *,
    strict: bool = False,
) -> Any | None:
    """Return an AnnData whose .X holds the space the model actually predicts in.

    STATE's `tx infer` writes predictions into `obsm[embed_key]` and leaves `.X`
    untouched whenever `--embed-key` is passed. The registered `embed_key` therefore
    tells us which slot carries the predicted expression; for the Replogle HVG models
    that slot holds the highly-variable-gene panel, so the object must also be subset
    to the matching genes. When the key is absent we fall back to `.X` unchanged.
    """
    if adata is None or not embed_key or embed_key == "X":
        return adata
    if embed_key not in adata.obsm:
        if strict:
            raise ScientificContractError(f"Registered expression slot obsm[{embed_key!r}] is missing")
        return adata
    matrix = np.asarray(adata.obsm[embed_key])
    expected_genes = _registered_gene_list(gene_list_path, matrix.shape[1])

    symbols = adata.var.get("gene_symbol", adata.var_names).astype(str).tolist()
    canonical = [symbol.strip().upper() for symbol in symbols]
    positions = [canonical.index(gene) for gene in expected_genes if gene in canonical]
    if len(positions) != len(expected_genes):
        missing = [gene for gene in expected_genes if gene not in canonical]
        raise ScientificContractError(
            f"Expression source is missing {len(missing)} registered genes, e.g. {missing[:5]}"
        )
    if matrix.shape[1] != len(expected_genes):
        raise ScientificContractError(
            f"obsm[{embed_key!r}] has {matrix.shape[1]} columns but the registered gene "
            f"list has {len(expected_genes)} genes"
        )

    view = adata[:, positions].copy()
    view.X = matrix[:, [expected_genes.index(gene) for gene in expected_genes]].copy()
    view.var_names = pd.Index(expected_genes)
    return view


def _registered_gene_list(gene_list_path: Path | None, width: int) -> list[str]:
    if gene_list_path is None or not gene_list_path.is_file():
        raise ScientificContractError(
            "The model registers an embed_key but no gene list is available to map "
            f"the {width} predicted columns onto genes"
        )
    genes = [
        line.strip().upper()
        for line in gene_list_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(genes) != width:
        raise ScientificContractError(
            f"Registered gene list has {len(genes)} genes but the prediction has {width} columns"
        )
    return genes


def _match_validation_batches(control: Any, predicted: Any, observed: Any, batch_key: str | None):
    sources = {"control": control, "predicted": predicted, "observed": observed}
    report = {"batch_key": batch_key, "input_cells": {key: frame.n_obs for key, frame in sources.items()}}
    if batch_key is None:
        report["status"] = "unstratified"
        return control, predicted, observed, report
    if any(batch_key not in frame.obs for frame in sources.values()):
        raise ScientificContractError(f"Registered validation batch column {batch_key!r} is missing")
    common = set.intersection(*(set(frame.obs[batch_key].astype(str)) for frame in sources.values()))
    if not common:
        raise ScientificContractError("Validation populations have no common measured batches")
    matched = {
        key: frame[frame.obs[batch_key].astype(str).isin(common)].copy() for key, frame in sources.items()
    }
    if min(frame.n_obs for frame in matched.values()) < 2:
        raise ScientificContractError("Common-batch validation has fewer than two cells in a population")
    report.update(
        status="common_batches_only",
        common_batches=sorted(common),
        selected_cells={key: frame.n_obs for key, frame in matched.items()},
        limitation="Batch frequencies are not reweighted; unpaired population diagnostic",
    )
    return matched["control"], matched["predicted"], matched["observed"], report


def _align_sources(control: Any, predicted: Any, observed: Any | None):
    sources = [control, predicted] + ([observed] if observed is not None else [])
    symbol_lists: list[list[str]] = []
    for source in sources:
        values = source.var.get("gene_symbol", source.var_names).astype(str).tolist()
        canonical = [value.strip().upper() for value in values]
        if len(canonical) != len(set(canonical)):
            raise ScientificContractError("A source contains duplicate canonical gene symbols")
        symbol_lists.append(canonical)
    common = set(symbol_lists[0])
    for values in symbol_lists[1:]:
        common &= set(values)
    ordered = [gene for gene in symbol_lists[0] if gene in common]
    if not ordered:
        raise ScientificContractError("Expression sources have no genes in common")
    aligned = []
    for source, symbols in zip(sources, symbol_lists, strict=True):
        locations = {gene: index for index, gene in enumerate(symbols)}
        view = source[:, [locations[gene] for gene in ordered]].copy()
        view.var_names = ordered
        aligned.append(view)
    if observed is None:
        aligned.append(None)
    return aligned, ordered, len(symbol_lists[0])


def _normalized_gene_mean(adata: Any) -> np.ndarray:
    if adata.uns.get("celllens_expression", {}).get("scale") != "log1p_cp10k":
        raise ScientificContractError("Gene means require declared log1p_cp10k expression scale")
    matrix = adata.X
    mean = np.asarray(matrix.mean(axis=0)).reshape(-1).astype(float)
    if not np.isfinite(mean).all() or np.any(mean < 0):
        raise ScientificContractError("Expression source has invalid log expression")
    return mean


def _contains_negative(matrix: Any) -> bool:
    if hasattr(matrix, "data") and not isinstance(matrix, np.ndarray):
        return bool(np.any(np.asarray(matrix.data) < 0))
    return bool(np.any(np.asarray(matrix) < 0))


def _combine_sources(ad: Any, control: Any, predicted: Any, observed: Any | None):
    sources = []
    for name, source in (("control", control), ("predicted", predicted), ("observed", observed)):
        if source is None:
            continue
        current = source.copy()
        current.obs["celllens_source"] = name
        sources.append(current)
    return ad.concat(sources, join="inner", merge="same", index_unique="-")


def _load_frozen_database(root: Path) -> tuple[dict[str, Any], str]:
    manifest_path = root / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    document = json.loads(manifest_bytes)
    if not document.get("enabled"):
        raise FileNotFoundError("frozen scCellFie database is not enabled")
    files = document.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("scCellFie manifest has no file hashes")
    for filename, expected in files.items():
        path = (root / filename).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise FileNotFoundError(f"missing scCellFie database file: {filename}")
        if file_sha256(path).lower() != str(expected).lower():
            raise ValueError(f"scCellFie database hash mismatch: {filename}")
    required_files = {
        "Rxn-Info-Recon2-2.json",
        "Task-Info.csv",
        "Task_by_Rxn.csv",
        "Task_by_Gene.csv",
        "Rxn_by_Gene.csv",
        "Thresholds.csv",
    }
    if not required_files.issubset(files):
        raise ValueError("scCellFie manifest must pin all six human database files")
    try:
        from sccellfie.datasets.database import load_sccellfie_database
    except ImportError as exc:
        raise ScientificContractError("Install the 'model' extra to load scCellFie") from exc
    database = load_sccellfie_database(organism="human", task_folder=str(root))
    required = {"rxn_info", "task_info", "task_by_rxn", "task_by_gene", "rxn_by_gene", "thresholds"}
    if any(database.get(key) is None for key in required):
        raise ValueError("scCellFie database could not be loaded completely")
    # Detect changes between verification and parsing; never attest a different DB snapshot.
    if manifest_path.read_bytes() != manifest_bytes or any(
        file_sha256(root / filename).lower() != str(expected).lower() for filename, expected in files.items()
    ):
        raise ValueError("scCellFie database changed while loading")
    database["_celllens_provenance"] = {
        "manifest_sha256": file_sha256(manifest_path),
        "files": dict(files),
        "source": document.get("source"),
        "organism": document.get("organism", "human"),
    }
    return database, str(document.get("version", "unknown"))


def _task_completeness(database: dict[str, Any], genes: list[str]) -> pd.DataFrame:
    task_by_gene = database["task_by_gene"]
    present = set(genes)
    rows: list[dict[str, Any]] = []
    for task, values in task_by_gene.iterrows():
        required = {str(gene).upper() for gene, value in values.items() if value != 0 and pd.notna(value)}
        fraction = len(required & present) / len(required) if required else 1.0
        level = "supported" if fraction >= 0.8 else "exploratory" if fraction >= 0.6 else "insufficient"
        rows.append(
            {
                "task": str(task),
                "gene_fraction": fraction,
                "evidence_level": level,
                "missing_genes": ";".join(sorted(required - present)),
            }
        )
    return pd.DataFrame.from_records(rows).set_index("task")


def _coverage_summary(
    state_gene_fraction: float,
    database: dict[str, Any],
    completeness: pd.DataFrame,
    genes: list[str],
) -> dict[str, Any]:
    reaction_by_gene = database["rxn_by_gene"]
    database_genes = {str(gene).upper() for gene in reaction_by_gene.columns}
    present = set(genes)
    reaction_fractions = []
    for _, values in reaction_by_gene.iterrows():
        required = {str(gene).upper() for gene, value in values.items() if value != 0 and pd.notna(value)}
        reaction_fractions.append(len(required & present) / len(required) if required else 1.0)
    counts = completeness["evidence_level"].value_counts()
    return {
        "state_gene_fraction": min(1.0, state_gene_fraction),
        "metabolic_gene_fraction": len(database_genes & present) / len(database_genes)
        if database_genes
        else 1.0,
        "reaction_fraction": float(np.mean(reaction_fractions)) if reaction_fractions else 0.0,
        "supported_tasks": int(counts.loc["supported"]) if "supported" in counts.index else 0,
        "exploratory_tasks": int(counts.loc["exploratory"]) if "exploratory" in counts.index else 0,
        "insufficient_tasks": int(counts.loc["insufficient"]) if "insufficient" in counts.index else 0,
    }


def _summarize_tasks(
    scores: pd.DataFrame,
    completeness: pd.DataFrame,
    has_observed: bool,
    database: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    numeric = scores.drop(columns=["source"]).apply(pd.to_numeric, errors="coerce")
    grouped = numeric.groupby(scores["source"], observed=True).mean()
    if "control" not in grouped.index or "predicted" not in grouped.index:
        raise ScientificContractError("scCellFie result lacks control or predicted scores")
    delta = grouped.loc["predicted"] - grouped.loc["control"]
    top = delta.abs().nlargest(20).index
    output = []
    for task in top:
        coverage = (
            float(completeness.loc[str(task), "gene_fraction"]) if str(task) in completeness.index else 0.0
        )
        level = (
            str(completeness.loc[str(task), "evidence_level"])
            if str(task) in completeness.index
            else "insufficient"
        )
        observed_delta = None
        if has_observed and "observed" in grouped.index:
            observed_delta = float(grouped.loc["observed", task] - grouped.loc["control", task])
        output.append(
            {
                "id": str(task),
                **(task_metadata(database, str(task)) if database is not None else {"label": str(task)}),
                "control": _optional_float(grouped.loc["control", task]),
                "predicted": _optional_float(grouped.loc["predicted", task]),
                "predicted_delta": float(delta[task]),
                "observed_delta": observed_delta,
                "coverage": coverage,
                "evidence_level": level,
                "determinant_genes": [],
            }
        )
    return output


def _validation_metrics(scores: pd.DataFrame) -> dict[str, Any]:
    numeric = scores.drop(columns=["source"]).apply(pd.to_numeric, errors="coerce")
    grouped = numeric.groupby(scores["source"], observed=True).mean()
    metrics = compare_task_deltas(grouped.loc["control"], grouped.loc["predicted"], grouped.loc["observed"])
    return {
        "spearman": metrics.spearman,
        "mae": metrics.mae,
        "direction_agreement": metrics.direction_agreement,
        "top_k_overlap": metrics.top_k_overlap,
        "valid_task_count": metrics.valid_task_count,
        "excluded_task_count": metrics.excluded_task_count,
    }


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _dense_matrix(matrix: Any) -> np.ndarray:
    return matrix.toarray() if hasattr(matrix, "toarray") else np.asarray(matrix)


def _projection_document(
    sources: list[tuple[str, np.ndarray]],
    *,
    seed: int,
    max_points: int,
    input_scale: str = "raw_counts",
) -> dict[str, Any]:
    """Create a deterministic, bounded 2-D random projection with stratified sampling."""
    nonempty = [(name, np.asarray(matrix, dtype=np.float32)) for name, matrix in sources if len(matrix)]
    total = sum(len(matrix) for _, matrix in nonempty)
    budget = min(max_points, total)
    if not nonempty or budget < 1:
        return {"method": "seeded-random-projection", "seed": seed, "points": []}

    raw = [budget * len(matrix) / total for _, matrix in nonempty]
    quotas = [min(len(matrix), int(value)) for value, (_, matrix) in zip(raw, nonempty, strict=True)]
    if budget >= len(nonempty):
        quotas = [max(1, quota) for quota in quotas]
    while sum(quotas) > budget:
        index = max(range(len(quotas)), key=lambda item: quotas[item])
        quotas[index] -= 1
    while sum(quotas) < budget:
        candidates = [index for index, (_, matrix) in enumerate(nonempty) if quotas[index] < len(matrix)]
        index = max(candidates, key=lambda item: raw[item] - quotas[item])
        quotas[index] += 1

    rng = np.random.default_rng(seed)
    sampled: list[tuple[str, np.ndarray, np.ndarray]] = []
    for quota, (name, matrix) in zip(quotas, nonempty, strict=True):
        indices = np.sort(rng.choice(len(matrix), size=quota, replace=False))
        sampled.append((name, indices, matrix[indices]))

    width = sampled[0][2].shape[1]
    basis = rng.normal(size=(width, 2)).astype(np.float32) / np.sqrt(max(width, 1))
    points: list[dict[str, Any]] = []
    for name, indices, matrix in sampled:
        if input_scale == "log1p_cp10k":
            normalized = matrix
        elif input_scale == "raw_counts":
            # Legacy synthetic demo callers explicitly retain their generator contract.
            totals = matrix.sum(axis=1, keepdims=True)
            normalized = np.log1p(matrix / np.maximum(totals, 1e-12) * 10_000.0)
        else:
            raise ScientificContractError(f"Unsupported projection expression scale: {input_scale}")
        coordinates = normalized @ basis
        for cell_index, (x_value, y_value) in zip(indices, coordinates, strict=True):
            points.append(
                {
                    "x": float(x_value),
                    "y": float(y_value),
                    "source": name,
                    "cell_index": int(cell_index),
                }
            )
    return {"method": "seeded-random-projection", "seed": seed, "input_scale": input_scale, "points": points}
