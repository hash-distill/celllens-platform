"""Read-only, provenance-checked cell state figures from frozen analysis inputs."""

import json
import re
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
import pandas as pd

from backend.app.core.registry import RegistryEntry
from backend.app.core.run_manifest import file_sha256, manifest_hash
from backend.app.services.expression_scale import prepare_log_expression
from backend.app.services.scientific_analysis import (
    _align_sources,
    _combine_sources,
    _dense_matrix,
    _expression_view,
    _select_prediction_population,
)

SOURCES = ("control", "predicted", "observed")
COLORS = {"control": "#0072B2", "predicted": "#D55E00", "observed": "#009E73"}
LABELS = {"control": "Control", "predicted": "Predicted", "observed": "Observed"}
_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()
_LOCK = Lock()


class CellStateUnavailable(ValueError):
    pass


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _checked(path: Path, expected: Any) -> Path:
    if not path.is_file() or not expected or file_sha256(path).lower() != str(expected).lower():
        raise CellStateUnavailable(f"Frozen input is missing or changed: {path.name}")
    return path


def _run_root(container: Any, run_id: str) -> Path:
    if not re.fullmatch(r"run_[A-Za-z0-9_]+", run_id):
        raise CellStateUnavailable("Invalid frozen source run ID")
    return container.settings.derived_root / run_id


def _manifest(container: Any, run_id: str) -> tuple[Path, dict[str, Any], str]:
    root = _run_root(container, run_id)
    matches = [a for a in container.store.artifacts(run_id) if Path(a.relative_path).name == "manifest.json"]
    if len(matches) != 1:
        raise CellStateUnavailable("No uniquely registered frozen manifest")
    path = _checked(root / "manifest.json", matches[0].sha256)
    return root, _json(path), matches[0].sha256


def frozen_inputs(container: Any, run_id: str) -> dict[str, Any]:
    """Replays locate predictions through a verified original manifest, never a context default."""
    root, manifest, sha = _manifest(container, run_id)
    if manifest.get("source_type") == "synthetic_precomputed":
        raise CellStateUnavailable("合成演示未提供可核验的真实表达来源；请打开真实计算或真实结果回放。")
    prediction_root, prediction_manifest = root, manifest
    if manifest.get("source_type") == "frozen_precomputed":
        prediction_root, prediction_manifest, original_sha = _manifest(container, manifest["source_run_id"])
        if original_sha != manifest.get("original_manifest_sha256"):
            raise CellStateUnavailable("Original run manifest does not match this replay")
        if prediction_manifest.get("source_type"):
            raise CellStateUnavailable("Nested replay is not a supported prediction source")
    outputs = manifest.get("outputs", {})
    files = {
        name: _checked(root / name, outputs.get(name, {}).get("sha256"))
        for name in (
            "expression_contract.json",
            "gene_identity.json",
            "gene_deltas.csv",
            "metabolic_task_scores.csv",
        )
    }
    files["predicted.h5ad"] = _checked(
        prediction_root / "predicted.h5ad",
        prediction_manifest.get("outputs", {}).get("predicted.h5ad", {}).get("sha256"),
    )
    contract = _json(files["expression_contract.json"])
    if contract.get("analysis_version") != "expression-cp10k-v2":
        raise CellStateUnavailable("This run lacks the verified expression-cp10k-v2 analysis contract")
    assets = manifest.get("assets", {})
    if assets != prediction_manifest.get("assets", {}):
        raise CellStateUnavailable("Replay assets do not match original analysis")
    registry = container.registry
    models = [r for r in registry.models if r["id"] == assets.get("model_id")]
    datasets = [r for r in registry.datasets if r["id"] == assets.get("dataset_id")]
    if len(models) != 1 or len(datasets) != 1:
        raise CellStateUnavailable("Frozen model/dataset ID is no longer locatable")
    model = RegistryEntry(models[0], container.settings.project_root)
    dataset = RegistryEntry(datasets[0], container.settings.project_root)
    for entry, key, hash_key in (
        (dataset, "control_path", "control_sha256"),
        (model, "gene_list_path", "gene_list_sha256"),
    ):
        files[key] = _checked(entry.path(key), assets.get(hash_key))
    if contract["source_scales"].get("observed"):
        files["observed_path"] = _checked(dataset.path("observed_path"), assets.get("observed_sha256"))
    if any(value != "log1p_cp10k" for value in contract["source_scales"].values() if value):
        raise CellStateUnavailable("Scientific view currently requires frozen log1p_cp10k sources")
    record = container.store.get(run_id)
    original_request = prediction_manifest["request"]
    if any(original_request[key] != getattr(record.request, key) for key in ("cell_line", "perturbation")):
        raise CellStateUnavailable("Run request does not match frozen prediction")
    return {
        "files": files,
        "contract": contract,
        "assets": assets,
        "manifest_sha256": sha,
        "source_run_id": manifest.get("source_run_id", run_id),
        "cell_line": record.request.cell_line,
        "perturbation": record.request.perturbation,
        "fingerprint": manifest_hash({"root": str(root.resolve()), "manifest": sha, "version": 1}),
    }


def reference_pca(matrices: dict[str, np.ndarray]) -> tuple[dict[str, np.ndarray], list[float]]:
    """Fit only the control reference. Prediction changes cannot rotate the fitted axes."""
    from sklearn.decomposition import PCA

    control = matrices["control"]
    if min(control.shape) < 2 or not all(np.isfinite(m).all() for m in matrices.values()):
        raise CellStateUnavailable("PCA requires finite matrices and at least two reference cells/genes")
    if np.var(control, axis=0).sum() <= 0:
        raise CellStateUnavailable("Control has zero expression variance")
    pca = PCA(n_components=2, svd_solver="full")
    pca.fit(control)
    return {name: pca.transform(m) for name, m in matrices.items()}, pca.explained_variance_ratio_.tolist()


def aligned_task_scores(scores: pd.DataFrame, ids: list[str], sources: list[str]) -> pd.DataFrame:
    if not scores.index.is_unique or len(set(ids)) != len(ids) or set(scores.index) != set(ids):
        raise CellStateUnavailable("Task scores and expression cell IDs do not match uniquely")
    result = scores.loc[ids]
    if result["source"].astype(str).tolist() != sources:
        raise CellStateUnavailable("Task score sources do not match expression cell IDs")
    return result


def _reconstruct(inputs: dict[str, Any]) -> dict[str, Any]:
    import anndata as ad

    files, contract, assets = inputs["files"], inputs["contract"], inputs["assets"]
    selection = contract["population_selection"]
    if selection.get("status") != "matched" or selection.get("perturbation") != inputs["perturbation"]:
        raise CellStateUnavailable("Frozen perturbation selection is not verified")
    column = selection["perturbation_column"]
    control = ad.read_h5ad(files["control_path"])
    predicted, selected = _select_prediction_population(
        ad.read_h5ad(files["predicted.h5ad"]), column, inputs["perturbation"]
    )
    if selected != selection:
        raise CellStateUnavailable("Reconstructed prediction selection differs from the frozen analysis")
    sources = {"control": control, "predicted": predicted}
    if "observed_path" in files:
        observed = ad.read_h5ad(files["observed_path"])
        if column not in observed.obs:
            raise CellStateUnavailable("Observed perturbation column is missing")
        sources["observed"] = observed[
            observed.obs[column].astype(str).str.upper() == inputs["perturbation"]
        ].copy()
    key = assets.get("expression_key") or assets.get("input_embed_key")
    expression_slots = {}
    for name, frame in sources.items():
        expression_slots[name] = f"obsm[{key}]" if key and key != "X" and key in frame.obsm else "X"
        frame = prepare_log_expression(frame, "log1p_cp10k")
        # Observed measurements can legitimately lack the model's prediction slot.
        # Their .X path must still match every frozen identity column and saved mean below.
        strict = (
            bool(key) if name == "predicted" else bool(assets.get("expression_key")) and name == "control"
        )
        sources[name] = _expression_view(frame, key, files["gene_list_path"], strict=strict)
    batch = contract.get("validation_population")
    if batch and batch.get("status") == "common_batches_only":
        for name, frame in sources.items():
            if frame.n_obs != batch["input_cells"][name]:
                raise CellStateUnavailable("Validation input population changed")
            sources[name] = frame[
                frame.obs[batch["batch_key"]].astype(str).isin(batch["common_batches"])
            ].copy()
            if sources[name].n_obs != batch["selected_cells"][name]:
                raise CellStateUnavailable("Validation batch population changed")
    identity = _json(files["gene_identity.json"])["sources"]
    for name, frame in sources.items():
        columns = identity[name]["columns"]
        current = frame.var.get("gene_symbol", frame.var_names).astype(str).tolist()
        if [s.upper() for s in current] != [c["source_symbol"].upper() for c in columns]:
            raise CellStateUnavailable("Frozen gene identity does not match the expression columns")
        names = [c["analysis_symbol"] for c in columns]
        frame.var["gene_symbol"] = names
        frame.var_names = pd.Index(names)
    aligned, genes, _ = _align_sources(sources["control"], sources["predicted"], sources.get("observed"))
    if len(genes) != contract["gene_count"]:
        raise CellStateUnavailable("Gene panel size differs from the frozen analysis")
    sources = {name: frame for name, frame in zip(SOURCES, aligned, strict=True) if frame is not None}
    matrices = {name: np.asarray(_dense_matrix(frame.X), dtype=float) for name, frame in sources.items()}
    frozen_genes = pd.read_csv(files["gene_deltas.csv"], index_col=0)
    if genes != frozen_genes.index.tolist():
        raise CellStateUnavailable("Frozen gene panel order does not match reconstructed expression")
    for name, matrix in matrices.items():
        mean = matrix.mean(axis=0)
        expected = (
            frozen_genes[name]
            if name in frozen_genes
            else frozen_genes["control"] + frozen_genes["observed_delta"]
        )
        if not np.allclose(mean, expected, rtol=1e-5, atol=3e-6):
            raise CellStateUnavailable(f"{name} gene means differ from the existing analysis")
    combined = _combine_sources(ad, sources["control"], sources["predicted"], sources.get("observed"))
    ids = combined.obs_names.astype(str).tolist()
    cell_sources = combined.obs["celllens_source"].astype(str).tolist()
    scores = aligned_task_scores(
        pd.read_csv(files["metabolic_task_scores.csv"], index_col=0), ids, cell_sources
    )
    coordinates, variance = reference_pca(matrices)
    gene_delta = np.asarray(frozen_genes["predicted_delta"], dtype=float).reshape(-1)
    gene_order = [genes[int(i)] for i in np.argsort(-np.abs(gene_delta), kind="stable")]
    task_means = scores.drop(columns="source").groupby(scores["source"]).mean()
    task_delta: Any = task_means.loc["predicted"] - task_means.loc["control"]
    task_order = (
        task_delta.replace([np.inf, -np.inf], np.nan)
        .abs()
        .dropna()
        .sort_values(ascending=False)
        .index.tolist()
    )
    return {
        "matrices": matrices,
        "genes": genes,
        "gene_order": gene_order,
        "task_order": task_order,
        "scores": scores,
        "sources": cell_sources,
        "ids": ids,
        "coordinates": coordinates,
        "variance": variance,
        "inputs": inputs,
        "expression_slots": expression_slots,
    }


def distribution(values: np.ndarray) -> dict[str, Any]:
    valid = values[np.isfinite(values)]
    if not len(valid):
        return {
            "n": len(values),
            "n_valid": 0,
            "mean": None,
            "q25": None,
            "median": None,
            "q75": None,
            "ecdf": [],
        }
    x, counts = np.unique(valid, return_counts=True)
    q = np.quantile(valid, [0.25, 0.5, 0.75]).tolist()
    return {
        "n": len(values),
        "n_valid": len(valid),
        "mean": float(valid.mean()),
        "q25": q[0],
        "median": q[1],
        "q75": q[2],
        "ecdf": np.column_stack([x, np.cumsum(counts) / len(valid)]).tolist(),
    }


def cell_state_document(container: Any, run_id: str, feature_kind: str, feature_id: str) -> dict[str, Any]:
    inputs = frozen_inputs(container, run_id)  # Hashes are rechecked even on cache hits.
    fingerprint = inputs["fingerprint"]
    with _LOCK:
        if fingerprint not in _CACHE:
            reconstructed = _reconstruct(inputs)
            if frozen_inputs(container, run_id)["fingerprint"] != fingerprint:
                raise CellStateUnavailable("Frozen inputs changed during reconstruction")
            _CACHE[fingerprint] = reconstructed
            while len(_CACHE) > 4:
                _CACHE.popitem(last=False)
        data = _CACHE[fingerprint]
        _CACHE.move_to_end(fingerprint)
    options = data["gene_order"] if feature_kind == "gene" else data["task_order"]
    if not options:
        raise CellStateUnavailable("No valid per-cell features are available")
    if not feature_id:
        feature_id = (
            inputs["perturbation"]
            if feature_kind == "gene" and inputs["perturbation"] in options
            else options[0]
        )
    if feature_id not in options:
        raise CellStateUnavailable("所选指标未提供可核验的逐细胞数值，请选择列表中的其他指标。")
    points, summaries = [], {}
    offset = 0
    rng = np.random.default_rng(42)
    budget = 12_000
    total = len(data["ids"])
    for name, matrix in data["matrices"].items():
        count = len(matrix)
        values = (
            matrix[:, data["genes"].index(feature_id)]
            if feature_kind == "gene"
            else data["scores"][feature_id].iloc[offset : offset + count].to_numpy(float)
        )
        summaries[name] = distribution(values)
        take = min(count, max(1, budget // len(data["matrices"])))
        indices = np.sort(rng.choice(count, take, replace=False)) if take < count else np.arange(count)
        for i in indices:
            xy = data["coordinates"][name][i]
            points.append(
                {
                    "x": float(xy[0]),
                    "y": float(xy[1]),
                    "source": name,
                    "cell_id": data["ids"][offset + i],
                    "cell_index": int(i),
                    "value": float(values[i]) if np.isfinite(values[i]) else None,
                }
            )
        summaries[name]["n_displayed"] = len(indices)
        offset += count
    all_coords = np.concatenate(list(data["coordinates"].values()))
    bounds = []
    for axis in range(2):
        low, high = float(all_coords[:, axis].min()), float(all_coords[:, axis].max())
        pad = max((high - low) * 0.06, 0.1)
        bounds.append([low - pad, high + pad])
    # Color range describes all cells, not just displayed scatter points.
    values_all = (
        np.concatenate([matrix[:, data["genes"].index(feature_id)] for matrix in data["matrices"].values()])
        if feature_kind == "gene"
        else data["scores"][feature_id].to_numpy(float)
    )
    finite = values_all[np.isfinite(values_all)]
    low, high = float(finite.min()), float(finite.max())
    return {
        "run_id": run_id,
        "cell_line": inputs["cell_line"],
        "perturbation": inputs["perturbation"],
        "method": "control-reference-pca",
        "fit_source": "control",
        "expression_units": "log1p(CP10K)",
        "gene_count": len(data["genes"]),
        "explained_variance_ratio": data["variance"],
        "feature": {
            "kind": feature_kind,
            "id": feature_id,
            "units": "log1p(CP10K)" if feature_kind == "gene" else "scCellFie task activity score",
        },
        "available_features": {"genes": data["gene_order"], "tasks": data["task_order"]},
        "points": points,
        "distributions": summaries,
        "bounds": bounds,
        "color_range": [low, high],
        "total_cells": total,
        "displayed_cells": len(points),
        "seed": 42,
        "provenance": {
            "manifest_sha256": inputs["manifest_sha256"],
            "source_run_id": inputs["source_run_id"],
            "population_selection": inputs["contract"]["population_selection"],
            "validation_population": inputs["contract"].get("validation_population"),
            "gene_means_verified": True,
            "task_cell_ids_verified": True,
            "expression_slots": data["expression_slots"],
        },
        "limitations": [
            "PCA fitted on centered control log expression; no gene-wise scaling.",
            "Explained variance applies to the control reference, not the predictions.",
            "Unpaired populations; no biological replicate inference or significance test.",
            "Expression space is not morphology, spatial location, trajectory, or metabolic flux.",
        ],
    }
