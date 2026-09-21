import numpy as np

from backend.app.services.scientific_analysis import _projection_document


def test_projection_is_deterministic_capped_and_preserves_sources():
    sources = [
        ("control", np.arange(30, dtype=float).reshape(10, 3)),
        ("predicted", np.arange(12, dtype=float).reshape(4, 3)),
    ]

    first = _projection_document(sources, seed=42, max_points=6)
    repeated = _projection_document(sources, seed=42, max_points=6)

    assert first == repeated
    assert len(first["points"]) == 6
    assert {point["source"] for point in first["points"]} == {"control", "predicted"}
