"""Explicit expression units; never infer units from a filename or matrix range."""

from typing import Any

import numpy as np

from backend.app.core.errors import ScientificContractError

SCALES = {"raw_counts", "cp10k", "log1p_cp10k"}
ANALYSIS_VERSION = "expression-cp10k-v2"


def require_scale(scale: Any) -> str:
    if scale not in SCALES:
        raise ScientificContractError(f"Unknown or missing expression scale: {scale!r}")
    return str(scale)


def _values(matrix: Any) -> np.ndarray:
    return matrix.data if hasattr(matrix, "tocsr") else np.asarray(matrix)


def validate_expression(matrix: Any) -> None:
    values = _values(matrix)
    if not np.isfinite(values).all() or np.any(values < 0):
        raise ScientificContractError("Expression must be finite and non-negative in the declared scale")


def prepare_log_expression(adata: Any, scale: str, *, total_counts_key: str | None = None) -> Any:
    """Canonicalize before gene subsetting, retaining the full-library normalization."""
    scale = require_scale(scale)
    result = adata.copy()
    validate_expression(result.X)
    if scale == "raw_counts":
        if not total_counts_key or total_counts_key not in result.obs:
            raise ScientificContractError("raw_counts requires an explicit full-library total counts column")
        counts = np.asarray(result.obs[total_counts_key], dtype=float)
        values = _values(result.X)
        if not np.allclose(values, np.rint(values), atol=1e-5, rtol=0):
            raise ScientificContractError("raw_counts contains noninteger expression values")
        if not np.isfinite(counts).all() or np.any(counts <= 0):
            raise ScientificContractError("Full-library total counts must be finite and positive")
        measured = np.asarray(result.X.sum(axis=1)).reshape(-1)
        if np.any(measured > counts + 1e-5):
            raise ScientificContractError("Full-library counts are smaller than the measured panel")
        if hasattr(result.X, "tocsr"):
            result.X = result.X.multiply((10_000.0 / counts)[:, None]).tocsr()
        else:
            result.X = np.asarray(result.X, dtype=float) * (10_000.0 / counts)[:, None]
    if scale != "log1p_cp10k":
        if hasattr(result.X, "tocsr"):
            sparse_matrix: Any = result.X.astype(float)
            sparse_matrix.data = np.log1p(sparse_matrix.data)
            result.X = sparse_matrix
        else:
            result.X = np.log1p(np.asarray(result.X, dtype=float))
    result.uns["celllens_expression"] = {
        "analysis_version": ANALYSIS_VERSION,
        "scale": "log1p_cp10k",
        "input_scale": scale,
        "normalization_target": 10_000,
        "normalization_basis": "upstream full library; never rescale the selected prediction panel",
        "total_counts_key": total_counts_key or "not_required",
    }
    return result


def linear_cp10k(adata: Any) -> Any:
    if adata.uns.get("celllens_expression", {}).get("scale") != "log1p_cp10k":
        raise ScientificContractError("Linear conversion requires declared log1p_cp10k expression scale")
    result = adata.copy()
    if hasattr(result.X, "tocsr"):
        result.X = result.X.astype(float)
        result.X.data = np.expm1(result.X.data)
    else:
        with np.errstate(over="ignore", invalid="ignore"):
            result.X = np.expm1(np.asarray(result.X, dtype=float))
    validate_expression(result.X)
    mark_cp10k(result)
    return result


def mark_cp10k(adata: Any) -> None:
    """scCellFie 0.6.2 recognizes this marker and skips its count normalization."""
    adata.uns["celllens_expression"] = {
        "analysis_version": ANALYSIS_VERSION,
        "scale": "cp10k",
        "normalization_target": 10_000,
        "normalization_basis": "upstream full library; selected panel is not renormalized",
    }
    adata.uns["normalization"] = {"method": "total_counts", "target_sum": 10_000}
