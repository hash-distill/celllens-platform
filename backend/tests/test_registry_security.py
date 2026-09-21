import json
from pathlib import Path

import pytest

from backend.app.core.errors import RegistryError
from backend.app.core.registry import AssetRegistry, RegistryEntry


def test_registry_path_cannot_escape_project_root(tmp_path: Path):
    entry = RegistryEntry({"id": "bad", "path": "../outside.txt"}, tmp_path)
    with pytest.raises(RegistryError, match="outside project root"):
        entry.path("path")


def test_registry_rejects_unknown_fields(tmp_path: Path):
    registry = tmp_path / "data" / "registry"
    registry.mkdir(parents=True)
    (registry / "models.json").write_text(
        json.dumps({"models": [{"id": "bad", "cell_line": "K562", "typo": True}]}),
        encoding="utf-8",
    )
    (registry / "datasets.json").write_text('{"datasets": []}', encoding="utf-8")
    with pytest.raises(RegistryError, match="Invalid registry row"):
        AssetRegistry(tmp_path, registry)
