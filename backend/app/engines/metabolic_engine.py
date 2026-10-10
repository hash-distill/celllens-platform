from dataclasses import dataclass
from typing import Any

import pandas as pd

from backend.app.core.errors import InsufficientCoverageError, ScientificContractError
from backend.app.services.expression_scale import validate_expression


@dataclass(frozen=True)
class MetabolicResult:
    task_scores: pd.DataFrame
    reaction_scores: pd.DataFrame
    determinant_genes: pd.DataFrame
    completeness: pd.DataFrame
    database_version: str


class ScCellFieEngine:
    def __init__(self, *, organism: str = "human", threshold_key: str = "sccellfie_threshold"):
        self.organism = organism
        self.threshold_key = threshold_key

    def run(
        self,
        adata: Any,
        *,
        database: dict[str, Any],
        database_version: str,
        completeness: pd.DataFrame,
    ) -> MetabolicResult:
        if adata.n_vars == 0:
            raise InsufficientCoverageError("No expression genes are available for metabolic analysis")
        if (
            adata.uns.get("celllens_expression", {}).get("scale") != "cp10k"
            or adata.uns.get("normalization", {}).get("method") != "total_counts"
            or adata.uns.get("normalization", {}).get("target_sum") != 10_000
        ):
            raise ScientificContractError(
                "scCellFie requires declared CP10K expression; normalization is frozen"
            )
        validate_expression(adata.X)
        thresholds = database.get("thresholds")
        if not isinstance(thresholds, pd.DataFrame) or self.threshold_key not in thresholds.columns:
            raise ScientificContractError(
                f"Frozen scCellFie database has no threshold column {self.threshold_key!r}"
            )
        try:
            import sccellfie
        except ImportError as exc:
            raise ScientificContractError("Install the 'model' extra to run scCellFie") from exc
        # scCellFie ships no return annotation, so assert the documented shape here.
        results: Any = sccellfie.run_sccellfie_pipeline(
            adata,
            organism=self.organism,
            sccellfie_db=database,
            process_by_group=False,
            threshold_key=self.threshold_key,
            # Cross-source KNN smoothing would leak observed/control information into predictions.
            smooth_cells=False,
            disable_pbar=True,
            save_folder=None,
            save_filename=None,
            verbose=False,
        )
        if not isinstance(results, dict) or "adata" not in results:
            raise ScientificContractError("scCellFie did not return an AnnData result")
        output = results["adata"]
        tasks = output.metabolic_tasks.to_df()
        reactions = output.reactions.to_df()
        determinant = _determinant_gene_frame(output.uns.get("Rxn-Max-Genes", {}))
        if tasks.empty or tasks.isna().any().any() or reactions.isna().any().any():
            raise ScientificContractError("scCellFie returned empty or NaN score matrices")
        return MetabolicResult(tasks, reactions, determinant, completeness.copy(), database_version)


def _determinant_gene_frame(payload: Any) -> pd.DataFrame:
    if isinstance(payload, pd.DataFrame):
        return payload.copy()
    if isinstance(payload, dict):
        return pd.DataFrame.from_dict(payload, orient="index")
    return pd.DataFrame()
