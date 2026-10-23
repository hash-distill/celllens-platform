"""Read frozen measured results; downloads never execute scientific work."""

import io
import json
import re
import tempfile
import zipfile
from pathlib import Path

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
    if "observed_delta" in frame:
        frame = frame.iloc[frame["observed_delta"].abs().to_numpy().argsort()[::-1]]
    return frame


def table_page(directory, summary, kind, query, limit, offset) -> dict:
    frame = read_table(directory, kind, query)
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
