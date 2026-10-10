"""Run the public scCellFie dataset completeness API on the full frozen database."""

import hashlib
import inspect
import json
import re
from importlib.metadata import version
from typing import Any

import pandas as pd


def compute_official_completeness(
    genes: list[str], database: dict[str, Any], database_version: str
) -> dict[str, Any]:
    import anndata as ad
    from sccellfie.reports import compute_dataset_completeness

    canonical = [str(gene).strip().upper() for gene in genes]
    if not canonical or any(not gene for gene in canonical):
        raise ValueError("Completeness requires a non-empty gene panel")
    if len(set(canonical)) != len(canonical):
        raise ValueError("Duplicate canonical genes in completeness panel")
    info = database["rxn_info"]
    if info["Reaction"].duplicated().any():
        raise ValueError("Duplicate reaction identifiers in frozen database")
    # Keep every original reaction. Filtering the DB first would hide absent genes.
    rules = {
        str(row["Reaction"]): re.sub(
            r"\b(?:AND|OR)\b", lambda match: match.group().lower(), str(row["GPR-symbol"]).upper()
        )
        for _, row in info.iterrows()
    }
    if info["GPR-symbol"].isna().any():
        raise ValueError("Missing GPR rule in frozen database")
    # Dataset completeness reads var_names only; no invented expression values.
    panel = ad.AnnData(shape=(0, len(canonical)), var=pd.DataFrame(index=pd.Index(canonical)))
    report: Any = compute_dataset_completeness(
        panel, rules, database["task_by_rxn"], metric="fraction_zeroed", threshold=1.0, disable_pbar=True
    )

    def rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
        # pandas serialisation handles numpy scalars; strict JSON disallows NaN.
        values = json.loads(json.dumps(frame.to_dict(orient="records"), allow_nan=False))
        return [
            {"id": str(identifier), **value} for identifier, value in zip(frame.index, values, strict=True)
        ]

    return {
        "schema_version": 1,
        "method": "sccellfie.reports.compute_dataset_completeness",
        "package_version": version("sccellfie"),
        "implementation_sha256": hashlib.sha256(
            inspect.getsource(compute_dataset_completeness).encode()
        ).hexdigest(),
        "parameters": {"metric": "fraction_zeroed", "threshold": 1.0, "scope": "dataset"},
        "database_version": database_version,
        "database_provenance": database["_celllens_provenance"],
        "panel_gene_count": len(canonical),
        "overall_summary": json.loads(
            json.dumps(report["overall_summary"].to_dict(orient="records"), allow_nan=False)
        )[0],
        "tasks": rows(report["task_completeness"]),
        "reactions": rows(report["reaction_completeness"]),
        "warnings": [
            "Dataset completeness measures gene availability, not prediction accuracy or validation.",
            "Essential genes use single-gene ablation on a uniform reference, not measured essentiality.",
            "Empty essential sets return 1; inspect n_genes_essential before interpretation.",
            "Single-gene impact sums do not prove joint missing-gene effects.",
        ],
    }
