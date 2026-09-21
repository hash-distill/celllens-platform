import numpy as np
import pytest
import scipy.sparse as sp

import scripts.extract_replogle_k562 as extractor
from scripts.extract_replogle_k562 import build_anndata


def test_build_anndata_preserves_state_hvg_features():
    rows = np.array([0, 1])
    frame = build_anndata(
        matrix=sp.csr_matrix([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]),
        hvg_matrix=np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32),
        var_names=np.array(["A", "B", "C"], dtype=object),
        perturbations=np.array(["non-targeting", "non-targeting"], dtype=object),
        cell_lines=np.array(["k562", "k562"], dtype=object),
        gem_group=np.array([1, 2]),
        barcodes=np.array(["c1", "c2"], dtype=object),
        rows=rows,
    )

    assert frame.obsm["X_hvg"].shape == (2, 2)
    np.testing.assert_array_equal(frame.obsm["X_hvg"], [[10.0, 20.0], [30.0, 40.0]])


def test_select_registered_hvg_preserves_registered_order():
    matrix = sp.csr_matrix([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])

    selected = extractor.select_registered_hvg(
        matrix,
        np.array(["A", "B", "C"], dtype=object),
        ["C", "A"],
    )

    np.testing.assert_array_equal(selected, [[3.0, 1.0], [6.0, 4.0]])


def test_select_registered_hvg_rejects_missing_gene():
    with pytest.raises(ValueError, match="missing registered HVG"):
        extractor.select_registered_hvg(
            sp.csr_matrix([[1.0, 2.0]]),
            np.array(["A", "B"], dtype=object),
            ["A", "C"],
        )
