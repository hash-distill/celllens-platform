import numpy as np
import pytest
import torch

from backend.app.core.errors import ScientificContractError
from backend.app.engines.se_decode_engine import (
    decoder_inputs,
    positive_log_expression_mean,
    resolve_read_depths,
    validate_query_keys,
)


def test_dataset_coordinates_are_split_once_in_decoder_input():
    cells = torch.tensor([[2.0, 3.0, 9.0]])
    genes = torch.tensor([[5.0, 6.0], [7.0, 8.0]])
    joined = decoder_inputs(cells, genes, read_depth=4.0, cell_dim=2, dataset_dim=1)
    np.testing.assert_array_equal(joined.numpy(), [[[5, 6, 2, 3, 4, 9], [7, 8, 2, 3, 4, 9]]])
    assert joined.shape[-1] == 6


def test_decoder_rejects_wrong_latent_space_and_nonfinite_inputs():
    with pytest.raises(ScientificContractError, match="latent"):
        decoder_inputs(torch.zeros((1, 2057)), torch.zeros((2, 2048)), read_depth=4.0)
    with pytest.raises(ScientificContractError, match="finite"):
        decoder_inputs(torch.full((1, 2058), float("nan")), torch.zeros((2, 2048)), read_depth=4.0)


def test_missing_or_duplicate_query_keys_never_use_zero_embedding_fallback():
    with pytest.raises(ScientificContractError, match="missing"):
        validate_query_keys(["A", "B"], {"A"})
    with pytest.raises(ScientificContractError, match="Duplicate"):
        validate_query_keys(["A", "A"], {"A"})
    validate_query_keys(["A", "B"], {"A", "B"})


def test_per_cell_depths_are_explicit_finite_and_not_broadcast_from_wrong_shapes():
    np.testing.assert_array_equal(resolve_read_depths(4.0, 2), [4.0, 4.0])
    np.testing.assert_allclose(resolve_read_depths(np.array([0.9, 1.1]), 2), [0.9, 1.1])
    with pytest.raises(ScientificContractError, match="shape"):
        resolve_read_depths(np.array([1.0]), 2)
    with pytest.raises(ScientificContractError, match="finite"):
        resolve_read_depths(np.array([1.0, np.nan]), 2)


def test_control_depth_estimator_ignores_true_zeros_without_filling_missing_columns():
    values = np.array([[0, 0.4, 0.8], [0.2, 0.0, 0.6]])
    np.testing.assert_allclose(positive_log_expression_mean(values), [0.6, 0.4])
    with pytest.raises(ScientificContractError, match="positive"):
        positive_log_expression_mean(np.zeros((1, 3)))
