import numpy as np
import pytest

from scripts.evaluate_se_observed import compare_deltas, matched_observed_rows, weighted_observed_mean


def test_observed_sampling_matches_each_control_batch_and_preserves_source_order():
    lines = np.array(["k562"] * 7 + ["rpe1"])
    perts = np.array(["AAMP", "AAMP", "non-targeting", "AAMP", "AAMP", "AAMP", "OTHER", "AAMP"])
    batches = np.array([1, 1, 1, 2, 2, 2, 2, 1])
    rows = matched_observed_rows(lines, perts, batches, "K562", np.array([1, 2, 2]), seed=42)
    assert len(rows) == 3
    assert np.array_equal(rows, np.sort(rows))
    assert np.array_equal(np.sort(batches[rows]), [1, 2, 2])
    assert (perts[rows] == "AAMP").all()


def test_missing_batch_rejects_unmatched_comparison():
    with pytest.raises(ValueError, match="batch"):
        matched_observed_rows(
            np.array(["k562"]), np.array(["AAMP"]), np.array([1]), "K562", np.array([2]), seed=42
        )


def test_no_change_baseline_is_reported_and_zero_observed_change_is_not_divided():
    metrics = compare_deltas(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 3.0]))
    assert metrics["rmse"] == 0
    assert metrics["mse_relative_to_no_change"] == 0
    zero = compare_deltas(np.array([1.0, 0.0]), np.zeros(2))
    assert zero["mse_relative_to_no_change"] is None
    assert zero["pearson"] is None


def test_scarce_measured_cells_are_not_duplicated_and_batch_means_use_control_weights():
    rows = matched_observed_rows(
        np.array(["k562", "k562"]),
        np.array(["AAMP", "AAMP"]),
        np.array([1, 2]),
        "K562",
        np.array([1, 1, 2]),
        seed=42,
    )
    assert np.array_equal(rows, [0, 1])
    mean = weighted_observed_mean(np.array([[3.0, 6.0], [0.0, 3.0]]), np.array([1, 2]), np.array([1, 1, 2]))
    assert np.allclose(mean, [2.0, 5.0])


def test_requested_perturbation_selects_its_measurements():
    rows = matched_observed_rows(
        np.array(["k562", "k562"]),
        np.array(["AAMP", "ALDOA"]),
        np.array([1, 1]),
        "K562",
        np.array([1]),
        seed=43,
        perturbation="ALDOA",
    )
    assert np.array_equal(rows, [1])
