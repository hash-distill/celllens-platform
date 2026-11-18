"""Download, checksum and inspect the single allowlisted sciPlex2 source.

Run: python -m scripts.prepare_sciplex2 [--inspect-only]
The API never accepts download URLs. Interrupted downloads remain .part files;
only the official checksum allows atomic publication and dataset registration.
"""

import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.dataset_contracts import Contrast, DatasetVersion
from backend.app.services.dataset_h5ad import read_csr, read_metadata
from backend.app.services.dataset_registry import (
    SCIPLEX_BYTES,
    SCIPLEX_ID,
    SCIPLEX_MD5,
    SCIPLEX_SOURCE,
    registry_path,
    source_path,
)

PROCESSING_REVISION = "fd4f5b360233520b0fc297f1bdf8953a6bee2dbb"
PROCESSING_URL = (
    "https://github.com/sanderlab/scPerturb/blob/"
    + PROCESSING_REVISION
    + "/dataset_processing/scripts/SrivatsanTrapnell2020.py"
)


def md5_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "md5").hexdigest()


def verify_official(path: Path) -> None:
    if path.stat().st_size != SCIPLEX_BYTES or md5_file(path) != SCIPLEX_MD5:
        raise ValueError("sciPlex2 文件大小或 MD5 不符合官方 v1.4 记录")


def download(root: Path) -> Path:
    path = source_path(root)
    if path.is_file():
        verify_official(path)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    for attempt in range(5):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > SCIPLEX_BYTES:
            raise ValueError("下载临时文件超过官方长度，请检查后移走该临时文件")
        if offset == SCIPLEX_BYTES:
            break
        request = urllib.request.Request(
            SCIPLEX_SOURCE["download_url"], headers={"Range": f"bytes={offset}-"} if offset else {}
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                if offset and (
                    response.status != 206
                    or not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-")
                ):
                    raise ValueError("下载服务未确认断点范围，未追加可能损坏的数据")
                with partial.open("ab" if offset else "wb") as handle:
                    last_report = time.monotonic()
                    while chunk := response.read(1 << 20):
                        if handle.tell() + len(chunk) > SCIPLEX_BYTES:
                            raise ValueError("下载响应超过官方长度")
                        handle.write(chunk)
                        if time.monotonic() - last_report > 10:
                            print(
                                json.dumps({"downloaded_bytes": handle.tell(), "total_bytes": SCIPLEX_BYTES}),
                                flush=True,
                            )
                            last_report = time.monotonic()
            if partial.stat().st_size == SCIPLEX_BYTES:
                break
        except (OSError, TimeoutError):
            if attempt == 4:
                raise
            time.sleep(2)
    verify_official(partial)
    partial.replace(path)
    return path


def build_contrasts(obs, version_id: str) -> list[Contrast]:
    """Only explicit same-drug zero-dose comparisons; never infer a DMSO label."""
    import pandas as pd

    required = {"organism", "cell_line", "perturbation", "dose_value"}
    if not required.issubset(obs.columns):
        raise ValueError("sciPlex2 缺少物种、背景、药物或剂量字段")
    selected = obs[(obs["organism"].astype(str) == "human") & (obs["cell_line"].astype(str) == "A549")]
    if selected.empty:
        raise ValueError("未找到已注释为 human/A549 的真实群体")
    contrasts = []
    for drug in sorted(set(selected["perturbation"].astype(str)) - {"control"}):
        drug_obs = selected[selected["perturbation"].astype(str) == drug]
        controls = drug_obs[pd.to_numeric(drug_obs["dose_value"], errors="coerce") == 0]
        if controls.empty:
            continue
        # Keep exact source spellings (e.g. 0 rather than generated 0.0).
        zero_labels = controls["dose_value"].astype(str).unique().tolist()
        if len(zero_labels) != 1:
            raise ValueError("零剂量标签不唯一，需显式修订 provider")
        for dose in sorted(drug_obs["dose_value"].dropna().astype(str).unique(), key=float):
            if float(dose) <= 0:
                continue
            treated = drug_obs[drug_obs["dose_value"].astype(str) == dose]
            common = {"organism": "human", "cell_line": "A549", "perturbation": drug}
            observed_filter = {**common, "dose_value": dose}
            identifier = (
                "contrast_"
                + hashlib.sha256(json.dumps(observed_filter, sort_keys=True).encode()).hexdigest()[:16]
            )
            contrasts.append(
                Contrast(
                    id=identifier,
                    dataset_version_id=version_id,
                    label=f"{drug} · dose {dose}",
                    cell_line="A549",
                    species="human",
                    perturbation=drug,
                    perturbation_type="drug",
                    dose=dose,
                    control_type="zero_dose_same_drug_label",
                    control_label=f"{drug} · dose 0",
                    cell_count=len(treated),
                    control_cell_count=len(controls),
                    observed_filter=observed_filter,
                    control_filter={**common, "dose_value": zero_labels[0]},
                    limitations=[
                        "对照为同一药物标签下源数据 dose_value=0 的细胞；不将其改称已核实的 DMSO 对照。",
                        "源文件未提供剂量单位和处理时间；dose 保留原始值，不推断单位或时间。",
                        "well 为原始实验标签，其独立生物学重复身份未核实；不计算正式差异显著性。",
                    ],
                )
            )
    if not contrasts:
        raise ValueError("未发现可核验的非零剂量与同标签零剂量对照")
    return contrasts


def inspect_and_register(root: Path, path: Path) -> dict:
    import h5py
    import numpy as np

    verify_official(path)
    digest = file_sha256(path)
    version_id = f"{SCIPLEX_ID}-v1.4-{digest[:12]}"
    with h5py.File(path, "r") as handle:
        obs, var = read_metadata(handle)
        if not obs.index.is_unique or not var.index.is_unique:
            raise ValueError("源数据细胞或基因标识不唯一")
        matrix = read_csr(handle)
        if matrix.shape != (len(obs), len(var)):
            raise ValueError("表达与注释维度不一致")
        values = handle["X/data"]
        if not isinstance(values, h5py.Dataset):
            raise ValueError("CSR X/data 不是数值数组")
        for start in range(0, len(values), 1_000_000):
            block = values[start : start + 1_000_000]
            if not np.isfinite(block).all() or np.any(block < 0) or not np.equal(block, np.rint(block)).all():
                raise ValueError("官方 counts 来源的实际 X 非有限、负值或非整数")
        totals = np.empty(len(obs), dtype=float)
        for start in range(0, len(obs), 256):
            totals[start : start + 256] = np.asarray(matrix[start : start + 256].sum(axis=1)).reshape(-1)
        if not np.isfinite(totals).all() or np.any(totals <= 0):
            raise ValueError("存在空或无效文库，必须先修订显式 QC 条件")
        gene_mask = var["ensembl_id"].astype(str).str.startswith("ENSG")
        if not gene_mask.any():
            raise ValueError("缺少可核验的人类 ENSG 基因")
        selected = (obs["organism"].astype(str) == "human") & (obs["cell_line"].astype(str) == "A549")
        contrasts = build_contrasts(obs, version_id)
        inspection = {
            "matrix_format": "csr",
            "matrix_shape": list(matrix.shape),
            "stored_values": int(len(values)),
            "all_stored_values_integer_nonnegative_finite": True,
            "positive_library_counts": True,
            "source_ncounts_matches_matrix": bool(np.allclose(totals, obs["ncounts"].to_numpy())),
            "obs_columns": obs.columns.tolist(),
            "var_columns": var.columns.tolist(),
            "organisms": {str(k): int(v) for k, v in obs["organism"].value_counts().items()},
            "backgrounds": {str(k): int(v) for k, v in obs["cell_line"].value_counts().items()},
            "perturbations": {str(k): int(v) for k, v in obs["perturbation"].value_counts().items()},
            "dose_values": sorted(obs["dose_value"].dropna().astype(str).unique(), key=float),
            "dose_unit": None,
            "time": None,
            "time_unit": None,
            "replicate_status": "not_verified",
            "biological_replicate_count": None,
            "well_label_count": int(obs["well"].nunique()),
            "well_labels_are_verified_biological_replicates": False,
            "excluded_unassigned_control_cells": int((obs["perturbation"].astype(str) == "control").sum()),
            "excluded_nonhuman_gene_count": int((~gene_mask).sum()),
            "counts_evidence_url": PROCESSING_URL,
            "counts_evidence": "Official processing constructs X directly from UMI.count.matrix as CSR; "
            "the downloaded matrix was independently streamed and checked for integer counts.",
            "selection": "organism=human; cell_line=A549; positive dose versus same-drug dose=0",
        }
    version = DatasetVersion(
        id=version_id,
        dataset_id=SCIPLEX_ID,
        provider="scperturb-sciplex2",
        source=SCIPLEX_SOURCE,
        file=path.relative_to(root).as_posix(),
        file_sha256=digest,
        file_md5=SCIPLEX_MD5,
        file_bytes=path.stat().st_size,
        expression_slot="X",
        expression_scale="raw_counts",
        gene_identifier="gene_symbol+ensembl_id",
        total_cell_count=len(obs),
        cell_count=int(selected.sum()),
        gene_count=int(gene_mask.sum()),
        species="human",
        cell_line="A549",
        inspection=inspection,
    )
    document = {
        "schema": "celllens-dataset-v1",
        "version": version.model_dump(),
        "contrasts": [row.model_dump() for row in contrasts],
    }
    target = registry_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target, document)
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--inspect-only", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    path = source_path(root) if args.inspect_only else download(root)
    document = inspect_and_register(root, path)
    print(
        json.dumps(
            {
                "registry": str(registry_path(root)),
                "version": document["version"]["id"],
                "condition_count": len(document["contrasts"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
