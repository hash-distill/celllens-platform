"""Provider adapters read only bounded groups from frozen, local source matrices."""

from pathlib import Path

from backend.app.core.run_manifest import file_sha256
from backend.app.services.dataset_contracts import check_analysis_budget
from backend.app.services.dataset_h5ad import read_csr, read_metadata
from backend.app.services.dataset_registry import read_dataset, source_path


def adapt_dataset_gene_identity(adapter, frame):
    """Keep distinct source features when a historical alias now names another gene.

    The fixed legacy adapter deliberately raises on all collisions. For newly
    registered datasets with distinct Ensembl identities, an exact approved
    symbol can be retained while a conflicting historical alias stays unresolved.
    No values are summed, dropped or borrowed from the approved gene.
    """
    from collections import defaultdict

    import pandas as pd

    from backend.app.core.errors import ScientificContractError

    genes = frame.var.get("gene_symbol", frame.var_names)
    columns = [adapter.resolve(str(gene)) for gene in genes]
    by_name = defaultdict(list)
    for index, row in enumerate(columns):
        by_name[row["analysis_symbol"]].append(index)
    unresolved = []
    for name, indices in by_name.items():
        if len(indices) < 2:
            continue
        approved = [i for i in indices if columns[i]["method"] == "approved"]
        if len(approved) != 1 or "ensembl_id" not in frame.var:
            raise ScientificContractError(
                "Dataset gene collision cannot be resolved without unique identities"
            )
        source_ids = frame.var.iloc[indices]["ensembl_id"].astype(str)
        if source_ids.nunique() != len(indices) or not source_ids.str.startswith("ENSG").all():
            raise ScientificContractError("Colliding dataset features lack distinct human Ensembl identities")
        for i in indices:
            if i in approved:
                continue
            row = columns[i]
            if row["method"] not in {"previous", "alias"}:
                raise ScientificContractError("Dataset contains a non-alias identity collision")
            detail = {
                "source_symbol": row["source_symbol"],
                "source_ensembl_id": str(frame.var.iloc[i]["ensembl_id"]),
                "candidate_analysis_symbol": name,
                "candidate_hgnc_id": row["hgnc_id"],
                "reason": "distinct source Ensembl feature conflicts with a present approved symbol",
            }
            unresolved.append(detail)
            columns[i] = {
                **row,
                "hgnc_id": None,
                "approved_symbol": None,
                "analysis_symbol": row["source_symbol"],
                "method": "unresolved_alias_collision",
                "collision": detail,
            }
    names = [row["analysis_symbol"] for row in columns]
    if len(set(names)) != len(names):
        raise ScientificContractError("Duplicate gene identities remain after conservative alias handling")
    result = frame.copy()
    result.var["source_gene_symbol"] = [str(gene) for gene in genes]
    result.var["gene_symbol"] = names
    result.var_names = pd.Index(names)
    return result, {
        "provenance": adapter.provenance,
        "columns": columns,
        "renamed_columns": sum(row["source_symbol"] != row["analysis_symbol"] for row in columns),
        "expression_values_changed": False,
        "unresolved_alias_collision_count": len(unresolved),
        "unresolved_alias_collisions": unresolved,
        "collision_policy": "retain approved symbol; preserve distinct conflicting source aliases "
        "unresolved; never aggregate expression",
    }


def selection_mask(obs, filters: dict):
    import numpy as np

    result = np.ones(len(obs), dtype=bool)
    for key, value in filters.items():
        if key not in obs:
            raise ValueError(f"源数据缺少比较条件字段：{key}")
        result &= obs[key].astype(str).to_numpy() == value
    return result


def prepare_sciplex_inputs(root: Path, request: dict, staging: Path, report) -> dict:
    import anndata as ad
    import h5py
    import numpy as np
    from scipy import sparse

    version, contrasts = read_dataset(root, request["dataset_id"])
    contrast = next((row for row in contrasts if row.id == request["condition_id"]), None)
    if (
        version.model_dump() != request["dataset_version"]
        or contrast is None
        or contrast.model_dump() != request["contrast"]
    ):
        raise ValueError("排队后数据版本或条件登记已改变，未继续计算")
    path = source_path(root)
    if file_sha256(path) != version.file_sha256:
        raise ValueError("数据文件摘要不符合冻结版本")
    groups = {}
    report(10, "从已校验的 sciPlex2 稀疏矩阵读取所选真实群体")
    with h5py.File(path, "r") as handle:
        obs, var = read_metadata(handle)
        matrix = read_csr(handle, version.expression_slot)
        # Explicit Ensembl species identity; mouse features are never relabelled human.
        gene_mask = var["ensembl_id"].astype(str).str.startswith("ENSG").to_numpy()
        if int(gene_mask.sum()) != version.gene_count:
            raise ValueError("实际人类基因面板与冻结登记不一致")
        counts = {"control": contrast.control_cell_count, "observed": contrast.cell_count}
        check_analysis_budget(
            min(request["max_cells"], counts["control"]),
            min(request["max_cells"], counts["observed"]),
            version.gene_count,
        )
        for group, filters in (("control", contrast.control_filter), ("observed", contrast.observed_filter)):
            available = np.flatnonzero(selection_mask(obs, filters))
            if len(available) != counts[group] or not len(available):
                raise ValueError("实际源细胞数与冻结条件不一致")
            rows = np.sort(
                np.random.default_rng(request["seed"]).choice(
                    available, size=min(request["max_cells"], len(available)), replace=False
                )
            )
            # X stays sparse. Only selected rows are read; no whole-source to_memory/dense.
            selected = matrix[rows, :].tocsr()
            selected_obs = obs.iloc[rows].copy()
            selected_obs["celllens_group"] = group
            selected_obs["source_row"] = rows
            selected_obs["celllens_total_counts"] = np.asarray(selected.sum(axis=1)).reshape(-1)
            frame = ad.AnnData(
                selected[:, gene_mask].tocsr(),
                obs=selected_obs,
                var=var.iloc[np.flatnonzero(gene_mask)].copy(),
            )
            if not sparse.issparse(frame.X):
                raise ValueError("数据 provider 必须保留稀疏计数")
            frame.uns["celllens_dataset_version_id"] = version.id
            frame.uns["celllens_control_type"] = contrast.control_type
            target = staging / "inputs" / f"{group}.h5ad"
            target.parent.mkdir(parents=True, exist_ok=True)
            frame.write_h5ad(target, compression="gzip")
            groups[group] = {
                "path": str(target),
                "sha256": file_sha256(target),
                "expression_scale": version.expression_scale,
                "total_counts_key": "celllens_total_counts",
                "origin": "frozen_dataset_sparse_row_selection",
                "source": version.source,
                "group_contract": {
                    "group": group,
                    "condition_id": contrast.id,
                    "dataset_version_id": version.id,
                    "cell_line": contrast.cell_line,
                    "labels": filters,
                },
            }
            report(18 if group == "control" else 25, f"已读取 {len(rows)} 个 {group} 真实细胞")
    if file_sha256(path) != version.file_sha256:
        raise ValueError("提取期间源数据摘要改变")
    return {
        "source": dict(version.source),
        "dataset_version": version.model_dump(),
        "contrast": contrast.model_dump(),
        "source_cell_count": contrast.cell_count,
        "source_catalog_sha256": request["source_catalog_sha256"],
        "sampling": {
            "max_cells_per_group": request["max_cells"],
            "seed": request["seed"],
            "with_replacement": False,
            "whole_source_densified": False,
        },
        "normalization": {
            "basis": "all original source features before human-gene selection",
            "target_sum": 10000,
            "input": "raw_counts",
        },
        "groups": groups,
    }


PROVIDERS = {"scperturb-sciplex2": prepare_sciplex_inputs}


def prepare_dataset_inputs(root: Path, request: dict, staging: Path, report) -> dict:
    provider = PROVIDERS.get(request["dataset_id"])
    if provider is None:
        raise ValueError("未登记的数据 provider")
    return provider(root, request, staging, report)
