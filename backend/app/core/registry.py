import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.app.core.errors import AssetNotReadyError, RegistryError
from backend.app.core.run_manifest import file_sha256


class _RegistryRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    cell_line: str = Field(min_length=1)
    enabled: bool = False
    disabled_reason: str | None = None
    license: str | None = None


class _ModelRow(_RegistryRow):
    code_version: str | None = None
    model_dir: str | None = None
    checkpoint_path: str | None = None
    checkpoint_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    config_path: str | None = None
    config_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    gene_list_path: str | None = None
    gene_list_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    embed_key: str | None = None
    perturbation_column: str | None = None
    cell_type_column: str | None = None
    control_perturbation: str | None = None
    supported_perturbations: list[str] = Field(default_factory=list)


class _DatasetRow(_RegistryRow):
    control_path: str | None = None
    control_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    observed_path: str | None = None
    observed_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    split_path: str | None = None
    split_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class RegistryEntry:
    payload: dict[str, Any]
    project_root: Path

    def path(self, key: str) -> Path:
        value = self.payload.get(key)
        if not value:
            raise RegistryError(f"Registry field {key!r} is missing for {self.payload.get('id')}")
        root = self.project_root.resolve()
        resolved = (root / value).resolve()
        if not resolved.is_relative_to(root):
            raise RegistryError(f"Registry path is outside project root: {resolved}")
        return resolved

    def asset_is_valid(self, path_field: str, hash_field: str) -> bool:
        try:
            path = self.path(path_field)
        except RegistryError:
            return False
        expected = self.payload.get(hash_field)
        return bool(path.is_file() and expected and file_sha256(path).lower() == str(expected).lower())

    @property
    def enabled(self) -> bool:
        return bool(self.payload.get("enabled", False))


class AssetRegistry:
    def __init__(self, project_root: Path, registry_root: Path):
        self.project_root = project_root.resolve()
        self.registry_root = registry_root.resolve()
        self.models = self._load("models.json", "models")
        self.datasets = self._load("datasets.json", "datasets")

    def _load(self, filename: str, key: str) -> list[dict[str, Any]]:
        path = self.registry_root / filename
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            rows = document[key]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RegistryError(f"Cannot load {path}: {exc}") from exc
        if not isinstance(rows, list):
            raise RegistryError(f"{path} field {key!r} must be a list")
        schema = _ModelRow if key == "models" else _DatasetRow
        try:
            return [schema.model_validate(row).model_dump() for row in rows]
        except ValidationError as exc:
            raise RegistryError(f"Invalid registry row in {path}: {exc}") from exc

    def model_for(self, cell_line: str, require_enabled: bool = True) -> RegistryEntry:
        for row in self.models:
            if row.get("cell_line") == cell_line:
                entry = RegistryEntry(row, self.project_root)
                if require_enabled and not entry.enabled:
                    reason = row.get("disabled_reason") or f"Model for {cell_line} is disabled"
                    raise AssetNotReadyError(reason)
                return entry
        raise RegistryError(f"No model registered for {cell_line}")

    def dataset_for(self, cell_line: str, require_enabled: bool = True) -> RegistryEntry:
        for row in self.datasets:
            if row.get("cell_line") == cell_line:
                entry = RegistryEntry(row, self.project_root)
                if require_enabled and not entry.enabled:
                    reason = row.get("disabled_reason") or f"Dataset for {cell_line} is disabled"
                    raise AssetNotReadyError(reason)
                return entry
        raise RegistryError(f"No dataset registered for {cell_line}")

    def supported_perturbations(self, cell_line: str) -> list[str]:
        entry = self.model_for(cell_line, require_enabled=False)
        return sorted({str(item).upper() for item in entry.payload.get("supported_perturbations", [])})

    def verify_entry(self, entry: RegistryEntry, path_field: str, hash_field: str) -> str:
        path = entry.path(path_field)
        expected = entry.payload.get(hash_field)
        if not path.is_file():
            raise AssetNotReadyError(f"Missing registered asset: {path}")
        if not expected:
            raise AssetNotReadyError(f"Missing {hash_field} for {entry.payload.get('id')}")
        actual = file_sha256(path)
        if actual.lower() != str(expected).lower():
            raise AssetNotReadyError(f"SHA-256 mismatch for {path.name}: expected {expected}, got {actual}")
        return actual
