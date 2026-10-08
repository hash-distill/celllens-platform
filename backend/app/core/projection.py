"""The projection required before a scientific run can be completed."""

import json
import math
from pathlib import Path
from typing import Any


def validate_projection(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("method"), str):
        raise ValueError("Projection must record its method")
    points = document.get("points")
    if not isinstance(points, list) or not points:
        raise ValueError("Projection must contain single-cell points")
    identities = set()
    sources = set()
    for point in points:
        if not isinstance(point, dict) or point.get("source") not in {"control", "predicted", "observed"}:
            raise ValueError("Projection contains an invalid cell source")
        for axis in ("x", "y"):
            value = point.get(axis)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("Projection coordinates must be finite numbers")
        index = point.get("cell_index")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError("Projection must record a nonnegative cell index")
        identity = (point["source"], index)
        if identity in identities:
            raise ValueError("Projection contains duplicate cell identities")
        identities.add(identity)
        sources.add(point["source"])
    if not {"control", "predicted"}.issubset(sources):
        raise ValueError("Projection must include control and predicted populations")
    return document
