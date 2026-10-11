"""Measured expression analysis; group differences are descriptive, not inferential."""

from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.app.config import Settings
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.engines.metabolic_engine import ScCellFieEngine
from backend.app.services.completeness import compute_official_completeness
from backend.app.services.expression_scale import linear_cp10k
from backend.app.services.gene_identity import GeneIdentityAdapter
from backend.app.services.scientific_analysis import _load_frozen_database, _task_completeness
from backend.app.user_data.datasets import read_expression
from backend.app.user_data.schemas import UploadMetadata


def _mean(matrix: Any) -> np.ndarray:
    return np.asarray(matrix.mean(axis=0)).reshape(-1)


def group_difference(frame: pd.DataFrame, groups: pd.Series, reference: str | None) -> pd.DataFrame:
    grouped = frame.groupby(groups.rename("group"), observed=True).mean()
    output = (
        grouped.rename_axis("group")
        .reset_index()
        .melt(id_vars="group", var_name="id", value_name="mean_score")
    )
    if reference:
        base = grouped.loc[reference]
        output["reference_mean"] = output["id"].map(base)
        output["delta"] = output["mean_score"] - output["reference_mean"]
    return output


def explore_expression(
    data: Any, *, group_key: str | None, reference_group: str | None, seed: int
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    from sklearn.decomposition import PCA

    matrix = data.X
    groups = data.obs[group_key].astype(str) if group_key else pd.Series("all", index=data.obs_names)
    if reference_group and (not group_key or reference_group not in set(groups)):
        raise ValueError("参考组不存在")
    linear = linear_cp10k(data)
    detected = np.asarray((matrix > 0).sum(axis=1)).reshape(-1)
    qc = pd.DataFrame(
        {
            "cell_id": data.obs_names,
            "group": groups.to_numpy(),
            "detected_genes": detected,
            "sum_cp10k": np.asarray(linear.X.sum(axis=1)).reshape(-1),
        }
    )
    if data.uns["celllens_expression"]["input_scale"] == "raw_counts":
        key = data.uns["celllens_expression"]["total_counts_key"]
        qc["full_library_counts"] = data.obs[key].to_numpy()
    means = _mean(matrix)
    second = _mean(matrix.multiply(matrix) if hasattr(matrix, "multiply") else np.square(matrix))
    variance = np.maximum(second - means * means, 0)
    genes = np.argsort(variance, kind="stable")[-min(1000, data.n_vars) :]
    rng = np.random.default_rng(seed)
    cells = np.sort(rng.choice(data.n_obs, size=min(2000, data.n_obs), replace=False))
    view = matrix[cells][:, genes]
    dense = view.toarray() if hasattr(view, "toarray") else np.asarray(view)
    coordinates = np.zeros((len(cells), 2))
    explained = [0.0, 0.0]
    if np.any(np.var(dense, axis=0) > 1e-20):
        pca = PCA(n_components=2, svd_solver="randomized", random_state=seed)
        coordinates = pca.fit_transform(dense)
        explained = [float(value) for value in pca.explained_variance_ratio_]
    baseline = _mean(matrix[np.asarray(groups == reference_group)]) if reference_group else None
    tables = []
    for group in sorted(set(groups)):
        selected = matrix[np.asarray(groups == group)]
        table = pd.DataFrame(
            {
                "gene": data.var_names,
                "group": group,
                "n_cells": int(sum(groups == group)),
                "mean_log1p_cp10k": _mean(selected),
                "detection_fraction": np.asarray((selected > 0).mean(axis=0)).reshape(-1),
            }
        )
        if baseline is not None:
            table["reference_mean_log1p_cp10k"] = baseline
            table["delta_log1p_cp10k"] = table["mean_log1p_cp10k"] - baseline
        tables.append(table)
    table = pd.concat(tables, ignore_index=True)
    if baseline is not None:
        preview = table[table["group"] != reference_group].copy()
        preview = preview.iloc[
            np.argsort(-np.abs(np.asarray(preview["delta_log1p_cp10k"])), kind="stable")[:50]
        ]
    else:
        preview = table.nlargest(50, "mean_log1p_cp10k")
    report = {
        "qc": {
            "n_cells": int(data.n_obs),
            "n_genes": int(data.n_vars),
            "zero_expression_cells": int(sum(detected == 0)),
            "median_detected_genes": float(np.median(detected)),
            "groups": {name: int(sum(groups == name)) for name in sorted(set(groups))},
        },
        "comparison": {
            "method": "difference_of_group_means" if reference_group else "group_means",
            "group_key": group_key,
            "reference_group": reference_group,
            "unit": "log1p_cp10k",
            "interpretation": "描述性组间差值；未进行显著性检验或因果推断。",
        },
        "projection": {
            "method": "PCA",
            "input_scale": "log1p_cp10k",
            "seed": seed,
            "total_cells": int(data.n_obs),
            "plotted_cells": len(cells),
            "selected_genes": [str(data.var_names[i]) for i in genes],
            "selection": "top 1000 genes by population variance; uniform cell sample up to 2000",
            "explained_variance_ratio": explained,
            "points": [
                {
                    "cell_id": str(data.obs_names[i]),
                    "group": str(groups.iloc[i]),
                    "x": float(coordinates[j, 0]),
                    "y": float(coordinates[j, 1]),
                }
                for j, i in enumerate(cells)
            ],
        },
        "genes": preview.to_dict(orient="records"),
    }
    return report, table, qc


class UserAnalysisService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, job: dict, dataset: dict, output_dir: Path) -> dict[str, dict]:
        path = self.settings.user_data_root / (dataset["id"] + ".h5ad")
        if file_sha256(path) != dataset["sha256"]:
            raise ValueError("源数据 SHA-256 校验失败")
        data, _ = read_expression(path, UploadMetadata.model_validate(dataset["metadata"]))
        request = job["request"]
        if request["group_key"] and request["group_key"] not in dataset["summary"]["group_columns"]:
            raise ValueError("分组列无效")
        report, genes, qc = explore_expression(
            data,
            group_key=request["group_key"],
            reference_group=request["reference_group"],
            seed=request["seed"],
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        genes.to_csv(output_dir / "gene_summary.csv", index=False)
        qc.to_csv(output_dir / "cell_quality.csv", index=False)
        files = ["gene_summary.csv", "cell_quality.csv", "report.json"]
        report.update(
            schema_version=1,
            analysis_id=job["id"],
            dataset_id=dataset["id"],
            kind=job["kind"],
            provenance={
                "source_sha256": dataset["sha256"],
                "metadata": dataset["metadata"],
                "analysis_version": "user-expression-v1",
                "software_versions": {
                    name: package_version(name)
                    for name in ("anndata", "numpy", "pandas", "scipy", "scikit-learn")
                },
                "expression": data.uns["celllens_expression"],
            },
            warnings=[
                "细胞层面的差值不能替代生物学重复和正式统计检验。",
                "PCA 坐标用于探索表达结构，不代表谱系关系或预测准确率。",
            ],
        )
        if job["kind"] == "metabolism":
            database, version = _load_frozen_database(self.settings.sccellfie_database_root)
            if self.settings.gene_identity_root.exists():
                adapter = GeneIdentityAdapter.load(
                    self.settings.gene_identity_root, self.settings.sccellfie_database_root
                )
                data, identity = adapter.adapt(data)
                atomic_write_json(output_dir / "gene_identity.json", identity)
                files.append("gene_identity.json")
            panel = list(data.var_names)
            official = compute_official_completeness(panel, database, version)
            official.update(analysis_id=job["id"], source_sha256=dataset["sha256"])
            atomic_write_json(output_dir / "official_completeness.json", official)
            files.append("official_completeness.json")
            result = ScCellFieEngine().run(
                linear_cp10k(data),
                database=database,
                database_version=version,
                completeness=_task_completeness(database, panel),
            )
            result.task_scores.to_csv(output_dir / "task_scores.csv", index_label="cell_id")
            result.reaction_scores.to_csv(output_dir / "reaction_scores.csv", index_label="cell_id")
            groups = (
                data.obs[request["group_key"]].astype(str)
                if request["group_key"]
                else pd.Series("all", index=data.obs_names)
            )
            scores = group_difference(result.task_scores, groups, request["reference_group"])
            scores.to_csv(output_dir / "task_group_summary.csv", index=False)
            files.extend(["task_scores.csv", "reaction_scores.csv", "task_group_summary.csv"])
            preview: Any = (
                scores[scores["group"] != request["reference_group"]]
                if request["reference_group"]
                else scores
            )
            if "delta" in preview:
                preview = preview.iloc[np.argsort(-np.abs(preview["delta"].to_numpy()), kind="stable")[:50]]
            else:
                preview = preview.nlargest(50, "mean_score")
            report["metabolism"] = {
                "database_version": version,
                "official_summary": official["overall_summary"],
                "n_tasks": result.task_scores.shape[1],
                "n_reactions": result.reaction_scores.shape[1],
                "n_tasks_database": len(database["task_by_rxn"]),
                "n_reactions_database": len(database["rxn_info"]),
                "unscored_tasks": sorted(
                    set(map(str, database["task_by_rxn"].index)) - set(map(str, result.task_scores.columns))
                ),
                "unscored_reactions": sorted(
                    set(map(str, database["rxn_info"]["Reaction"]))
                    - set(map(str, result.reaction_scores.columns))
                ),
                "score_scope": "仅展示 scCellFie 返回的可评分任务与反应；未返回项不视为零分。",
                "tasks": preview.to_dict(orient="records"),
                "interpretation": "表达支持的代谢任务评分与数据完整性，不能等同于实测通量或生物学验证。",
            }
        if file_sha256(path) != dataset["sha256"]:
            raise ValueError("分析期间源数据发生变化")
        atomic_write_json(output_dir / "report.json", report)
        return {
            name: {"sha256": file_sha256(output_dir / name), "size_bytes": (output_dir / name).stat().st_size}
            for name in files
        }
