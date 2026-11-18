"""Bounded browser uploads owned by a workspace, separate from immutable imports.

Only generated upload IDs address storage. A project-wide OS lease serializes
intake, inspection, import and deletion, including across application workers.
"""

import asyncio
import hashlib
import json
import re
import shutil
from contextlib import closing
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from starlette.requests import ClientDisconnect

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.controlled_import import (
    MAX_CELLS,
    MAX_ELEMENTS,
    MAX_GENES,
    _h5_preflight,
    _import_h5ad_source,
)
from backend.app.services.resource_downloads import ResourceLease

ID_PATTERN = re.compile(r"upload_[a-f0-9]{32}")
MAX_COLUMN_VALUES = 1000
MAX_TOTAL_VALUES = 4000


class UploadTooLarge(ValueError):
    pass


class UploadUnavailable(ValueError):
    pass


def capabilities(settings):
    enabled = getattr(settings, "h5ad_upload_enabled", True)
    reason = None if enabled else "管理员已关闭浏览器 H5AD 上传"
    if getattr(settings, "deployment_mode", "local") == "public":
        enabled, reason = False, "公开部署仅提供冻结案例，不接受自有数据上传"
    if enabled:
        try:
            import anndata  # noqa: F401
            import h5py  # noqa: F401
        except ImportError:
            enabled, reason = False, "缺少 H5AD 分析依赖"
    return {
        "available": bool(enabled),
        "reason": reason,
        "mode": "browser-h5ad-upload",
        "max_bytes": getattr(settings, "h5ad_upload_max_bytes", 268_435_456),
        "max_total_bytes": getattr(settings, "h5ad_upload_max_total_bytes", 1_073_741_824),
        "ttl_seconds": getattr(settings, "h5ad_upload_ttl_seconds", 86_400),
        "max_cells": MAX_CELLS,
        "max_genes": MAX_GENES,
        "max_matrix_elements": MAX_ELEMENTS,
        "scales": ["raw_counts", "cp10k", "log1p_cp10k"],
        "custom_prediction_available": False,
    }


def _require_enabled(settings):
    limits = capabilities(settings)
    if not limits["available"]:
        raise UploadUnavailable(limits["reason"])
    return limits


def validate_filename(filename):
    # Filename is display provenance only, never a filesystem path.
    if (
        not filename
        or len(filename) > 200
        or filename != filename.strip()
        or any(ord(char) < 32 or char in '/\\:*?"<>|' for char in filename)
        or not filename.lower().endswith(".h5ad")
        or filename in {".h5ad", "..h5ad"}
    ):
        raise ValueError("请选择单个 .h5ad 文件，文件名不得包含路径或特殊字符")
    return filename


def _base(settings):
    root = settings.project_root.resolve()
    base = root / "data/uploads"
    if base.resolve() != base or not base.resolve().is_relative_to(root):
        raise ValueError("上传存储目录配置不安全")
    base.mkdir(parents=True, exist_ok=True)
    return base


def _directory(base, identifier):
    if not ID_PATTERN.fullmatch(identifier):
        raise KeyError(identifier)
    directory = base / identifier
    if directory.resolve() != directory or directory.is_symlink():
        raise ValueError("上传存储目录配置不安全")
    return directory


def _remove(base, directory):
    if directory.resolve().parent != base.resolve() or directory.is_symlink():
        raise ValueError("上传清理路径不安全")
    if not ID_PATTERN.fullmatch(directory.name):
        raise ValueError("上传清理标识无效")
    if directory.exists():
        shutil.rmtree(directory)


def _cleanup_expired(base, ttl_seconds):
    now = datetime.now(UTC)
    for candidate in base.iterdir():
        if not ID_PATTERN.fullmatch(candidate.name) or not candidate.is_dir():
            continue
        directory = _directory(base, candidate.name)
        metadata = directory / "metadata.json"
        if metadata.is_file():
            document = json.loads(metadata.read_text(encoding="utf-8"))
            expired = datetime.fromisoformat(document["expires_at"]) <= now
        else:
            # A process crash can leave partial bytes. The lease proves no live writer owns them.
            expired = now.timestamp() - directory.stat().st_mtime > ttl_seconds
        if expired:
            _remove(base, directory)


def _usage(base):
    total = 0
    for candidate in base.iterdir():
        if not ID_PATTERN.fullmatch(candidate.name) or not candidate.is_dir():
            continue
        directory = _directory(base, candidate.name)
        for filename in ("source.h5ad", "source.partial"):
            source = directory / filename
            if source.is_symlink() or source.resolve().parent != directory:
                raise ValueError("上传存储文件配置不安全")
            if source.is_file():
                total += source.stat().st_size
    return total


def inspect_h5ad(path):
    """Read bounded metadata after rejecting unsafe HDF storage and oversized matrices."""
    import anndata as ad
    import pandas as pd

    _h5_preflight(path)
    frame = ad.read_h5ad(path, backed="r")
    try:
        genes = frame.var_names.astype(str)
        cells = frame.obs_names.astype(str)
        if not genes.is_unique or not cells.is_unique:
            raise ValueError("基因 ID 和细胞 ID 必须唯一；不会自动合并或改名")
        if any(not gene.strip() or gene != gene.strip() for gene in genes):
            raise ValueError("基因 ID 不得为空或包含首尾空格")
        if any(not cell.strip() for cell in cells):
            raise ValueError("细胞 ID 不得为空")
        if len({gene.upper() for gene in genes}) != len(genes):
            raise ValueError("基因 ID 经大小写规范化后重复")
        if len(frame.obs.columns) > 128 or not frame.obs.columns.is_unique:
            raise ValueError("obs 列不得重复，且最多支持 128 列")
        columns = []
        remaining = MAX_TOTAL_VALUES
        for name in frame.obs.columns:
            if not isinstance(name, str) or not name.strip() or len(name) > 100:
                raise ValueError("obs 列名必须是 1–100 字符的非空文本")
            series = frame.obs[name]
            if not isinstance(series, pd.Series):
                raise ValueError("obs 列必须是单列记录")
            numeric = pd.api.types.is_numeric_dtype(series.dtype) and not pd.api.types.is_bool_dtype(
                series.dtype
            )
            labels = series.dropna().astype(str)
            counts = labels.value_counts(sort=False)
            # Numeric columns remain available for library totals, without thousands of numeric options.
            maximum = 0 if numeric else min(MAX_COLUMN_VALUES, remaining)
            selected = counts.iloc[:maximum]
            values = [
                {"label": str(label), "count": int(count)}
                for label, count in selected.items()
                if len(str(label)) <= 200
            ]
            remaining -= len(values)
            columns.append(
                {
                    "name": name,
                    "dtype": str(series.dtype),
                    "kind": "numeric" if numeric else "categorical",
                    "missing_count": int(series.isna().sum()),
                    "unique_count": int(len(counts)),
                    "values": values,
                    "truncated": len(values) < len(counts),
                }
            )
        suggestions = []
        suggested = None
        backgrounds = frame.obs["cell_line"] if "cell_line" in frame.obs else None
        if isinstance(backgrounds, pd.Series) and not backgrounds.isna().any():
            unique = list(dict.fromkeys(backgrounds.astype(str)))
            suggestions = [label for label in unique[:100] if len(label) <= 32]
            suggested = unique[0] if len(unique) == 1 and suggestions else None
        return {
            "cells": int(frame.n_obs),
            "genes": int(frame.n_vars),
            "obs_columns": columns,
            "gene_preview": [gene for gene in genes[:20] if len(gene) <= 200],
            "cell_line_suggestions": suggestions,
            "suggested_cell_line": suggested,
            "custom_prediction_available": False,
        }
    finally:
        frame.file.close()


async def _thread_complete(function, *args):
    """Finish file-using workers before cancellation releases leases or removes their input."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await asyncio.shield(task)
        except Exception:
            pass
        raise


async def receive_upload(settings, filename, chunks, content_length=None, *, is_disconnected=None):
    limits = _require_enabled(settings)
    filename = validate_filename(filename)
    if content_length is not None and (content_length < 0 or content_length > limits["max_bytes"]):
        raise UploadTooLarge("H5AD 文件超过上传大小上限")
    base = _base(settings)
    with closing(ResourceLease(base / "uploads.lock")):
        _cleanup_expired(base, limits["ttl_seconds"])
        existing_bytes = _usage(base)
        if existing_bytes + (content_length or 0) > limits["max_total_bytes"]:
            raise UploadTooLarge("临时上传空间不足，请先移除旧上传")
        identifier = "upload_" + uuid4().hex
        directory = _directory(base, identifier)
        directory.mkdir()
        complete = False
        try:
            partial = directory / "source.partial"
            size = 0
            digest = hashlib.sha256()
            async with asyncio.timeout(getattr(settings, "h5ad_upload_timeout_seconds", 300)):
                with partial.open("xb") as stream:
                    async for chunk in chunks:
                        size += len(chunk)
                        if size > limits["max_bytes"] or existing_bytes + size > limits["max_total_bytes"]:
                            raise UploadTooLarge("H5AD 文件或临时上传空间超过大小上限")
                        # Bound each disk operation even when an ASGI server yields a large chunk.
                        for offset in range(0, len(chunk), 1024 * 1024):
                            piece = memoryview(chunk)[offset : offset + 1024 * 1024]
                            await _thread_complete(stream.write, piece)
                            digest.update(piece)
            if not size:
                raise ValueError("上传文件为空")
            if content_length is not None and size != content_length:
                raise ValueError("上传字节数与 Content-Length 不一致，请重新上传")
            source = directory / "source.h5ad"
            partial.replace(source)
            try:
                inspected = await _thread_complete(inspect_h5ad, source)
            except (OSError, KeyError, TypeError, AttributeError) as exc:
                raise ValueError("无法读取有效的 H5AD 文件，请检查文件格式及 obs/var 结构") from exc
            # Only probe after exhausting request.stream(): an earlier probe can consume body bytes.
            if is_disconnected is not None and await is_disconnected():
                raise ClientDisconnect()
            now = datetime.now(UTC)
            metadata = {
                "upload_id": identifier,
                "filename": filename,
                "bytes": size,
                "sha256": digest.hexdigest(),
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(seconds=limits["ttl_seconds"])).isoformat(),
                **inspected,
            }
            atomic_write_json(directory / "metadata.json", metadata)
            complete = True
            return metadata
        finally:
            if not complete:
                _remove(base, directory)


def _read(base, identifier):
    directory = _directory(base, identifier)
    path = directory / "metadata.json"
    if not path.is_file():
        raise KeyError(identifier)
    metadata = json.loads(path.read_text(encoding="utf-8"))
    source = directory / "source.h5ad"
    if metadata.get("upload_id") != identifier or source.resolve().parent != directory:
        raise ValueError("上传文件身份不匹配")
    if not source.is_file() or file_sha256(source) != metadata["sha256"]:
        raise ValueError("上传文件已改变，请重新上传")
    return source, metadata


def get_upload(settings, identifier):
    limits = _require_enabled(settings)
    base = _base(settings)
    with closing(ResourceLease(base / "uploads.lock")):
        _cleanup_expired(base, limits["ttl_seconds"])
        return _read(base, identifier)[1]


def delete_upload(settings, identifier):
    _require_enabled(settings)
    base = _base(settings)
    with closing(ResourceLease(base / "uploads.lock")):
        directory = _directory(base, identifier)
        if not directory.is_dir():
            raise KeyError(identifier)
        _remove(base, directory)


def import_upload(settings, identifier, request):
    limits = _require_enabled(settings)
    base = _base(settings)
    with closing(ResourceLease(base / "uploads.lock")):
        _cleanup_expired(base, limits["ttl_seconds"])
        source, metadata = _read(base, identifier)
        return _import_h5ad_source(
            settings,
            request,
            source,
            source_filename=metadata["filename"],
            max_bytes=limits["max_bytes"],
        )
