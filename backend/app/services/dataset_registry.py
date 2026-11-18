"""Frozen, allowlisted public sources; preparation is an explicit local operation."""

import json
from functools import lru_cache
from pathlib import Path

from backend.app.core.run_manifest import file_sha256
from backend.app.services.dataset_contracts import Contrast, DatasetVersion, check_analysis_budget

SCIPLEX_ID = "scperturb-sciplex2"
SCIPLEX_FILE = "SrivatsanTrapnell2020_sciplex2.h5ad"
SCIPLEX_MD5 = "12a48293a166a859f994551653a2ad8c"
SCIPLEX_BYTES = 145178504
SCIPLEX_SHA256 = "0adabca03632ac9421a769fc9eaa4178447d4d572f4c2c54e4fde93a81acde67"
SCIPLEX_SOURCE = {
    "kind": "public_dataset",
    "provider": "scperturb",
    "dataset_id": SCIPLEX_ID,
    "version": "1.4",
    "revision": "zenodo-13350497",
    "url": "https://zenodo.org/records/13350497",
    "download_url": "https://zenodo.org/records/13350497/files/" + SCIPLEX_FILE,
    "doi": "10.5281/zenodo.13350497",
    "study_accession": "GSE139944/GSM4150377",
    "study_url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4150377",
    "license": "CC-BY-4.0 (scPerturb record)",
}


def registry_path(root: Path) -> Path:
    return root / "data/registry/datasets/scperturb-sciplex2-v1.4.json"


def source_path(root: Path) -> Path:
    return root / "data/raw/scperturb" / SCIPLEX_FILE


@lru_cache(maxsize=8)
def _cached_digest(path: str, size: int, modified: int, changed: int) -> str:
    return file_sha256(Path(path))


def source_available(root: Path, version: DatasetVersion) -> bool:
    path = source_path(root)
    try:
        stat = path.stat()
        return (
            stat.st_size == version.file_bytes
            and _cached_digest(str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            == version.file_sha256
        )
    except OSError:
        return False


def read_dataset(root: Path, dataset_id: str) -> tuple[DatasetVersion, list[Contrast]]:
    if dataset_id != SCIPLEX_ID:
        raise KeyError(dataset_id)
    path = registry_path(root)
    if not path.is_file():
        raise ValueError("数据尚未准备；请由本地分析管理员运行 prepare_sciplex2")
    document = json.loads(path.read_text(encoding="utf-8"))
    version = DatasetVersion.model_validate(document["version"])
    contrasts = [Contrast.model_validate(row) for row in document["contrasts"]]
    if (
        document.get("schema") != "celllens-dataset-v1"
        or version.source != SCIPLEX_SOURCE
        or version.dataset_id != dataset_id
        or version.file != source_path(root).relative_to(root).as_posix()
        or version.file_md5 != SCIPLEX_MD5
        or version.file_bytes != SCIPLEX_BYTES
        or version.file_sha256 != SCIPLEX_SHA256
        or version.id != f"{SCIPLEX_ID}-v1.4-{SCIPLEX_SHA256[:12]}"
        or version.expression_scale != "raw_counts"
        or version.expression_slot != "X"
        or version.provider != SCIPLEX_ID
        or version.species != "human"
        or version.cell_line != "A549"
        or any(row.dataset_version_id != version.id for row in contrasts)
        or len({row.id for row in contrasts}) != len(contrasts)
    ):
        raise ValueError("数据登记与固定官方来源不一致")
    return version, contrasts


def dataset_card(root: Path) -> dict:
    card = {
        "id": SCIPLEX_ID,
        "title": "sciPlex2 · A549 药物响应",
        "version": "1.4",
        "status": "needs_preparation",
        "cell_count": None,
        "total_cell_count": None,
        "condition_count": 0,
        "source": SCIPLEX_SOURCE,
        "perturbation_type": "drug",
        "capabilities": {
            "expression": False,
            "descriptive_comparison": False,
            "prediction": False,
            "formal_differential_expression": False,
        },
        "preparation": "本地运行 python -m scripts.prepare_sciplex2；校验后开放分析",
    }
    try:
        version, contrasts = read_dataset(root, SCIPLEX_ID)
    except ValueError as exc:
        card["status_reason"] = str(exc)
        return card
    ready = source_available(root, version)
    card.update(
        status="ready" if ready else "needs_preparation",
        dataset_version_id=version.id,
        cell_count=version.cell_count,
        total_cell_count=version.total_cell_count,
        gene_count=version.gene_count,
        condition_count=len(contrasts),
        species=version.species,
        cell_line=version.cell_line,
        inspection=version.inspection,
        file_sha256=version.file_sha256,
        expression_scale=version.expression_scale,
        expression_slot=version.expression_slot,
    )
    card["capabilities"].update(expression=ready, descriptive_comparison=ready)
    return card


def list_datasets(root: Path) -> dict:
    return {"items": [dataset_card(root)], "total": 1}


def list_conditions(root: Path, dataset_id: str, query: str = "", limit: int = 10, offset: int = 0) -> dict:
    if dataset_id != SCIPLEX_ID:
        raise KeyError(dataset_id)
    card = dataset_card(root)
    rows = []
    if registry_path(root).is_file():
        _, contrasts = read_dataset(root, dataset_id)
        for contrast in contrasts:
            if query.casefold() in (contrast.label + " " + contrast.cell_line).casefold():
                row = contrast.model_dump(exclude={"observed_filter", "control_filter"})
                row["analysis_available"] = card["status"] == "ready"
                rows.append(row)
    return {
        "dataset": card,
        "items": rows[offset : offset + limit],
        "total": len(rows),
        "limit": limit,
        "offset": offset,
    }


def dataset_analysis_request(root: Path, request: dict) -> dict:
    version, contrasts = read_dataset(root, request["dataset_id"])
    contrast = next((row for row in contrasts if row.id == request["condition_id"]), None)
    if contrast is None:
        raise ValueError("所选条件不属于该冻结数据版本")
    if not source_available(root, version):
        raise ValueError("源数据未准备或校验失败，请重新准备该固定版本")
    maximum = request["max_cells"]
    if not isinstance(maximum, int) or not 1 <= maximum <= 4096:
        raise ValueError("每组 max_cells 必须在 1–4096 之间")
    check_analysis_budget(
        min(maximum, contrast.control_cell_count), min(maximum, contrast.cell_count), version.gene_count
    )
    return {
        **request,
        "cell_line": contrast.cell_line,
        "perturbation": contrast.label,
        "source_cell_count": contrast.cell_count,
        "source": dict(version.source),
        "dataset_version": version.model_dump(),
        "contrast": contrast.model_dump(),
        "source_catalog_sha256": file_sha256(registry_path(root)),
    }
