"""Stable ASCII attachment names; full feature IDs remain in the data document."""

import hashlib
import re


def feature_token(feature: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", feature).strip("_-")[:48] or "feature"
    return f"{slug}-{hashlib.sha256(feature.encode('utf-8')).hexdigest()[:8]}"


def figure_filename(
    run_id: str, space: str, embedding: str, kind: str, feature: str, file_format: str
) -> str:
    return f"{run_id}_cell_state_{space}_{embedding}_{kind}_{feature_token(feature)}.{file_format}"
