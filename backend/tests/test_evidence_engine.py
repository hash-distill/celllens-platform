import pandas as pd
import pytest

from backend.app.engines.evidence_engine import compare_task_deltas


def test_task_delta_uses_same_control_reference():
    control = pd.Series({"T1": 1.0, "T2": 2.0})
    predicted = pd.Series({"T1": 1.5, "T2": 1.0})
    observed = pd.Series({"T1": 1.4, "T2": 0.8})
    result = compare_task_deltas(control, predicted, observed)
    assert result.table.loc["T1", "predicted_delta"] == pytest.approx(0.5)
    assert result.table.loc["T1", "observed_delta"] == pytest.approx(0.4)
    assert bool(result.table.loc["T1", "direction_match"])
    assert result.direction_agreement == 1.0


def test_metrics_use_one_common_finite_task_set():
    control = pd.Series({"T1": 0.0, "T2": 0.0, "T3": 0.0, "T4": 0.0})
    predicted = pd.Series({"T1": 1.0, "T2": float("nan"), "T3": 2.0, "T4": 3.0})
    observed = pd.Series({"T1": 1.0, "T2": 2.0, "T3": 2.0, "T4": 4.0})
    result = compare_task_deltas(control, predicted, observed)
    assert list(result.table.index) == ["T1", "T3", "T4"]
    assert result.valid_task_count == 3
    assert result.excluded_task_count == 1
    assert result.spearman == pytest.approx(1.0)
    assert result.direction_agreement == 1.0
    assert result.top_k_overlap == 1.0
