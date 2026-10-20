"""Gene and task availability from verified panels; no model inference or expression scores."""

import re
from functools import lru_cache
from typing import Any

from backend.app.services.completeness import compute_official_completeness
from backend.app.services.task_trace import associations, task_metadata


@lru_cache(maxsize=8)
def cached_completeness(genes: tuple[str, ...], database_root: str, manifest_sha256: str) -> dict[str, Any]:
    # Callers still verify assets on each request; a changed manifest selects a new cache key.
    from pathlib import Path

    from backend.app.services.scientific_analysis import _load_frozen_database

    database, version = _load_frozen_database(Path(database_root))
    if database["_celllens_provenance"]["manifest_sha256"] != manifest_sha256:
        raise ValueError("Database changed while computing coverage")
    return compute_official_completeness(list(genes), database, version)


def coverage_catalog(
    panel: list[str], database: dict[str, Any], report: dict[str, Any], identity: Any = None
) -> dict[str, Any]:
    """Enrich official availability with names and frozen knowledge associations."""
    present = set(panel)
    if len(present) != len(panel) or len(panel) != report["panel_gene_count"]:
        raise ValueError("Gene panel does not match the saved coverage report")
    reaction_genes = {}
    for _, row in database["rxn_info"].iterrows():
        reaction_genes[str(row["Reaction"])] = {
            token
            for token in re.findall(r"[^\s(),]+", str(row["GPR-symbol"]).upper())
            if token not in {"AND", "OR"}
        }
    all_genes = set().union(*reaction_genes.values())
    gene_tasks: dict[str, list[str]] = {gene: [] for gene in all_genes}
    gene_reactions = {
        gene: sorted(identifier for identifier, genes in reaction_genes.items() if gene in genes)
        for gene in all_genes
    }
    tasks = []
    for row in report["tasks"]:
        required = set().union(
            *(
                reaction_genes.get(identifier, set())
                for identifier in associations(database["task_by_rxn"], row["id"])
            )
        )
        # The list must use the same GPR scope as the official completeness calculation.
        if len(required) != row["n_genes_all"] or len(required & present) != row["n_present_all"]:
            raise ValueError("Task gene associations differ from official coverage")
        for gene in required:
            gene_tasks[gene].append(row["id"])
        status = (
            "unmapped"
            if not required
            else "full"
            if required <= present
            else "partial"
            if required & present
            else "absent"
        )
        tasks.append(
            {
                **row,
                **task_metadata(database, row["id"]),
                "coverage_status": status,
                "present_genes_all": ";".join(sorted(required & present)),
            }
        )
    genes = []
    for symbol in sorted(all_genes):
        metadata = identity.document["database_genes"].get(symbol, {}) if identity is not None else {}
        genes.append(
            {
                "symbol": symbol,
                "approved_symbol": metadata.get("approved_symbol", symbol),
                "hgnc_id": metadata.get("hgnc_id"),
                "in_panel": symbol in present,
                "tasks": sorted(gene_tasks[symbol]),
                "reactions": gene_reactions[symbol],
            }
        )
    summary = report["overall_summary"]
    if (
        len(all_genes) != summary["n_genes_in_db_total"]
        or len(all_genes & present) != summary["n_genes_in_db_present_in_adata"]
    ):
        raise ValueError("Gene catalogue differs from official coverage")
    return {**report, "genes": genes, "tasks": tasks}
