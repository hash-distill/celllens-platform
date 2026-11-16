"""Restore completed historical artifacts into a separate deployment, without inference.

Source files remain unchanged. Every manifest-listed output and prepared figure
is checked before copying. Existing destination IDs are never replaced.
"""

import argparse
import json
import mimetypes
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath

from backend.app.config import Settings
from backend.app.container import build_container
from backend.app.core.run_manifest import file_sha256
from backend.app.db.models import RunArtifactModel, RunEventModel, RunModel
from backend.app.schemas import CreateRunRequest, RunStatus


def source_file(root: Path, name: str) -> Path:
    if not isinstance(name, str) or Path(name).is_absolute() or PureWindowsPath(name).drive:
        raise ValueError("Source artifact path must be relative")
    if ".." in Path(name).parts or ".." in PureWindowsPath(name).parts:
        raise ValueError("Source artifact path escapes selected directory")
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()) or path.resolve() == root.resolve():
        raise ValueError("Source artifact path escapes selected directory")
    if not path.is_file():
        raise ValueError(f"Missing source artifact: {name}")
    return path


def json_source(root: Path, name: str):
    path = source_file(root, name)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Historical metadata exceeds the import limit")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("Historical metadata must be an object")
    return value


def validate(source: Path, identifier: str):
    if not re.fullmatch(r"run_[A-Za-z0-9_]{1,36}", identifier):
        raise ValueError("Invalid historical run ID")
    manifest_path = source_file(source, "manifest.json")
    manifest = json_source(source, "manifest.json")
    request = CreateRunRequest.model_validate(manifest["request"])
    if request.mode not in {"online", "validation"} or manifest.get("source_type"):
        raise ValueError("Only original real run manifests may be restored")
    summary = json_source(source, "summary.json")
    if summary.get("result_kind") not in {None, "frozen_model_result"}:
        raise ValueError("Synthetic or unknown result kinds cannot be restored as real research")
    if (
        summary.get("status") != "completed"
        or summary.get("run_id") != identifier
        or summary.get("cell_line") != request.cell_line
        or summary.get("perturbation") != request.perturbation
    ):
        raise ValueError("Summary and source identity differ")
    outputs = manifest.get("outputs", {})
    if not {"summary.json", "gene_deltas.csv", "expression_contract.json", "predicted.h5ad"}.issubset(
        outputs
    ):
        raise ValueError("A verified real expression contract is required")
    files = [manifest_path]
    for name, entry in outputs.items():
        path = source_file(source, name)
        if path in files or not isinstance(entry, dict) or file_sha256(path) != entry.get("sha256"):
            raise ValueError(f"Source artifact integrity failure: {name}")
        files.append(path)
    contract = json_source(source, "expression_contract.json")
    scales = contract.get("source_scales", {})
    if (
        contract.get("analysis_version") != "expression-cp10k-v2"
        or contract.get("run_id") != identifier
        or contract.get("gene_units") != "mean(log1p(CP10K))"
        or contract.get("predicted_values_are_measured_counts") is not False
        or any(
            scales.get(key) not in {"raw_counts", "cp10k", "log1p_cp10k"} for key in ("control", "predicted")
        )
    ):
        raise ValueError("Historical expression units or source contract are not verified")
    assets = manifest.get("assets", {})
    if (
        not assets.get("model_id")
        or not assets.get("dataset_id")
        or any(
            not re.fullmatch(r"[a-fA-F0-9]{64}", str(assets.get(key, "")))
            for key in ("checkpoint_sha256", "control_sha256", "gene_list_sha256")
        )
    ):
        raise ValueError("Historical model/data provenance is incomplete")
    prepared_path = source / "cell_state/prepared.json"
    if prepared_path.is_file():
        prepared_path = source_file(source, "cell_state/prepared.json")
        prepared = json_source(source, "cell_state/prepared.json")
        if (
            prepared.get("schema_version") != 1
            or prepared.get("run_id") != identifier
            or prepared.get("source_manifest_sha256") != file_sha256(manifest_path)
        ):
            raise ValueError("Prepared figure provenance differs")
        required = {"plot_data.npz"}
        for key in prepared.get("figures", {}):
            if key not in {"expression_pca", "expression_umap", "metabolic_pca", "metabolic_umap"}:
                raise ValueError("Unknown prepared figure contract")
            required.update({f"{key}.json", f"{key}.svg"})
        if not required.issubset(prepared.get("outputs", {})):
            raise ValueError("Prepared figure outputs are incomplete")
        files.append(prepared_path)
        for name, expected in prepared["outputs"].items():
            path = source_file(prepared_path.parent, name)
            if path in files or file_sha256(path) != expected:
                raise ValueError(f"Prepared figure integrity failure: {name}")
            files.append(path)
    return manifest, request, files


def restore(container, source_root: Path, identifier: str):
    if container.settings.project_root.resolve().is_relative_to(source_root.resolve()):
        raise ValueError("Source and destination projects must be separate")
    source = (source_root.resolve() / "data/derived/runs" / identifier).resolve()
    if not source.is_relative_to(source_root.resolve()):
        raise ValueError("Source escapes selected project")
    manifest, request, files = validate(source, identifier)
    original_hashes = {file.relative_to(source).as_posix(): file_sha256(file) for file in files}
    destination = container.settings.derived_root / identifier
    if destination.exists():
        raise ValueError(f"Destination exists; refusing replacement: {identifier}")
    try:
        container.store.get(identifier)
    except KeyError:
        pass
    else:
        raise ValueError("Destination database already contains this ID")
    stage = destination.with_name(identifier + ".importing")
    if stage.exists():
        raise ValueError("An interrupted import staging directory exists; inspect it first")
    stage.mkdir(parents=True)
    for file in files:
        target = stage / file.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
        if file_sha256(target) != original_hashes[file.relative_to(source).as_posix()]:
            raise ValueError("Copied artifact differs from verified source")
    # Revalidate the copied snapshot against its copied manifest before publication.
    copied_manifest, copied_request, _ = validate(stage, identifier)
    if copied_manifest != manifest or copied_request != request:
        raise ValueError("Source contract changed while restoring; import was not published")
    if any(file_sha256(source / name) != digest for name, digest in original_hashes.items()):
        raise ValueError("Source changed while restoring; import was not published")
    if destination.exists():
        raise ValueError("Destination appeared while restoring; refusing replacement")
    stage.replace(destination)
    # Publish the completed row, artifact index and event in one transaction. Never
    # expose a queued row that an external worker could claim for new inference.
    now = datetime.now(UTC)
    with container.store.session_factory.begin() as session:
        session.add(
            RunModel(
                run_id=identifier,
                mode=request.mode,
                cell_line=request.cell_line,
                perturbation=request.perturbation,
                n_cells=request.n_cells,
                seed=request.seed,
                status=RunStatus.COMPLETED.value,
                stage_progress=100,
                request_json=request.model_dump(mode="json"),
                created_at=now,
                updated_at=now,
                warnings_json=[
                    *manifest.get("warnings", []),
                    "从核验通过的历史产物恢复；记录创建时间为导入时间，未重新执行模型。",
                ],
            )
        )
        session.flush()
        for file in files:
            relative = file.relative_to(source)
            path = destination / relative
            kind = (
                "cell_state_preparation" if relative.as_posix() == "cell_state/prepared.json" else path.stem
            )
            if relative.parts[0] == "cell_state" and kind != "cell_state_preparation":
                continue
            session.add(
                RunArtifactModel(
                    run_id=identifier,
                    kind=kind,
                    relative_path=f"{identifier}/{relative.as_posix()}",
                    sha256=file_sha256(path),
                    size_bytes=path.stat().st_size,
                    created_at=now,
                    mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                )
            )
        session.add(
            RunEventModel(
                run_id=identifier,
                from_status=None,
                to_status=RunStatus.COMPLETED.value,
                stage_progress=100,
                created_at=now,
                message="Historical artifacts restored after SHA256 verification; no model inference",
            )
        )
    return {
        "run_id": identifier,
        "status": "restored",
        "files_verified": len(files),
        "manifest_sha256": file_sha256(destination / "manifest.json"),
        "new_inference": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--run-id", action="append", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.resolve().is_relative_to(args.source_root.resolve()):
        raise ValueError("Import report must be outside the unchanged source project")
    container = build_container(Settings())
    if args.source_root.resolve() == container.settings.project_root.resolve():
        raise ValueError("Source and destination projects must be separate")
    report = [restore(container, args.source_root, identifier) for identifier in args.run_id]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
