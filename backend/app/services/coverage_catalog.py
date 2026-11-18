"""Gene and task availability from verified panels; no model inference or expression scores."""

import re
from collections import OrderedDict
from threading import Lock
from typing import Any

from backend.app.services.completeness import compute_official_completeness
from backend.app.services.task_trace import associations, task_metadata

_verified_reports: OrderedDict[tuple, dict[str, Any]] = OrderedDict()
_verified_reports_lock = Lock()


def clear_completeness_cache() -> None:
    with _verified_reports_lock:
        _verified_reports.clear()


def completeness_from_verified_database(
    genes: list[str], database: dict[str, Any], database_version: str, database_root: str
) -> dict[str, Any]:
    """Reuse this request's verified parse instead of reopening all database files."""
    key = (database_root, tuple(genes), database["_celllens_provenance"]["manifest_sha256"], database_version)
    with _verified_reports_lock:
        if key not in _verified_reports:
            report = compute_official_completeness(genes, database, database_version)
            _verified_reports[key] = report
            if len(_verified_reports) > 8:
                _verified_reports.popitem(last=False)
        _verified_reports.move_to_end(key)
        return _verified_reports[key]


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
