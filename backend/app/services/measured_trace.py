"""Explain a measured task using the exact knowledge version recorded by its result.

No inference, score recomputation, or writes. Unknown historical knowledge stays unavailable.
"""

import hashlib
import io
import json
from pathlib import Path

import pandas as pd

from backend.app.services.measured_results import confined, read_table
from backend.app.services.task_trace import associations, finite


def measured_task_evidence(root: Path, directory: Path, summary: dict, task_id: str) -> dict:
    metabolism = summary.get("metabolism", {})
    if not metabolism.get("available"):
        raise ValueError("本次分析没有可用的功能评分")
    provenance = metabolism.get("database_provenance", {})
    database = confined(root, "data/registry/sccellfie/human")
    manifest_data = (database / "manifest.json").read_bytes()
    if (
        not provenance.get("manifest_sha256")
        or hashlib.sha256(manifest_data).hexdigest() != provenance["manifest_sha256"]
    ):
        raise ValueError("本次分析的知识库版本无法核验，不能补入其他版本的关联")
    manifest = json.loads(manifest_data)
    if manifest.get("version") != metabolism.get("database_version"):
        raise ValueError("知识库版本与本次分析不一致")
    required = (
        "Task-Info.csv",
        "Task_by_Gene.csv",
        "Task_by_Rxn.csv",
        "Rxn_by_Gene.csv",
        "Rxn-Info-Recon2-2.json",
    )
    documents = {}
    for name in required:
        digest = provenance.get("files", {}).get(name)
        if not digest or manifest.get("files", {}).get(name) != digest:
            raise ValueError("本次分析未记录完整的知识关联指纹")
        raw = (database / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("知识关联文件已变化，拒绝混用历史分析与当前知识库")
        documents[name] = raw

    def csv(name, index=None):
        frame = pd.read_csv(io.BytesIO(documents[name]), keep_default_na=False, index_col=index)
        if not frame.columns.is_unique or (index is not None and not frame.index.is_unique):
            raise ValueError("知识关联存在重复标识")
        return frame

    def index_table(kind, key):
        frame = read_table(directory, kind)
        if frame[key].duplicated().any():
            raise ValueError("结果表存在重复标识")
        return frame.set_index(key)

    tasks, genes, reactions = (
        index_table("tasks", "task"),
        index_table("genes", "gene"),
        index_table("reactions", "reaction"),
    )
    if task_id not in tasks.index:
        raise KeyError(task_id)
    info = csv("Task-Info.csv").set_index("Task")
    if not info.index.is_unique:
        raise ValueError("任务分类存在重复标识")
    task_genes, task_reactions, reaction_genes = (
        csv(name, 0) for name in ("Task_by_Gene.csv", "Task_by_Rxn.csv", "Rxn_by_Gene.csv")
    )
    if task_id not in task_genes.index or task_id not in task_reactions.index:
        raise ValueError("冻结知识库未收录该任务的完整关联")
    reaction_info = pd.read_json(io.BytesIO(documents["Rxn-Info-Recon2-2.json"])).set_index("Reaction")
    if not reaction_info.index.is_unique:
        raise ValueError("反应定义存在重复标识")

    def scores(frame, identifier):
        row = frame.loc[identifier] if identifier in frame.index else {}
        return {name: finite(row.get(name)) for name in ("control", "observed", "observed_delta")}

    def gene(identifier):
        return {"id": identifier, "present": identifier in genes.index, **scores(genes, identifier)}

    def gene_rule(identifier):
        value = reaction_info.loc[identifier].get("GPR-symbol") if identifier in reaction_info.index else None
        return str(value) if value is not None and pd.notna(value) and str(value).strip() else None

    gene_ids = associations(task_genes, task_id)
    rxn_ids = associations(task_reactions, task_id)
    present = [name for name in gene_ids if name in genes.index]
    metadata = info.loc[task_id] if task_id in info.index else {}
    return {
        "schema_version": "measured-task-evidence-v1",
        "analysis_id": summary["analysis_id"],
        "source_kind": "measured",
        "relationship_kind": "knowledge_association",
        "database_version": manifest["version"],
        "database_provenance": provenance,
        "units": {"expression": summary.get("expression_units"), "function": metabolism.get("units")},
        "task": {
            "id": task_id,
            "category": metadata.get("System") or None,
            "subcategory": metadata.get("Subsystem") or None,
            **scores(tasks, task_id),
            "recorded_gene_fraction": finite(tasks.loc[task_id].get("gene_fraction")),
        },
        "coverage": {
            "present": len(present),
            "total": len(gene_ids),
            "missing": [name for name in gene_ids if name not in genes.index],
        },
        "genes": [gene(name) for name in gene_ids],
        "reactions": [
            {
                "id": name,
                **scores(reactions, name),
                "gene_rule": gene_rule(name),
                "genes": [gene(identifier) for identifier in associations(reaction_genes, name)],
            }
            for name in rxn_ids
        ],
        "limitations": [
            "关联由本次记录的知识库版本提供，不是本次实验验证的因果链。",
            "评分来自表达支持，不等于代谢通量；缺失成员保留为缺失，不填成零。",
            "任务成员齐全只说明输入覆盖，不表示功能得到实验验证。",
        ],
    }
