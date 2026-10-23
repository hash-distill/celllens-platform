import json
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi.responses import JSONResponse

from backend.app.core.cache import code_fingerprint
from backend.app.core.run_manifest import atomic_write_json, file_sha256, manifest_hash

_lock = Lock()


def _fingerprint(root: Path, cell_line: str | None, models: list[dict[str, Any]]) -> str:
    files: dict[str, str | None] = {}
    for folder in (root / 'data/registry', root / 'backend/app/resources'):
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                if not path.resolve().is_relative_to(root.resolve()):
                    raise ValueError('Catalogue input is outside the project')
                files[path.relative_to(root).as_posix()] = file_sha256(path)
    for model in models:
        if model.get('enabled') and model.get('gene_list_path'):
            path = (root / model['gene_list_path']).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError('Model panel is outside the project')
            files[path.relative_to(root).as_posix()] = file_sha256(path) if path.is_file() else None
    return manifest_hash({
        'schema': 1, 'cell_line': cell_line, 'models': models, 'files': files,
        'code': code_fingerprint(root),
        'packages': {name: version(name) for name in ('sccellfie', 'anndata', 'pandas', 'numpy')},
    })


def model_catalog_response(
    root: Path, cell_line: str | None, models: list[dict[str, Any]], build: Callable[[], JSONResponse]
) -> JSONResponse:
    with _lock:
        fingerprint = _fingerprint(root, cell_line, models)
        path = root / 'data/derived/catalog-cache' / (manifest_hash({'cell_line': cell_line}) + '.json')
        try:
            cached = json.loads(path.read_text(encoding='utf-8'))
            if (
                cached['fingerprint'] == fingerprint
                and manifest_hash(cached['body']) == cached['body_sha256']
                and _fingerprint(root, cell_line, models) == fingerprint
            ):
                return JSONResponse(cached['body'], headers={'Cache-Control': 'no-store'})
        except (OSError, ValueError, KeyError, TypeError):
            pass
        response = build()
        if _fingerprint(root, cell_line, models) != fingerprint:
            raise ValueError('Catalogue inputs changed while building the snapshot')
        body = json.loads(bytes(response.body))
        try:
            atomic_write_json(path, {
                'fingerprint': fingerprint, 'body': body, 'body_sha256': manifest_hash(body),
            })
        except OSError:
            pass
        return response
