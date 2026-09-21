from collections.abc import Iterable
from dataclasses import dataclass

from backend.app.core.errors import ScientificContractError


@dataclass(frozen=True)
class GeneAlignment:
    genes: list[str]
    missing_from_prediction: list[str]
    missing_from_control: list[str]


def normalize_gene_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _normalized_unique(symbols: Iterable[str], label: str) -> list[str]:
    normalized = [normalize_gene_symbol(item) for item in symbols]
    duplicates = sorted({item for item in normalized if normalized.count(item) > 1})
    if duplicates:
        raise ScientificContractError(f"Duplicate canonical genes in {label}: {duplicates[:10]}")
    return normalized


def align_gene_names(control_genes: Iterable[str], predicted_genes: Iterable[str]) -> GeneAlignment:
    control = _normalized_unique(control_genes, "control")
    predicted = _normalized_unique(predicted_genes, "prediction")
    predicted_set = set(predicted)
    control_set = set(control)
    common = [gene for gene in control if gene in predicted_set]
    if not common:
        raise ScientificContractError("Control and prediction have no genes in common")
    return GeneAlignment(
        genes=common,
        missing_from_prediction=[gene for gene in control if gene not in predicted_set],
        missing_from_control=[gene for gene in predicted if gene not in control_set],
    )


def align_anndata(control, predicted):
    """Return copied AnnData views on an ordered intersection; never zero-fill missing genes."""
    control_symbols = control.var.get("gene_symbol", control.var_names).astype(str).tolist()
    predicted_symbols = predicted.var.get("gene_symbol", predicted.var_names).astype(str).tolist()
    alignment = align_gene_names(control_symbols, predicted_symbols)
    control_map = {normalize_gene_symbol(gene): i for i, gene in enumerate(control_symbols)}
    predicted_map = {normalize_gene_symbol(gene): i for i, gene in enumerate(predicted_symbols)}
    control_view = control[:, [control_map[gene] for gene in alignment.genes]].copy()
    predicted_view = predicted[:, [predicted_map[gene] for gene in alignment.genes]].copy()
    control_view.var_names = alignment.genes
    predicted_view.var_names = alignment.genes
    return control_view, predicted_view, alignment
