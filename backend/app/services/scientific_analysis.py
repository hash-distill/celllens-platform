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
    ):
        self.database_root = database_root
        self.metabolic_engine = metabolic_engine or ScCellFieEngine()
        self.max_projection_points = max_projection_points

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

        # STATE writes gene-space predictions into obsm[embed_key] when the model is
        # registered with an embed_key, leaving .X untouched. Without this the predicted
        # matrix would silently equal the control matrix and every delta would be zero.
        embed_key = model.payload.get("embed_key")
        gene_list_path = model.path("gene_list_path") if model.payload.get("gene_list_path") else None
        control = _expression_view(control, embed_key, gene_list_path)
        predicted = _expression_view(predicted, embed_key, gene_list_path)
        observed = _expression_view(observed, embed_key, gene_list_path) if observed is not None else None

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
        atomic_write_json(
            projection_path,
            _projection_document(
                projection_sources,
                seed=request.seed,
                max_points=self.max_projection_points,
            ),
        )

        warnings: list[str] = []
        artifacts = [gene_path, projection_path]
        coverage_summary = None
        metabolic_tasks: list[dict[str, Any]] = []
        try:
            database, database_version = _load_frozen_database(self.database_root)
            completeness = _task_completeness(database, genes)
            coverage_path = output_dir / "metabolic_coverage.csv"
            completeness.to_csv(coverage_path, index=True)
            artifacts.append(coverage_path)
            combined = _combine_sources(ad, control, predicted, observed)
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
            reaction_scores["source"] = combined.obs.loc[
                reaction_scores.index, "celllens_source"
            ].astype(str)
            reaction_scores.to_csv(reaction_path)
            artifacts.extend([task_path, reaction_path])
            metabolic_tasks = _summarize_tasks(task_scores, completeness, observed is not None)
            coverage_summary = _coverage_summary(
                len(genes) / original_control_gene_count,
                database,
                completeness,
                genes,
            )
            if observed is not None:
                metrics = _validation_metrics(task_scores)
                metrics_path = output_dir / "validation_metrics.json"
                atomic_write_json(metrics_path, metrics)
                artifacts.append(metrics_path)
        except (FileNotFoundError, ValueError, ScientificContractError, InsufficientCoverageError) as exc:
            warnings.append(f"Metabolic analysis unavailable: {exc}")

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


def _expression_view(
    adata: Any | None,
    embed_key: str | None,
    gene_list_path: Path | None = None,
) -> Any | None:
    """Return an AnnData whose .X holds the space the model actually predicts in.

    STATE's `tx infer` writes predictions into `obsm[embed_key]` and leaves `.X`
    untouched whenever `--embed-key` is passed. The registered `embed_key` therefore
    tells us which slot carries the predicted expression; for the Replogle HVG models
    that slot holds the highly-variable-gene panel, so the object must also be subset
    to the matching genes. When the key is absent we fall back to `.X` unchanged.
    """
    if adata is None or not embed_key or embed_key not in adata.obsm:
        return adata
    matrix = np.asarray(adata.obsm[embed_key])
    expected_genes = _registered_gene_list(gene_list_path, matrix.shape[1])

    symbols = adata.var.get("gene_symbol", adata.var_names).astype(str).tolist()
    canonical = [symbol.strip().upper() for symbol in symbols]
    positions = [canonical.index(gene) for gene in expected_genes if gene in canonical]
    if len(positions) != len(expected_genes):
        missing = [gene for gene in expected_genes if gene not in canonical]
        raise ScientificContractError(
            f"Expression source is missing {len(missing)} registered genes, "
            f"e.g. {missing[:5]}"
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
    matrix = adata.X
    mean = np.asarray(matrix.mean(axis=0)).reshape(-1).astype(float)
    total = float(mean.sum())
    if not np.isfinite(mean).all() or total <= 0:
        raise ScientificContractError("Expression source has invalid or zero total counts")
    return np.log1p(mean / total * 10_000.0)


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
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
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
    try:
        from sccellfie.datasets.database import load_sccellfie_database
    except ImportError as exc:
        raise ScientificContractError("Install the 'model' extra to load scCellFie") from exc
    database = load_sccellfie_database(organism="human", task_folder=str(root))
    required = {"rxn_info", "task_info", "task_by_rxn", "task_by_gene", "rxn_by_gene", "thresholds"}
    if any(database.get(key) is None for key in required):
        raise ValueError("scCellFie database could not be loaded completely")
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
    scores: pd.DataFrame, completeness: pd.DataFrame, has_observed: bool
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
                "label": str(task),
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
        candidates = [
            index for index, (_, matrix) in enumerate(nonempty) if quotas[index] < len(matrix)
        ]
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
        totals = matrix.sum(axis=1, keepdims=True)
        normalized = np.log1p(matrix / np.maximum(totals, 1e-12) * 10_000.0)
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
    return {"method": "seeded-random-projection", "seed": seed, "points": points}
