"""Run-frozen knowledge associations with measured source means, never causal attribution."""

import math
from typing import Any

import pandas as pd


def finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def source_means(scores: pd.DataFrame) -> dict[str, dict[str, float | None]]:
    numeric = scores.drop(columns=["source"]).apply(pd.to_numeric, errors="coerce")
    grouped = numeric.groupby(scores["source"], observed=True).mean()
    output = {}
    for identifier in grouped.columns:
        control = finite(grouped.loc["control", identifier]) if "control" in grouped.index else None
        predicted = finite(grouped.loc["predicted", identifier]) if "predicted" in grouped.index else None
        observed = finite(grouped.loc["observed", identifier]) if "observed" in grouped.index else None
        output[str(identifier)] = {
            "control": control,
            "predicted": predicted,
            "predicted_delta": predicted - control if predicted is not None and control is not None else None,
            "observed_delta": observed - control if observed is not None and control is not None else None,
        }
    return output


def task_metadata(database: dict[str, Any], task_id: str) -> dict[str, Any]:
    table = database["task_info"]
    rows = (
        table[table["Task"].astype(str) == task_id] if "Task" in table else table.loc[table.index == task_id]
    )
    row = rows.iloc[0] if len(rows) else None

    def field(name: str) -> str | None:
        value = row.get(name) if row is not None else None
        return str(value) if value is not None and pd.notna(value) else None

    return {"label": field("Task") or task_id, "category": field("System"), "subcategory": field("Subsystem")}


def associations(table: pd.DataFrame, identifier: str) -> list[str]:
    if identifier not in table.index:
        return []
    return sorted(str(key) for key, value in table.loc[identifier].items() if pd.notna(value) and value != 0)


def build_task_trace(
    run_id: str,
    database: dict[str, Any],
    database_version: str,
    task_scores: pd.DataFrame,
    reaction_scores: pd.DataFrame,
    gene_table: pd.DataFrame,
    completeness: pd.DataFrame,
) -> dict[str, Any]:
    """Snapshot all associations before publication; reads must never consult the live DB."""
    task_values = source_means(task_scores)
    reaction_values = source_means(reaction_scores)
    missing = {"control": None, "predicted": None, "predicted_delta": None, "observed_delta": None}
    tasks: dict[str, Any] = {}
    reactions: dict[str, Any] = {}
    genes: dict[str, Any] = {}
    rxn_info = database["rxn_info"].set_index("Reaction")
    for task_id, values in task_values.items():
        reaction_ids = associations(database["task_by_rxn"], task_id)
        coverage = completeness.loc[task_id] if task_id in completeness.index else None
        tasks[task_id] = {
            "id": task_id,
            **task_metadata(database, task_id),
            **values,
            "coverage": finite(coverage["gene_fraction"]) if coverage is not None else 0.0,
            "evidence_level": str(coverage["evidence_level"]) if coverage is not None else "insufficient",
            "reaction_ids": reaction_ids,
        }
        for reaction_id in reaction_ids:
            if reaction_id in reactions:
                continue
            gene_ids = associations(database["rxn_by_gene"], reaction_id)
            rule = rxn_info.loc[reaction_id].get("GPR-symbol") if reaction_id in rxn_info.index else None
            reactions[reaction_id] = {
                "id": reaction_id,
                "label": reaction_id,
                **reaction_values.get(reaction_id, missing),
                "gene_ids": gene_ids,
                "gene_rule": str(rule) if rule is not None and pd.notna(rule) else None,
            }
            for gene_id in gene_ids:
                row = gene_table.loc[gene_id.upper()] if gene_id.upper() in gene_table.index else None
                genes[gene_id] = {
                    "id": gene_id,
                    "label": gene_id,
                    **{key: finite(row.get(key)) if row is not None else None for key in missing},
                }
    return {
        "schema_version": 1,
        "run_id": run_id,
        "database_version": database_version,
        "database_provenance": database["_celllens_provenance"],
        "relationship_kind": "knowledge_association",
        "determinant_status": "unavailable",
        "determinant_genes": [],
        "score_units": {
            "gene": "mean(log1p(CP10K))",
            "reaction": "scCellFie reaction activity score",
            "task": "scCellFie task activity score",
        },
        "tasks": tasks,
        "reactions": reactions,
        "genes": genes,
        "warnings": [
            "Edges are frozen database knowledge associations, not causal contributions or measured flux.",
            "Determinant genes are unavailable: the engine output has not been validated "
            "for source-specific attribution.",
            "Missing or non-finite run scores are null; gene and metabolic score units differ.",
        ],
    }
