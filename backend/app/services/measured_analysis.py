"""Describe two measured populations without invoking a predictive model."""

import html
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.app.core.errors import CellLensError
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.expression_scale import linear_cp10k, mark_cp10k, prepare_log_expression

VERSION = "measured-expression-v2"


class AnalysisAssetsChangedError(Exception):
    pass


def bind_analysis_assets(existing: dict[str, str], frozen: dict[str, str]) -> None:
    if any(relative in existing and existing[relative] != digest for relative, digest in frozen.items()):
        raise AnalysisAssetsChangedError("分析过程中知识库或基因映射版本改变，未发布结果")
    existing.update(frozen)


def freeze_analysis_assets(root: Path, directory: Path) -> dict[str, str]:
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assets = [path, *(directory / name for name in manifest["files"])]
    return {item.resolve().relative_to(root.resolve()).as_posix(): file_sha256(item) for item in assets}


def checked_frame(entry: dict, cell: str, label: str):
    import anndata as ad

    path = Path(entry["path"])
    if not path.is_file() or file_sha256(path) != entry["sha256"]:
        raise ValueError("实测输入文件缺失或摘要已改变")
    frame = ad.read_h5ad(path)
    if not frame.n_obs or not frame.n_vars or not frame.obs_names.is_unique:
        raise ValueError("实测输入为空或细胞记录 ID 重复")
    contract = entry.get("group_contract")
    if contract:
        if contract["cell_line"].lower() != cell.lower():
            raise ValueError("实测群体背景与比较契约不一致")
        expected_labels = {**contract["labels"], "celllens_group": contract["group"]}
        if frame.uns.get("celllens_dataset_version_id") != contract["dataset_version_id"]:
            raise ValueError("实测群体与冻结数据版本不一致")
    else:
        expected_labels = {"cell_line": cell, "gene": label}
    for column, expected in expected_labels.items():
        if column not in frame.obs or set(frame.obs[column].astype(str).str.strip().str.lower()) != {
            str(expected).strip().lower()
        }:
            raise ValueError(f"实测输入的 {column} 标签与所选分析不一致")
    if "source_row" in frame.obs and frame.obs["source_row"].duplicated().any():
        raise ValueError("实测输入包含重复的源细胞行")
    try:
        return prepare_log_expression(
            frame, entry["expression_scale"], total_counts_key=entry.get("total_counts_key")
        )
    except CellLensError as exc:
        raise ValueError(str(exc)) from exc


def match_batches(control: Any, observed: Any) -> tuple[Any, Any, dict]:
    counts = {"control": int(control.n_obs), "observed": int(observed.n_obs)}
    if "gem_group" not in control.obs or "gem_group" not in observed.obs:
        return (
            control,
            observed,
            {
                "status": "unmatched_metadata_unavailable",
                "input_cells": counts,
                "limitation": "缺少共有批次字段；结果为未进行批次匹配的描述性群体比较",
            },
        )
    if control.obs["gem_group"].isna().any() or observed.obs["gem_group"].isna().any():
        raise ValueError("实测来源包含缺失的实验批次标签")
    common = sorted(set(control.obs["gem_group"].astype(str)) & set(observed.obs["gem_group"].astype(str)))
    if not common:
        raise ValueError("对照与目标扰动没有共有实验批次，不能直接比较")
    control = control[control.obs["gem_group"].astype(str).isin(common)].copy()
    observed = observed[observed.obs["gem_group"].astype(str).isin(common)].copy()
    return (
        control,
        observed,
        {
            "status": "common_batches_only",
            "batch_key": "gem_group",
            "common_batches": common,
            "input_cells": counts,
            "selected_cells": {"control": int(control.n_obs), "observed": int(observed.n_obs)},
            "limitation": "保持共有批次原有频率，不重加权；细胞记录不等于独立生物学重复",
        },
    )


def projection_document(matrices: dict, coordinates: dict, frames: dict, method: str, **metadata) -> dict:
    points = []
    for group in ("control", "observed"):
        values = np.asarray(coordinates[group], dtype=float)
        if values.shape != (len(matrices[group]), 2) or not np.isfinite(values).all():
            raise ValueError("实测二维投影坐标无效")
        for name, (x, y) in zip(frames[group].obs_names.astype(str), values, strict=True):
            points.append({"x": float(x), "y": float(y), "source": group, "cell_id": str(name)})
    return {
        "method": method,
        "source_kind": "measured",
        "points": points,
        "counts": {group: len(values) for group, values in matrices.items()},
        "gene_count": int(matrices["control"].shape[1]),
        "input_units": "log1p(CP10K)",
        "coordinates_are_physical_positions": False,
        **metadata,
    }


def mean_differences(scores: pd.DataFrame, sources: pd.Series, identifier: str) -> pd.DataFrame:
    labels = sources.reindex(scores.index)
    if labels.isna().any() or set(labels.astype(str)) != {"control", "observed"}:
        raise ValueError("代谢分数的实测群体标签不完整")
    means = scores.groupby(labels, observed=True).mean().T
    table = pd.DataFrame(means[["control", "observed"]]).copy()
    table["observed_delta"] = table["observed"] - table["control"]
    table.index.name = identifier
    return table


def measured_metabolism(root: Path, control: Any, observed: Any, genes: list[str], output: Path) -> dict:
    import anndata as ad

    from backend.app.engines.metabolic_engine import ScCellFieEngine
    from backend.app.services.completeness import compute_official_completeness
    from backend.app.services.scientific_analysis import (
        _combine_sources,
        _load_frozen_database,
        _task_completeness,
    )

    database, version = _load_frozen_database(root / "data/registry/sccellfie/human")
    complete = _task_completeness(database, genes)
    official = compute_official_completeness(genes, database, version)
    atomic_write_json(output / "official_completeness.json", official)
    complete.to_csv(output / "metabolic_coverage.csv")
    combined = _combine_sources(ad, linear_cp10k(control), None, linear_cp10k(observed))
    mark_cp10k(combined)
    result = ScCellFieEngine().run(
        combined, database=database, database_version=version, completeness=complete
    )
    labels = combined.obs["celllens_source"].astype(str)
    tasks = mean_differences(result.task_scores, labels, "task")
    tasks = tasks.join(complete[["gene_fraction", "missing_genes"]], how="left")
    from backend.app.services.task_trace import task_metadata

    tasks["label"] = [task_metadata(database, str(key))["label"] for key in tasks.index]
    tasks.to_csv(output / "tasks.csv")
    reactions = mean_differences(result.reaction_scores, labels, "reaction")
    reactions.to_csv(output / "reactions.csv")
    # Preserve per-cell task support for export; reaction CSV is explicitly a population mean table.
    cell_tasks = result.task_scores.copy()
    cell_tasks["source"] = labels.reindex(cell_tasks.index)
    cell_tasks.to_csv(output / "metabolic_task_scores.csv")
    top = tasks.iloc[np.argsort(-np.abs(tasks["observed_delta"].to_numpy()))[:20]].reset_index()
    database_genes = {str(g).upper() for g in database["rxn_by_gene"].columns}
    return {
        "available": True,
        "database_version": version,
        "task_count": len(tasks),
        "reaction_count": len(reactions),
        "top_tasks": json.loads(top.to_json(orient="records")),
        "units": "expression-derived scCellFie task/reaction support score",
        "coverage": {
            "available_metabolic_genes": len(set(genes) & database_genes),
            "database_metabolic_genes": len(database_genes),
            "full_gene_panel": len(genes),
        },
        "database_provenance": database["_celllens_provenance"],
    }


def render_report(summary: dict, output: Path) -> None:
    def safe(value):
        return html.escape(str(value))

    rows = "".join(
        f"<tr><td>{safe(row['gene'])}</td><td>{row['control']:.5g}</td><td>{row['observed']:.5g}</td>"
        f"<td>{row['observed_delta']:.5g}</td></tr>"
        for row in summary["top_genes"]
    )
    notes = "".join(f"<li>{safe(note)}</li>" for note in summary["limitations"] + summary["warnings"])
    document = (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>CellLens 实测分析</title>'
        "<style>body{max-width:1080px;margin:40px auto;font:16px/1.8 sans-serif;color:#203647}"
        "table{border-collapse:collapse;width:100%}td,th{padding:8px;border:1px solid #dce5ec}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f8fb;padding:16px}</style>"
        f"<h1>{safe(summary['cell_line'])} / {safe(summary['perturbation'])} 实测数据分析</h1>"
        f"<p>分析编号：{safe(summary['analysis_id'])}；来源：真实测量，CPU 描述性分析。</p>"
        f"<p>实际分析对照 {summary['counts']['control']} 个，"
        f"目标扰动实测 {summary['counts']['observed']} 个；"
        f"共同基因 {summary['gene_count']} 个。</p><h2>表达均值变化</h2>"
        "<p>单位 mean(log1p(CP10K))；差值 = 目标扰动实测均值 − 对照均值。</p>"
        "<table><tr><th>Gene</th><th>Control</th><th>Observed</th><th>Observed − Control</th></tr>"
        f"{rows}</table><h2>适用范围</h2><ul>{notes}</ul><h2>来源</h2>"
        f"<pre>{safe(json.dumps(summary['provenance'], ensure_ascii=False, indent=2))}</pre></html>"
    )
    (output / "report.html").write_text(document, encoding="utf-8")


def analyse_measured(
    root: Path,
    request: dict,
    inputs: dict,
    output: Path,
    report: Any,
    *,
    metabolism: bool = True,
    compute_umap: bool = True,
) -> dict:
    """Use measured expression and a full common panel; never access a model checkpoint."""
    from backend.app.services.cell_state import joint_umap, reference_pca
    from backend.app.services.scientific_analysis import _align_sources, _dense_matrix

    output.mkdir(parents=True, exist_ok=True)
    report(30, "校验真实对照与目标扰动观测")
    if request.get("dataset_id"):
        # Verify both group contracts against the frozen queued request, not only
        # against labels provided by an individual input descriptor.
        contrast = request["contrast"]
        for group, key in (("control", "control_filter"), ("observed", "observed_filter")):
            expected = {
                "group": group,
                "condition_id": contrast["id"],
                "dataset_version_id": request["dataset_version"]["id"],
                "cell_line": contrast["cell_line"],
                "labels": contrast[key],
            }
            if inputs["groups"][group].get("group_contract") != expected:
                raise ValueError("实测输入群体契约与排队比较条件不一致")
    control = checked_frame(inputs["groups"]["control"], request["cell_line"], "non-targeting")
    observed = checked_frame(inputs["groups"]["observed"], request["cell_line"], request["perturbation"])
    input_counts = {"control": int(control.n_obs), "observed": int(observed.n_obs)}
    control, observed, batches = match_batches(control, observed)
    warnings = []
    identity_root = root / "data/registry/gene_identity"
    identity = {}
    analysis_assets = {}
    metabolism_skip_reason = "本次未启用代谢评分"
    if (identity_root / "manifest.json").is_file():
        from backend.app.services.gene_identity import GeneIdentityAdapter

        database_root = root / "data/registry/sccellfie/human"
        try:
            frozen_identity = freeze_analysis_assets(root, identity_root)
            frozen_database = freeze_analysis_assets(root, database_root)
            adapter = GeneIdentityAdapter.load(identity_root, database_root)
        except (CellLensError, OSError, ValueError, KeyError) as exc:
            warnings.append(f"基因身份映射不可用，保留原始共同基因表达，跳过代谢评分：{exc}")
            metabolism = False
            metabolism_skip_reason = "知识库或身份映射缺失／不匹配；保留真实表达分析"
        else:
            # Ambiguous identities remain a hard error, rather than silently changing gene semantics.
            if request.get("dataset_id"):
                from backend.app.services.dataset_providers import adapt_dataset_gene_identity

                control, identity["control"] = adapt_dataset_gene_identity(adapter, control)
                observed, identity["observed"] = adapt_dataset_gene_identity(adapter, observed)
                collisions = identity["control"].get("unresolved_alias_collision_count", 0)
                if collisions:
                    warnings.append(
                        f"{collisions} 个旧别名与现存标准基因冲突；"
                        "保留原始独立特征，未合并表达或按该别名映射。"
                    )
            else:
                control, identity["control"] = adapter.adapt(control)
                observed, identity["observed"] = adapter.adapt(observed)
            atomic_write_json(output / "gene_identity.json", identity)
            bind_analysis_assets(analysis_assets, frozen_identity)
            bind_analysis_assets(analysis_assets, frozen_database)
    try:
        aligned, genes, _ = _align_sources(control, observed, None)
    except CellLensError as exc:
        raise ValueError(str(exc)) from exc
    control, observed = aligned[:2]
    frames = {"control": control, "observed": observed}
    from backend.app.services.dataset_contracts import check_analysis_budget

    check_analysis_budget(control.n_obs, observed.n_obs, len(genes))
    matrices = {name: np.asarray(_dense_matrix(frame.X), dtype=float) for name, frame in frames.items()}
    # This is the actual analysed population, with stable IDs shared with the
    # projection. A sparse frozen artifact supports later single-gene views.
    from scipy import sparse

    sparse.save_npz(
        output / "expression_preview.npz",
        sparse.vstack([sparse.csr_matrix(matrices[group]) for group in ("control", "observed")]),
    )
    atomic_write_json(
        output / "expression_preview.json",
        {
            "schema": "celllens-expression-preview-v1",
            "genes": genes,
            "cells": [
                {"cell_id": str(name), "source": group}
                for group in ("control", "observed")
                for name in frames[group].obs_names
            ],
            "units": "log1p(CP10K)",
            "counts": {group: int(frame.n_obs) for group, frame in frames.items()},
        },
    )
    table = pd.DataFrame(
        {"control": matrices["control"].mean(0), "observed": matrices["observed"].mean(0)},
        index=pd.Index(genes, name="gene"),
    )
    table["observed_delta"] = table["observed"] - table["control"]
    table.to_csv(output / "genes.csv")
    from backend.app.services.pathway_analysis import analyse_measured_pathways

    pathways, frozen_pathways = analyse_measured_pathways(
        root, request, inputs, matrices, genes, table, output
    )
    bind_analysis_assets(analysis_assets, frozen_pathways)
    top = table.iloc[np.argsort(-np.abs(table["observed_delta"].to_numpy()))[:20]].reset_index()
    report(40, "计算真实表达的二维参考投影")
    projections = {}
    for name in ("pca", "umap"):
        if name == "umap" and not compute_umap:
            projections[name] = {"available": False, "reason": "本次未启用 UMAP"}
            continue
        try:
            if name == "pca":
                coords, variance = reference_pca(matrices)
                document = projection_document(
                    matrices, coords, frames, "control-reference-pca", explained_variance_ratio=variance
                )
            else:
                report(50, "联合计算真实对照与实测群体 UMAP")
                coords, parameters = joint_umap(matrices)
                document = projection_document(matrices, coords, frames, "joint-umap", parameters=parameters)
            atomic_write_json(output / f"projection-{name}.json", document)
            projections[name] = {"available": True, "method": document["method"]}
        except (ValueError, RuntimeError, ImportError) as exc:
            projections[name] = {"available": False, "reason": str(exc)}
            warnings.append(f"{name.upper()} 不可用：{exc}")
    report(65, "从真实表达计算 scCellFie 功能支持分数")
    metabolic = {"available": False, "reason": metabolism_skip_reason}
    if metabolism:
        try:
            frozen_database = freeze_analysis_assets(root, root / "data/registry/sccellfie/human")
            metabolic = measured_metabolism(root, control, observed, genes, output)
            bind_analysis_assets(analysis_assets, frozen_database)
        except (ValueError, RuntimeError, ImportError, OSError, KeyError) as exc:
            metabolic = {"available": False, "reason": str(exc)}
            warnings.append(f"代谢评分不可用：{exc}")
    for entry in inputs["groups"].values():
        if file_sha256(Path(entry["path"])) != entry["sha256"]:
            raise ValueError("分析过程中实测输入已改变，未发布结果")
    for relative, digest in analysis_assets.items():
        if file_sha256(root / relative) != digest:
            raise ValueError("分析过程中知识库或基因映射已改变，未发布结果")
    inputs["analysis_assets"] = analysis_assets
    summary = {
        "analysis_id": request["id"],
        "analysis_version": VERSION,
        "source_kind": "measured",
        "cell_line": request["cell_line"],
        "perturbation": request["perturbation"],
        "input_counts": input_counts,
        "counts": {name: int(frame.n_obs) for name, frame in frames.items()},
        "source_cell_count": inputs["source_cell_count"],
        "gene_count": len(genes),
        "expression_units": "mean(log1p(CP10K))",
        "top_genes": json.loads(top.to_json(orient="records")),
        "metabolism": metabolic,
        "pathways": pathways,
        "projections": projections,
        "batch_matching": batches,
        "warnings": warnings,
        "provenance": inputs,
        "limitations": [
            "本次仅分析真实对照与目标扰动实测，未执行 STATE 预测。",
            "表达和任务变化为未配对群体的描述性比较；细胞记录不等于独立生物学重复。",
            "scCellFie 分数来自表达推断，不是实测代谢通量。",
            "PCA/UMAP 坐标表示特征分布，不是细胞形态、物理位置或逐细胞迁移轨迹。",
            "实测数据的存在与本次分析完成不证明预测模型的泛化能力。",
        ],
    }
    if request.get("dataset_id"):
        summary["dataset_id"] = request["dataset_id"]
        summary["dataset_version_id"] = request["dataset_version"]["id"]
        summary["contrast"] = request["contrast"]
        summary["limitations"].extend(request["contrast"].get("limitations", []))
    atomic_write_json(output / "summary.json", summary)
    render_report(summary, output)
    report(95, "实测分析完成，正在核验并冻结结果")
    return summary
