import json
from collections import OrderedDict
from collections.abc import Callable
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi.responses import JSONResponse, Response

from backend.app.core.cache import code_fingerprint
from backend.app.core.run_manifest import atomic_write_json, file_sha256, manifest_hash

_lock = Lock()
# Fingerprints and snapshot bytes are still checked on every request. This only
# avoids repeatedly parsing and serializing an already verified 1 MB JSON body.
_encoded_snapshots: OrderedDict[Path, tuple[str, str, bytes]] = OrderedDict()


def _response(body: bytes) -> Response:
    return Response(body, media_type="application/json", headers={"Cache-Control": "no-store"})


def _fingerprint(root: Path, cell_line: str | None, models: list[dict[str, Any]]) -> str:
    files: dict[str, str | None] = {}
    for folder in (root / "data/registry", root / "backend/app/resources"):
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                if not path.resolve().is_relative_to(root.resolve()):
                    raise ValueError("Catalogue input is outside the project")
                files[path.relative_to(root).as_posix()] = file_sha256(path)
    for model in models:
        if model.get("enabled") and model.get("gene_list_path"):
            path = (root / model["gene_list_path"]).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError("Model panel is outside the project")
            files[path.relative_to(root).as_posix()] = file_sha256(path) if path.is_file() else None
    return manifest_hash(
        {
            "schema": 1,
            "cell_line": cell_line,
            "models": models,
            "files": files,
            "code": code_fingerprint(root),
            "packages": {name: version(name) for name in ("sccellfie", "anndata", "pandas", "numpy")},
        }
    )


def model_catalog_response(
    root: Path, cell_line: str | None, models: list[dict[str, Any]], build: Callable[[], JSONResponse]
) -> Response:
    with _lock:
        fingerprint = _fingerprint(root, cell_line, models)
        path = root / "data/derived/catalog-cache" / (manifest_hash({"cell_line": cell_line}) + ".json")
        try:
            raw = path.read_bytes()
            raw_sha256 = sha256(raw).hexdigest()
            memo = _encoded_snapshots.get(path)
            if memo is not None and memo[:2] == (fingerprint, raw_sha256):
                if _fingerprint(root, cell_line, models) != fingerprint:
                    raise ValueError("Catalogue inputs changed while reading the snapshot")
                _encoded_snapshots.move_to_end(path)
                return _response(memo[2])
            cached = json.loads(raw)
            if (
                cached["fingerprint"] == fingerprint
                and manifest_hash(cached["body"]) == cached["body_sha256"]
                and _fingerprint(root, cell_line, models) == fingerprint
            ):
                body_bytes = bytes(JSONResponse(cached["body"]).body)
                _encoded_snapshots[path] = (fingerprint, raw_sha256, body_bytes)
                _encoded_snapshots.move_to_end(path)
                if len(_encoded_snapshots) > 8:
                    _encoded_snapshots.popitem(last=False)
                return _response(body_bytes)
        except (OSError, ValueError, KeyError, TypeError):
            pass
        response = build()
        if _fingerprint(root, cell_line, models) != fingerprint:
            raise ValueError("Catalogue inputs changed while building the snapshot")
        body = json.loads(bytes(response.body))
        try:
            atomic_write_json(
                path,
                {
                    "fingerprint": fingerprint,
                    "body": body,
                    "body_sha256": manifest_hash(body),
                },
            )
        except OSError:
            pass
        return response
