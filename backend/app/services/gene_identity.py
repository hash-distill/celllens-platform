"""Frozen HGNC identity adaptation. Never changes or fills expression values."""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.core.errors import ScientificContractError
from backend.app.core.run_manifest import file_sha256


def build_identity_document(rxn_info: pd.DataFrame, hgnc: pd.DataFrame) -> dict[str, Any]:
    required: dict[str, set[str]] = defaultdict(set)
    for _, row in rxn_info.iterrows():
        ids = re.findall(r"HGNC:\d+", str(row["GPR"]))
        tokens = re.findall(r"[^\s(),]+", str(row["GPR-symbol"]))
        symbols = [token for token in tokens if token.lower() not in {"and", "or"}]
        id_rule = re.sub(r"HGNC:\d+", "GENE", str(row["GPR"]))
        symbol_rule = re.sub(
            r"[^\s(),]+",
            lambda m: m[0] if m[0].lower() in {"and", "or"} else "GENE",
            str(row["GPR-symbol"]),
        )
        if len(ids) != len(symbols) or id_rule != symbol_rule:
            raise ScientificContractError("HGNC and symbol GPR structure differs")
        for symbol, identifier in zip(symbols, ids, strict=True):
            required[symbol.upper()].add(identifier)

    approved = dict(zip(hgnc["hgnc_id"], hgnc["symbol"].str.upper(), strict=True))
    lookups: dict[str, dict[str, set[str]]] = {
        label: defaultdict(set) for label in ("approved", "previous", "alias")
    }
    for _, row in hgnc.iterrows():
        identifier = str(row["hgnc_id"])
        lookups["approved"][str(row["symbol"]).upper()].add(identifier)
        for label, field in (("previous", "prev_symbol"), ("alias", "alias_symbol")):
            for symbol in str(row[field]).split("|"):
                if symbol:
                    lookups[label][symbol.upper()].add(identifier)
    lookup = {}
    for label, table in lookups.items():
        for symbol, identifiers in table.items():
            if symbol not in lookup:
                lookup[symbol] = {"hgnc_ids": sorted(identifiers), "method": label}
    database = {}
    for symbol, identifiers in required.items():
        if len(identifiers) != 1:
            raise ScientificContractError(f"Non-unique database identity: {symbol}")
        identifier = next(iter(identifiers))
        if identifier not in approved:
            raise ScientificContractError(f"HGNC snapshot lacks database identity: {identifier}")
        database[symbol] = {"hgnc_id": identifier, "approved_symbol": approved[identifier]}
    if len({row["hgnc_id"] for row in database.values()}) != len(database):
        raise ScientificContractError("Database contains duplicate HGNC identities")
    return {
        "schema_version": 1,
        "database_genes": database,
        "approved_by_id": approved,
        "symbol_lookup": lookup,
    }


class GeneIdentityAdapter:
    def __init__(self, document: dict[str, Any], *, provenance: dict[str, Any]):
        self.document = document
        self.provenance = provenance
        self.by_id = {row["hgnc_id"]: symbol for symbol, row in document["database_genes"].items()}

    @classmethod
    def load(cls, root: Path, database_root: Path) -> "GeneIdentityAdapter":
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if manifest["database_manifest_sha256"] != file_sha256(database_root / "manifest.json"):
            raise ScientificContractError("Gene identity database manifest hash mismatch")
        path = root / "human.json"
        if file_sha256(path) != manifest["files"]["human.json"]:
            raise ScientificContractError("Gene identity asset hash mismatch")
        # A manifest match alone does not verify the database files on disk.
        db_manifest = json.loads((database_root / "manifest.json").read_text(encoding="utf-8"))
        for filename, digest in db_manifest["files"].items():
            if file_sha256(database_root / filename) != digest:
                raise ScientificContractError(f"Gene identity database file hash mismatch: {filename}")
        return cls(
            json.loads(path.read_text(encoding="utf-8")),
            provenance={
                "manifest_sha256": file_sha256(root / "manifest.json"),
                "mapping_sha256": file_sha256(path),
                **manifest,
            },
        )

    def resolve(self, symbol: str, identifier: str | None = None) -> dict[str, Any]:
        symbol = str(symbol).strip().upper()
        lookup = self.document["symbol_lookup"].get(symbol)
        candidates = lookup["hgnc_ids"] if lookup else []
        if identifier:
            if identifier not in self.document["approved_by_id"]:
                raise ScientificContractError(f"Unknown HGNC ID: {identifier}")
            if candidates and identifier not in candidates:
                raise ScientificContractError(f"HGNC ID conflicts with gene symbol: {symbol}")
            method = "explicit_hgnc_id"
        elif len(candidates) == 1:
            identifier = candidates[0]
            method = lookup["method"]
        elif len(candidates) > 1 and any(item in self.by_id for item in candidates):
            raise ScientificContractError(f"Ambiguous metabolic gene symbol: {symbol}")
        else:
            method = "unresolved"
        return {
            "source_symbol": symbol,
            "hgnc_id": identifier,
            "approved_symbol": self.document["approved_by_id"].get(identifier),
            "analysis_symbol": self.by_id.get(identifier, symbol),
            "method": method,
        }

    def adapt(self, adata: Any) -> tuple[Any, dict[str, Any]]:
        genes = adata.var["gene_symbol"] if "gene_symbol" in adata.var else adata.var_names
        ids = adata.var["hgnc_id"] if "hgnc_id" in adata.var else [None] * adata.n_vars
        columns = [
            self.resolve(gene, str(identifier) if pd.notna(identifier) and identifier else None)
            for gene, identifier in zip(genes, ids, strict=True)
        ]
        names = [row["analysis_symbol"] for row in columns]
        if len(set(names)) != len(names):
            raise ScientificContractError("Duplicate gene identities after HGNC adaptation")
        result = adata.copy()
        result.var["source_gene_symbol"] = [str(gene) for gene in genes]
        result.var["gene_symbol"] = names
        result.var_names = pd.Index(names)
        return result, {
            "provenance": self.provenance,
            "columns": columns,
            "renamed_columns": sum(row["source_symbol"] != row["analysis_symbol"] for row in columns),
            "expression_values_changed": False,
        }
