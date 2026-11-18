"""Read frozen measured results; downloads never execute scientific work."""

import io
import json
import re
import tempfile
import zipfile
from pathlib import Path
from typing import cast

import pandas as pd

from backend.app.core.run_manifest import file_sha256


def result_directory(root: Path, identifier: str) -> Path:
    if not re.fullmatch(r"measured_[a-f0-9]{24}", identifier):
        raise KeyError(identifier)
    return root.resolve() / "data/derived/measured" / identifier


def confined(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError("实测结果路径越界")
    return path


def verified_result(root: Path, identifier: str, expected: str | None) -> tuple[Path, dict, dict]:
    directory = result_directory(root, identifier)
    path = directory / "manifest.json"
    if not expected or not path.is_file() or file_sha256(path) != expected:
        raise ValueError("实测结果清单校验失败，请创建新分析")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest["id"] != identifier or manifest["source_kind"] != "measured":
        raise ValueError("实测结果标识不匹配")
    for item in directory.rglob("*"):
        relative = item.relative_to(directory).as_posix()
        if (
            item.is_file()
            and relative not in manifest["files"]
            and relative not in {"manifest.json", "request.json"}
        ):
            raise ValueError("实测目录出现未登记产物，未作为有效结果提供")
    for relative, digest in manifest["files"].items():
        item = confined(directory, relative)
        if not item.is_file() or file_sha256(item) != digest:
            raise ValueError("实测分析文件已变化，原结果不可继续使用")
    for entry in manifest["inputs"]["groups"].values():
        for source in (entry, entry.get("source_reference")):
            if source:
                item = confined(root, source["path"])
                if not item.is_file() or file_sha256(item) != source["sha256"]:
                    raise ValueError("实测输入文件已变化，请核对来源并创建新分析")
    for relative, digest in manifest["inputs"].get("analysis_assets", {}).items():
        item = confined(root, relative)
        if not item.is_file() or file_sha256(item) != digest:
            raise ValueError("实测分析使用的知识库或基因映射已变化，请核对后重新分析")
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    return directory, summary, manifest


def read_table(directory: Path, kind: str, query: str = "") -> pd.DataFrame:
    path = directory / f"{kind}.csv"
    if not path.is_file():
        raise ValueError("该分析未生成此结果；请查看摘要中的原因")
    frame = pd.read_csv(path, keep_default_na=False)
    if query:
        fields = [key for key in ("gene", "task", "label", "reaction") if key in frame]
        mask = pd.Series(False, index=frame.index)
        for key in fields:
            mask |= frame[key].astype(str).str.contains(query, case=False, regex=False)
        frame = frame.loc[mask]
    if kind == "genes" and "observed_delta" in frame:
        frame = frame.iloc[frame["observed_delta"].abs().to_numpy().argsort()[::-1]]
    return order_function_rows(frame, kind)


def order_function_rows(frame: pd.DataFrame, kind: str) -> pd.DataFrame:
    if kind == "tasks":
        frame = frame.copy()
        column = frame.get("gene_fraction", pd.Series(index=frame.index, dtype=float))
        if not isinstance(column, pd.Series):
            raise ValueError("任务覆盖列存在重复标识")
        coverage = cast(pd.Series, pd.to_numeric(column, errors="coerce"))
        frame["_coverage_order"] = coverage.where(coverage.between(0, 1), -1).fillna(-1)
        keys = [
            "_coverage_order",
            *(key for key in ("category", "subcategory", "label", "task") if key in frame),
        ]
        return frame.sort_values(
            keys, ascending=[False, *([True] * (len(keys) - 1))], na_position="last", kind="stable"
        ).drop(columns="_coverage_order")
    if kind == "reactions" and "reaction" in frame:
        return frame.sort_values("reaction", kind="stable")
    return frame


def task_categories(directory: Path, summary: dict, frame: pd.DataFrame) -> pd.DataFrame:
    """Attach only Task-Info metadata from the knowledge version frozen by this result."""
    frame = frame.copy()
    frame["category"], frame["subcategory"] = None, None
    provenance = summary.get("metabolism", {}).get("database_provenance", {})
    expected = provenance.get("files", {}).get("Task-Info.csv")
    if not expected or not provenance.get("manifest_sha256") or "task" not in frame:
        return frame
    if len(directory.resolve().parents) < 4:
        return frame
    database = directory.resolve().parents[3] / "data/registry/sccellfie/human"
    manifest_path, info_path = database / "manifest.json", database / "Task-Info.csv"
    try:
        if file_sha256(manifest_path) != provenance["manifest_sha256"] or file_sha256(info_path) != expected:
            return frame
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            manifest.get("version") != summary.get("metabolism", {}).get("database_version")
            or manifest.get("files", {}).get("Task-Info.csv") != expected
        ):
            return frame
        info = pd.read_csv(info_path, keep_default_na=False)
        if not {"Task", "System", "Subsystem"}.issubset(info.columns) or info["Task"].duplicated().any():
            return frame
        if file_sha256(info_path) != expected or file_sha256(manifest_path) != provenance["manifest_sha256"]:
            return frame
        metadata = info.set_index("Task")
        for output, column in (("category", "System"), ("subcategory", "Subsystem")):
            identifiers, labels = frame["task"], metadata[column]
            if not isinstance(identifiers, pd.Series) or not isinstance(labels, pd.Series):
                return frame
            frame[output] = identifiers.map(labels).replace("", None)
    except (OSError, ValueError, KeyError):
        return frame
    return frame


def table_page(directory, summary, kind, query, limit, offset) -> dict:
    frame = read_table(directory, kind, query)
    if kind == "tasks":
        frame = order_function_rows(task_categories(directory, summary, frame), kind)
    units = summary["expression_units"] if kind == "genes" else "expression-derived scCellFie score"
    return {
        "items": json.loads(frame.iloc[offset : offset + limit].to_json(orient="records")),
        "total": len(frame),
        "limit": limit,
        "offset": offset,
        "units": units,
    }


def csv_bytes(directory: Path, summary: dict, kind: str) -> bytes:
    frame = read_table(directory, kind)
    for key in ("analysis_id", "source_kind", "cell_line", "perturbation"):
        frame[key] = summary[key]
    for name, count in summary["counts"].items():
        frame[f"{name}_cells"] = count
    frame["units"] = summary["expression_units"] if kind == "genes" else "expression-derived scCellFie score"
    # Spreadsheet consumers must not execute any label as a formula.
    for key in frame.select_dtypes(include="object"):
        frame[key] = frame[key].map(
            lambda value: (
                "'" + value
                if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r"))
                else value
            )
        )
    stream = io.StringIO(newline="")
    frame.to_csv(stream, index=False)
    return stream.getvalue().encode("utf-8-sig")


def bundle_stream(directory: Path, manifest: dict):
    stream = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    try:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for relative in (*manifest["files"], "manifest.json"):
                archive.write(confined(directory, relative), relative)
        stream.seek(0)
        while chunk := stream.read(1024 * 1024):
            yield chunk
    finally:
        stream.close()
