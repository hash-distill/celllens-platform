"""Versioned, explicitly prepared diagnostics; reading never opens expression matrices.

Historical comparison bundles are immutable. This sidecar binds their exact hashes,
reproduces their pooled estimate, and records a separate equal-batch sensitivity.
"""

import csv
import hashlib
import json
import math
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.measured_comparison import ComparisonUnavailable, _checked, _path, _read

VERSION = "comparison-diagnostics-v2"
GROUPS = ("control", "predicted", "observed")
LIMITATIONS = [
    "共同 gem_group 为记录的批次，不自动代表独立生物学重复。",
    "批次等权是敏感性诊断；少细胞批次均值可能不稳定，不替代冻结的原汇总估计。",
    "细胞级探索性诊断，非生物学重复检验；增加生成记录不会增加实测独立证据。",
    "未确认训练排除，非独立留出验证；scCellFie 一致性不等于实测代谢通量验证。",
]
WARNING_TRANSLATIONS = dict(
    [
        (
            "Matched observations do not prove checkpoint training exclusion or held-out generalization.",
            "匹配观测不能证明检查点训练时排除了这些样本，也不能证明留出泛化。",
        ),
        (
            "Cell-level Wilcoxon is a diagnostic; cells are not independent biological replicates.",
            "细胞级 Wilcoxon 仅为探索性诊断；细胞不是独立生物学重复。",
        ),
        (
            "All-gene direction agreement differs from direction agreement on shared significant DEGs.",
            "全基因方向一致率与共有诊断显著 DEG 的方向一致率是不同分母。",
        ),
        (
            "Evaluation uses the common recorded batches, with their original frequencies.",
            "冻结估计采用共同记录批次，保留各组原始批次频率，未重加权。",
        ),
        (
            "scCellFie agreement is expression-derived task agreement, not measured flux.",
            "scCellFie 一致性是表达派生任务的一致性，不是实测代谢通量。",
        ),
        (
            "All finite paired genes, including zero changes, are evaluated; no observations are imputed.",
            "评价保留所有具有有限成对数值的基因，包括零变化；没有填补观测值。",
        ),
    ]
)


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _coverage_rows(bundle, manifest):
    digest = manifest.get("outputs", {}).get("metabolic_coverage.csv")
    if not digest:
        return {}
    path = _checked(bundle, "metabolic_coverage.csv", digest)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len({row["task"] for row in rows}) != len(rows):
        raise ComparisonUnavailable("Duplicate comparison coverage task identity")
    return {row["task"]: row for row in rows}


def task_annotations(report, bundle, manifest):
    """Join only this comparison's bound coverage, never the original population."""
    coverage = _coverage_rows(bundle, manifest)
    rows = []
    seen = set()
    for task in report.get("tasks", []):
        if task["id"] in seen or not all(
            isinstance(task.get(key), (int, float)) and math.isfinite(task[key])
            for key in (*GROUPS, "predicted_delta", "observed_delta")
        ):
            raise ComparisonUnavailable("Duplicate task identity or non-finite paired task values")
        seen.add(task["id"])
        row = coverage.get(task["id"], {})
        fraction = float(row["gene_fraction"]) if row.get("gene_fraction") else None
        if fraction is not None and (not math.isfinite(fraction) or not 0 <= fraction <= 1):
            raise ComparisonUnavailable("Invalid task gene coverage")
        rows.append(
            {
                **task,
                "coverage": fraction,
                "evidence_level": row.get("evidence_level") or "unknown",
                "missing_genes": row.get("missing_genes", ""),
                "coverage_source": "comparison/metabolic_coverage.csv" if row else "unavailable",
                "input_scope": "matched comparison expression panel",
            }
        )
    counts = Counter(row["evidence_level"] for row in rows)
    return rows, {
        "finite_paired_task_count": len(rows),
        "knowledge_base_task_count": len(coverage) or None,
        "unscored_task_count": len(set(coverage) - {row["id"] for row in rows}) if coverage else None,
        "by_evidence_level": {
            level: counts[level] for level in ("supported", "exploratory", "insufficient", "unknown")
        },
        "coverage_sha256": manifest.get("outputs", {}).get("metabolic_coverage.csv"),
        "scope": "comparison's own frozen metabolic coverage; RNA-derived task support, not flux",
    }


def _directory(root, run_id):
    return _path(root, f"data/derived/comparison_diagnostics/{VERSION}/{run_id}")


def load_diagnostics(root, run_id, comparison_manifest_sha256, comparison_sha256):
    directory = _directory(root, run_id)
    if not directory.exists():
        return None
    manifest = _read(directory / "manifest.json")
    if (
        manifest.get("run_id") != run_id
        or manifest.get("version") != VERSION
        or manifest.get("comparison_manifest_sha256") != comparison_manifest_sha256
        or manifest.get("comparison_sha256") != comparison_sha256
    ):
        raise ComparisonUnavailable("Diagnostic source binding mismatch")
    digest = manifest.get("diagnostics_sha256")
    document = _read(_checked(directory, "diagnostics.json", digest))
    if document.get("run_id") != run_id or document.get("version") != VERSION:
        raise ComparisonUnavailable("Diagnostic identity mismatch")
    return {
        **document,
        "diagnostics_sha256": digest,
        "diagnostics_manifest_sha256": file_sha256(directory / "manifest.json"),
    }


def enrich_comparison(root, run_id, report, bundle, manifest):
    """Small read-only joins and verified sidecar load; no matrix/score calculations."""
    rows, coverage = task_annotations(report, bundle, manifest)
    comparison_sha = manifest["outputs"]["comparison.json"]
    manifest_sha = file_sha256(bundle / "manifest.json")
    report = {
        **report,
        "tasks": rows,
        "task_coverage": coverage,
        "comparison_sha256": comparison_sha,
        "comparison_manifest_sha256": manifest_sha,
        "warnings_zh": list(
            dict.fromkeys(
                [
                    *LIMITATIONS,
                    *[
                        WARNING_TRANSLATIONS.get(value, "来源提醒（原文）：" + value)
                        for value in report.get("warnings", [])
                    ],
                ]
            )
        ),
        "evaluation_protocol": {
            "status": "selection_not_prepared",
            "reference_selection_sha256": None,
            "comparison_policy": "仅相同参考群体选择指纹可横向比较；seed/n 改变可能改变实测真值群体。",
        },
        "batch_sensitivity": {
            "status": "unavailable",
            "reason": "批次敏感性尚未显式准备；读取不会触发计算。",
        },
    }
    try:
        diagnostics = load_diagnostics(root, run_id, manifest_sha, comparison_sha)
    except (ComparisonUnavailable, OSError, KeyError, TypeError, ValueError) as exc:
        report["batch_sensitivity"]["reason"] = f"已有诊断未通过来源校验：{exc}"
        report["batch_sensitivity"]["status"] = "invalid"
        return report
    if diagnostics:
        report["batch_sensitivity"] = {
            **diagnostics["batch_sensitivity"],
            "status": "available",
            "diagnostics_sha256": diagnostics["diagnostics_sha256"],
        }
        report["evaluation_protocol"] = diagnostics["evaluation_protocol"]
        report["task_coverage"].update(diagnostics["task_statistics"])
        structures = diagnostics["task_score_structures"]
        report["tasks"] = [{**row, **structures.get(row["id"], {})} for row in rows]
        report["diagnostics_provenance"] = {
            key: diagnostics[key]
            for key in (
                "version",
                "implementation_sha256",
                "diagnostics_sha256",
                "diagnostics_manifest_sha256",
            )
        }
    return report


def _metrics(means):
    pred = means["predicted"] - means["control"]
    obs = means["observed"] - means["control"]
    mse = float(np.mean((pred - obs) ** 2))
    baseline = float(np.mean(obs**2))
    pearson = float(np.corrcoef(pred, obs)[0, 1]) if np.std(pred) > 0 and np.std(obs) > 0 else None
    return {
        "signed_delta_pearson": pearson,
        "mse": mse,
        "no_change_mse": baseline,
        "mse_relative_to_no_change": mse / baseline if baseline > 0 else None,
        "direction_agreement": float(np.mean(np.sign(pred) == np.sign(obs))),
    }


def _verify_metric(actual, expected):
    if actual is None or expected is None:
        return actual is None and expected is None
    return bool(
        np.isfinite(actual) and np.isfinite(expected) and np.isclose(actual, expected, rtol=2e-5, atol=2e-6)
    )


def _task_statistics(rows):
    statistics = {}
    for level in ("supported", "exploratory", "insufficient", "unknown"):
        selected = [row for row in rows if row["evidence_level"] == level]
        pred = pd.Series([row["predicted_delta"] for row in selected], dtype=float)
        obs = pd.Series([row["observed_delta"] for row in selected], dtype=float)
        statistics[level] = {
            "finite_paired_task_count": len(selected),
            "mae": float((pred - obs).abs().mean()) if len(selected) else None,
            "spearman": float(np.corrcoef(pred.rank(), obs.rank())[0, 1])
            if pred.nunique() > 1 and obs.nunique() > 1
            else None,
        }
    signatures = {row["id"]: tuple(round(float(row[key]), 8) for key in GROUPS) for row in rows}
    sizes = Counter(signatures.values())
    annotations = {
        name: {
            "score_structure_id": _digest(signature)[:16],
            "same_score_structure_task_count": sizes[signature],
        }
        for name, signature in signatures.items()
    }
    return {
        "stratified_metrics": statistics,
        "distinct_mean_triplets_8dp": len(sizes),
        "independence_note": "相同三元均值按 8 位小数分组仅提示相关结构；不同组也不能视作独立功能证据。",
    }, annotations


def prepare_diagnostics(root: Path, run_id: str):
    """Explicit CPU-only preparation from already frozen matrices; never calls STATE."""
    from backend.app.services.measured_comparison import load_comparison

    report = load_comparison(root, run_id, include_diagnostics=False)
    if not report:
        raise ComparisonUnavailable("No verified comparison to diagnose")
    bundle = _path(root, f"data/derived/comparisons/{run_id}")
    manifest = _read(bundle / "manifest.json")
    manifest_sha = file_sha256(bundle / "manifest.json")
    comparison_sha = manifest["outputs"]["comparison.json"]
    existing = load_diagnostics(root, run_id, manifest_sha, comparison_sha)
    if existing:
        return existing
    original = _read(
        _checked(root, f"data/derived/runs/{run_id}/manifest.json", manifest["source_manifest_sha256"])
    )
    assets = original["assets"]
    contract = _read(
        _checked(bundle, "expression_contract.json", manifest["outputs"].get("expression_contract.json"))
    )
    if (
        contract.get("analysis_version") != "expression-cp10k-v2"
        or contract.get("gene_units") != "mean(log1p(CP10K))"
        or any(contract.get("source_scales", {}).get(group) != "log1p_cp10k" for group in GROUPS)
    ):
        raise ComparisonUnavailable("Sensitivity requires a verified log1p_cp10k contract for all sources")

    def input_by_sha(digest):
        names = [name for name, sha in manifest["inputs"].items() if sha == digest]
        if len(names) != 1:
            raise ComparisonUnavailable("Ambiguous frozen input binding")
        return _checked(root, names[0], digest)

    import anndata as ad

    paths = {
        "control": input_by_sha(assets["control_sha256"]),
        "predicted": input_by_sha(original["outputs"]["predicted.h5ad"]["sha256"]),
        "observed": input_by_sha(report["source"]["observed_sha256"]),
    }
    panel_path = input_by_sha(assets["gene_list_sha256"])
    panel = [
        line.strip().upper() for line in panel_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    genes = [row["id"] for row in report["genes"]]
    if len(panel) != len(set(panel)) or len(genes) != len(set(genes)):
        raise ComparisonUnavailable("Sensitivity requires the exact frozen unique gene panel")
    identity_digest = manifest["outputs"].get("gene_identity.json")
    identities = _read(_checked(bundle, "gene_identity.json", identity_digest)) if identity_digest else {}
    source_genes = {}
    for group in GROUPS:
        mapping = identities.get("sources", {}).get(group)
        if mapping:
            columns = mapping["columns"]
            inverse = {row["analysis_symbol"]: row["source_symbol"] for row in columns}
            if (
                mapping.get("expression_values_changed") is not False
                or len(inverse) != len(columns)
                or len({row["source_symbol"] for row in columns}) != len(columns)
                or not set(genes).issubset(inverse)
            ):
                raise ComparisonUnavailable("Frozen gene identity map is not a unique value-preserving map")
            source_genes[group] = [inverse[gene] for gene in genes]
        else:
            source_genes[group] = genes
        if set(source_genes[group]) != set(panel):
            raise ComparisonUnavailable(
                "Frozen identity mapping does not reproduce the registered gene panel"
            )
    slot = assets.get("expression_key") or assets.get("input_embed_key") or "X"
    selection = contract["population_selection"]
    column = selection.get("perturbation_column")
    target = report["perturbation"].strip().upper()
    matching = report.get("population_matching") or {}
    batch_key = matching.get("batch_key")
    common = matching.get("common_batches")
    if not batch_key or not common or len(common) != len(set(common)):
        raise ComparisonUnavailable("No frozen common-batch selection")
    frames: dict[str, Any] = {key: ad.read_h5ad(path) for key, path in paths.items()}
    pooled, equal, batch_counts, selection_rows = {}, {}, {}, {}
    for group, frame in frames.items():
        if group == "predicted" or (group == "observed" and column in frame.obs):
            if not column or column not in frame.obs:
                raise ComparisonUnavailable("Missing frozen perturbation selector")
            frame = frame[frame.obs[column].astype(str).str.strip().str.upper() == target].copy()
        if frame.n_obs != matching.get("input_cells", {}).get(group):
            raise ComparisonUnavailable("Input cell count differs from frozen comparison")
        if batch_key not in frame.obs or frame.obs[batch_key].isna().any() or not frame.obs_names.is_unique:
            raise ComparisonUnavailable("Missing batches or duplicate cell IDs within a source")
        frame = frame[frame.obs[batch_key].astype(str).isin(common)].copy()
        if frame.n_obs != report["parameters"]["population_counts"][group]:
            raise ComparisonUnavailable("Selected population differs from frozen comparison")
        if slot != "X" and slot in frame.obsm:
            matrix = frame.obsm[slot]
            matrix = matrix.toarray() if hasattr(matrix, "toarray") else np.asarray(matrix)
            if matrix.shape[1] != len(panel):
                raise ComparisonUnavailable("Expression slot width differs from frozen panel")
            matrix = matrix[:, [panel.index(gene) for gene in source_genes[group]]]
        else:
            if group == "predicted" and slot != "X":
                raise ComparisonUnavailable("Predicted expression slot missing")
            names = frame.var.get("gene_symbol", frame.var_names).astype(str).str.strip().str.upper().tolist()
            positions = {gene: index for index, gene in enumerate(names)}
            if len(positions) != len(names) or not set(source_genes[group]).issubset(positions):
                raise ComparisonUnavailable("Cannot align unique gene axis")
            matrix = frame[:, [positions[gene] for gene in source_genes[group]]].X
            matrix = matrix.toarray() if hasattr(matrix, "toarray") else np.asarray(matrix)
        if matrix.shape != (frame.n_obs, len(genes)) or not np.isfinite(matrix).all():
            raise ComparisonUnavailable("Expression matrix has a mismatched axis or non-finite values")
        batches = frame.obs[batch_key].astype(str).to_numpy()
        counts = {batch: int(np.sum(batches == batch)) for batch in common}
        if min(counts.values()) == 0:
            raise ComparisonUnavailable("A frozen common batch is absent")
        batch_counts[group] = counts
        pooled[group] = matrix.mean(axis=0)
        equal[group] = np.mean([matrix[batches == batch].mean(axis=0) for batch in common], axis=0)
        if not np.isfinite(pooled[group]).all() or not np.isfinite(equal[group]).all():
            raise ComparisonUnavailable("Population means are non-finite")
        selection_rows[group] = sorted(
            [
                {"cell_id": str(identifier), "batch": str(batch)}
                for identifier, batch in zip(frame.obs_names, batches, strict=True)
            ],
            key=lambda item: item["cell_id"],
        )
        frozen_means = np.asarray([row[group] for row in report["genes"]])
        if not np.allclose(pooled[group], frozen_means, rtol=2e-5, atol=2e-6):
            raise ComparisonUnavailable("Pooled expression means do not reproduce frozen gene table")
    pooled_metrics, equal_metrics = _metrics(pooled), _metrics(equal)
    if {row["cell_id"] for row in selection_rows["control"]} & {
        row["cell_id"] for row in selection_rows["observed"]
    }:
        raise ComparisonUnavailable("Control and observed populations contain overlapping measured cell IDs")
    for key in ("mse", "no_change_mse", "mse_relative_to_no_change", "signed_delta_pearson"):
        if not _verify_metric(pooled_metrics[key], report["expression"][key]):
            raise ComparisonUnavailable("Pooled metrics do not reproduce frozen comparison")
    reference = {
        "version": VERSION,
        "control_sha256": assets["control_sha256"],
        "observed_sha256": report["source"]["observed_sha256"],
        "gene_axis_sha256": _digest(genes),
        "source_gene_axes_sha256": _digest({group: source_genes[group] for group in ("control", "observed")}),
        "expression_scale": "log1p_cp10k",
        "batch_key": batch_key,
        "common_batches": common,
        "selected_cells": {group: selection_rows[group] for group in ("control", "observed")},
        "pooled_weights": {
            group: {batch: n / sum(batch_counts[group].values()) for batch, n in batch_counts[group].items()}
            for group in ("control", "observed")
        },
        "equal_batch_weights": {batch: 1 / len(common) for batch in common},
    }
    rows, _ = task_annotations(report, bundle, manifest)
    statistics, structures = _task_statistics(rows)
    ratio, equal_ratio = (
        pooled_metrics["mse_relative_to_no_change"],
        equal_metrics["mse_relative_to_no_change"],
    )
    diagnostics = {
        "version": VERSION,
        "run_id": run_id,
        "implementation_sha256": file_sha256(Path(__file__)),
        "comparison_sha256": comparison_sha,
        "comparison_manifest_sha256": manifest_sha,
        "frozen_gene_identity_sha256": identity_digest,
        "evaluation_protocol": {
            **reference,
            "status": "frozen_selection",
            "reference_selection_sha256": _digest(reference),
            "comparison_policy": "仅相同参考群体选择指纹、基因轴与权重协议可横比；seed/n 可能改变真值。",
            "prediction_population_is_generated": True,
            "held_out_validation": False,
            "training_exclusion_verified": False,
        },
        "batch_sensitivity": {
            "pooled_cells": pooled_metrics,
            "equal_batch_weight": equal_metrics,
            "baseline_conclusion_consistent": (ratio < 1) == (equal_ratio < 1)
            if ratio is not None and equal_ratio is not None
            else None,
            "baseline_comparison_reason": None
            if ratio is not None and equal_ratio is not None
            else "实测变化的基线 MSE 为零，误差比与基线方向判断未定义。",
            "batch_key": batch_key,
            "common_batches": common,
            "batch_counts": batch_counts,
            "total_variation_control_observed": float(
                sum(
                    abs(
                        reference["pooled_weights"]["control"][b] - reference["pooled_weights"]["observed"][b]
                    )
                    for b in common
                )
                / 2
            ),
            "formula": "每组先求各批次均值，再对共同批次等权平均；变化减同口径对照，MSE 对相同基因轴平均。",
            "gene_axis_sha256": _digest(genes),
            "gene_count": len(genes),
            "finite_values_verified": True,
            "unique_cell_ids_within_source_verified": True,
            "cell_id_scope": "IDs scoped by source; predictions are simulated, not biological replicates",
            "limitations": LIMITATIONS,
        },
        "task_statistics": statistics,
        "task_score_structures": structures,
    }
    # Recheck every bound source after reading; publish into a new, separate directory.
    load_comparison(root, run_id, include_diagnostics=False)
    final = _directory(root, run_id)
    partial = final.with_name(f"{run_id}.{uuid.uuid4().hex}.partial")
    partial.mkdir(parents=True, exist_ok=False)
    atomic_write_json(partial / "diagnostics.json", diagnostics)
    atomic_write_json(
        partial / "manifest.json",
        {
            "version": VERSION,
            "run_id": run_id,
            "comparison_sha256": comparison_sha,
            "comparison_manifest_sha256": manifest_sha,
            "diagnostics_sha256": file_sha256(partial / "diagnostics.json"),
        },
    )
    try:
        partial.rename(final)
    except OSError:
        if not final.is_dir():
            raise
    return load_diagnostics(root, run_id, manifest_sha, comparison_sha)
