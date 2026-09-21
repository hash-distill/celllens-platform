from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from backend.app.schemas import CreateRunRequest


def code_fingerprint(project_root: Path) -> str:
    """Hash executable backend/configuration inputs in stable path order."""
    candidates = list((project_root / "backend" / "app").rglob("*.py"))
    for root in (project_root / "configs",):
        if root.is_dir():
            candidates.extend(path for path in root.rglob("*") if path.is_file())
    candidates.extend(
        path for name in ("pyproject.toml", "uv.lock") if (path := project_root / name).is_file()
    )
    digest = hashlib.sha256()
    for path in sorted(set(candidates), key=lambda item: item.relative_to(project_root).as_posix()):
        relative = path.relative_to(project_root).as_posix().encode()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def build_cache_key(
    request: CreateRunRequest,
    assets: dict[str, Any],
    *,
    code_hash: str,
    database_hash: str | None,
) -> str:
    identity = {
        "schema": 1,
        "request": request.model_dump(mode="json"),
        "assets": assets,
        "code_sha256": code_hash,
        "metabolic_database_manifest_sha256": database_hash,
    }
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()
