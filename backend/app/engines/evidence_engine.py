from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EvidenceMetrics:
    spearman: float | None
    mae: float
    direction_agreement: float
    top_k_overlap: float
    table: pd.DataFrame
    valid_task_count: int
    excluded_task_count: int


def compare_task_deltas(
    control: pd.Series,
    predicted: pd.Series,
    observed: pd.Series,
    *,
    top_k: int = 10,
) -> EvidenceMetrics:
    names = control.index.intersection(predicted.index).intersection(observed.index)
    raw = pd.DataFrame(
        {
            "predicted_delta": predicted.loc[names] - control.loc[names],
            "observed_delta": observed.loc[names] - control.loc[names],
        }
    )
    finite = np.isfinite(raw["predicted_delta"]) & np.isfinite(raw["observed_delta"])
    frame = raw.loc[finite].copy()
    excluded_task_count = int((~finite).sum())
    frame["direction_match"] = np.sign(frame["predicted_delta"]) == np.sign(frame["observed_delta"])
    frame["absolute_error"] = (frame["predicted_delta"] - frame["observed_delta"]).abs()
    if len(frame) < 2 or frame["predicted_delta"].nunique() < 2 or frame["observed_delta"].nunique() < 2:
        spearman = None
    else:
        predicted_rank = frame["predicted_delta"].rank(method="average").to_numpy(dtype=float)
        observed_rank = frame["observed_delta"].rank(method="average").to_numpy(dtype=float)
        spearman = float(np.corrcoef(predicted_rank, observed_rank)[0, 1])
    actual_k = min(top_k, len(frame))
    if actual_k == 0:
        overlap = 0.0
    else:
        predicted_top = set(frame["predicted_delta"].abs().nlargest(actual_k).index)
        observed_top = set(frame["observed_delta"].abs().nlargest(actual_k).index)
        overlap = len(predicted_top & observed_top) / actual_k
    return EvidenceMetrics(
        spearman=spearman,
        mae=float(frame["absolute_error"].mean()) if len(frame) else 0.0,
        direction_agreement=float(frame["direction_match"].mean()) if len(frame) else 0.0,
        top_k_overlap=overlap,
        table=frame,
        valid_task_count=len(frame),
        excluded_task_count=excluded_task_count,
    )
