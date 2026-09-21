import pytest

from backend.app.core.errors import ScientificContractError
from backend.app.engines.anndata_adapter import align_gene_names


def test_gene_alignment_uses_intersection_without_zero_fill():
    result = align_gene_names(["A", "B", "C"], ["B", "C", "D"])
    assert result.genes == ["B", "C"]
    assert result.missing_from_prediction == ["A"]
    assert result.missing_from_control == ["D"]


def test_gene_alignment_rejects_duplicate_canonical_names():
    with pytest.raises(ScientificContractError, match="Duplicate canonical genes"):
        align_gene_names(["A", "a"], ["A"])
