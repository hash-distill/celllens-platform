import json

from backend.app.config import get_settings
from backend.app.core.diagnostic_protocol import load_diagnostic_protocol
from backend.app.core.registry import AssetRegistry
from backend.app.core.run_manifest import file_sha256
from backend.app.services.gene_identity import GeneIdentityAdapter


def _verify_declared(registry, entry, pairs, failures, label):
    for path_field, hash_field in pairs:
        if not entry.payload.get(path_field):
            continue
        try:
            digest = registry.verify_entry(entry, path_field, hash_field)
            print(f"OK {label} {path_field} {digest}")
        except Exception as exc:
            failures.append(str(exc))


def _audit_sccellfie(root, failures):
    manifest_path = root / "manifest.json"
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        failures.append(f"Cannot read scCellFie manifest: {exc}")
        return
    if not document.get("enabled"):
        print(f"SKIP scCellFie database: {document.get('note', 'disabled')}")
        return
    files = document.get("files", {})
    if len(files) != 6:
        failures.append("Enabled scCellFie manifest must contain exactly six database file hashes")
        return
    for filename, expected in files.items():
        path = (root / filename).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            failures.append(f"Missing scCellFie file: {filename}")
            continue
        actual = file_sha256(path)
        if actual.lower() != str(expected).lower():
            failures.append(f"scCellFie SHA-256 mismatch: {filename}")
        else:
            print(f"OK scCellFie {filename} {actual}")


def main() -> int:
    settings = get_settings()
    registry = AssetRegistry(settings.project_root, settings.registry_root)
    failures: list[str] = []
    for row in registry.models:
        if not row.get("enabled"):
            print(f"SKIP model {row.get('id')}: {row.get('disabled_reason')}")
            continue
        entry = registry.model_for(row["cell_line"])
        if not row.get("expression_scale"):
            failures.append(f"Model {row['id']} has no declared expression scale")
        _verify_declared(
            registry,
            entry,
            (
                ("checkpoint_path", "checkpoint_sha256"),
                ("gene_list_path", "gene_list_sha256"),
                ("config_path", "config_sha256"),
            ),
            failures,
            f"model {row['id']}",
        )
    for row in registry.datasets:
        if not row.get("enabled"):
            print(f"SKIP dataset {row.get('id')}: {row.get('disabled_reason')}")
            continue
        entry = registry.dataset_for(row["cell_line"])
        if not row.get("expression_scale"):
            failures.append(f"Dataset {row['id']} has no declared expression scale")
        _verify_declared(
            registry,
            entry,
            (
                ("control_path", "control_sha256"),
                ("observed_path", "observed_sha256"),
                ("split_path", "split_sha256"),
                ("validation_protocol_path", "validation_protocol_sha256"),
            ),
            failures,
            f"dataset {row['id']}",
        )
        if row.get("validation_protocol_path"):
            try:
                protocol = load_diagnostic_protocol(entry, registry.model_for(row["cell_line"]))
                print(f"OK measured diagnostic {row['cell_line']} {protocol['perturbations']}")
            except Exception as exc:
                failures.append(f"Diagnostic protocol audit failed: {exc}")
    _audit_sccellfie(settings.sccellfie_database_root, failures)
    if settings.gene_identity_root.exists():
        try:
            adapter = GeneIdentityAdapter.load(settings.gene_identity_root, settings.sccellfie_database_root)
            print(f"OK HGNC identity {len(adapter.by_id)} database genes")
        except Exception as exc:
            failures.append(f"HGNC identity audit failed: {exc}")
    for message in failures:
        print(f"ERROR {message}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
