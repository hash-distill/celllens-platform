"""Durable, provenance-bound plotting data prepared by the worker, never by GET."""

import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd

from backend.app.core.run_manifest import atomic_write_json, file_sha256

ARTIFACT_KIND = "cell_state_preparation"
VERSION = 1


def prepared_manifest(container: Any, inputs: dict[str, Any]) -> tuple[Path, dict[str, Any]] | None:
    from backend.app.services.cell_state import CellStateUnavailable, _checked, _run_root

    run_id = inputs["run_id"]
    matches = [a for a in container.store.artifacts(run_id) if getattr(a, "kind", None) == ARTIFACT_KIND]
    root = _run_root(container, run_id) / "cell_state"
    if not matches:
        if root.exists():
            raise CellStateUnavailable("Prepared cell-state bundle is not registered")
        return None
    if len(matches) != 1 or matches[0].relative_path != f"{run_id}/cell_state/prepared.json":
        raise CellStateUnavailable("Prepared cell-state identity is ambiguous")
    path = _checked(root / "prepared.json", matches[0].sha256)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        manifest.get("schema_version") != VERSION
        or manifest.get("run_id") != run_id
        or manifest.get("source_manifest_sha256") != inputs["manifest_sha256"]
    ):
        raise CellStateUnavailable("Prepared cell-state source manifest changed")
    # Check this even on default-document and in-memory hits.
    _checked(root / "plot_data.npz", manifest["outputs"].get("plot_data.npz"))
    return root, manifest


def prepared_document(
    container: Any, inputs: dict[str, Any], kind: str, feature: str, embedding: str, space: str
) -> dict[str, Any] | None:
    from backend.app.services.cell_state import CellStateUnavailable, _checked

    bundle = prepared_manifest(container, inputs)
    if bundle is None:
        return None
    root, manifest = bundle
    key = f"{space}_{embedding}"
    default = manifest["figures"].get(key)
    if default is None and space in manifest["unavailable"]:
        raise CellStateUnavailable(manifest["unavailable"][space])
    if default is None or kind != default["kind"] or (feature and feature != default["feature"]):
        return None
    path = _checked(root / f"{key}.json", manifest["outputs"].get(f"{key}.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def prepared_figure(container: Any, document: dict[str, Any]) -> bytes | None:
    from backend.app.services.cell_state import _checked, frozen_inputs

    inputs = frozen_inputs(container, document["run_id"])
    bundle = prepared_manifest(container, inputs)
    if bundle is None:
        return None
    root, manifest = bundle
    embedding = "umap" if document["method"] == "joint-umap" else "pca"
    key = f"{document['embedding_space']}_{embedding}"
    default = manifest["figures"].get(key)
    if not default or document["feature"] != default["document_feature"]:
        return None
    return _checked(root / f"{key}.svg", manifest["outputs"].get(f"{key}.svg")).read_bytes()


def _save_data(path: Path, data: dict[str, Any]) -> None:
    arrays = {f"expression_{source}": matrix for source, matrix in data["matrices"].items()}
    metadata = {key: data[key] for key in (
        "genes", "gene_order", "task_order", "sources", "ids", "expression_slots"
    )}
    metadata["task_columns"] = data["scores"].drop(columns="source").columns.tolist()
    arrays["task_scores"] = data["scores"].drop(columns="source").to_numpy(dtype=float)
    metadata["projections"] = {}
    for space, projection in (("expression", data), ("metabolic", data.get("metabolic"))):
        if projection is None:
            continue
        description = {"variance": projection["variance"]}
        if "umap" in projection:
            description["umap_parameters"] = projection["umap"][1]
        if space == "metabolic":
            description["preprocessing"] = projection["preprocessing"]
        metadata["projections"][space] = description
        for source in data["matrices"]:
            arrays[f"{space}_pca_{source}"] = projection["coordinates"][source]
            if "umap" in projection:
                arrays[f"{space}_umap_{source}"] = projection["umap"][0][source]
    arrays["metadata"] = np.asarray(json.dumps(metadata, ensure_ascii=False))
    np.savez_compressed(path, **arrays)


def load_prepared_data(container: Any, inputs: dict[str, Any]) -> dict[str, Any] | None:
    bundle = prepared_manifest(container, inputs)
    if bundle is None:
        return None
    root, _ = bundle
    with np.load(root / "plot_data.npz", allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata"].item()))
        names = [name for name in ("control", "predicted", "observed") if name in metadata["sources"]]
        data = {key: metadata[key] for key in (
            "genes", "gene_order", "task_order", "sources", "ids", "expression_slots"
        )}
        data["matrices"] = {name: archive[f"expression_{name}"] for name in names}
        data["scores"] = pd.DataFrame(
            archive["task_scores"], index=data["ids"], columns=metadata["task_columns"]
        )
        data["scores"]["source"] = data["sources"]
        data["inputs"] = inputs
        for space, description in metadata["projections"].items():
            projection = data if space == "expression" else {}
            projection["coordinates"] = {name: archive[f"{space}_pca_{name}"] for name in names}
            projection["variance"] = description["variance"]
            if "umap_parameters" in description:
                projection["umap"] = (
                    {name: archive[f"{space}_umap_{name}"] for name in names},
                    description["umap_parameters"],
                )
            if space == "metabolic":
                projection["preprocessing"] = description["preprocessing"]
                data["metabolic"] = projection
    return data


def prepare_cell_state_artifacts(
    container: Any, run_id: str, *, source_root: Path | None = None
) -> dict[str, Any]:
    """Finish all costly embeddings and default SVGs before a worker completes a run."""
    from backend.app.services.cell_state import (
        CellStateUnavailable,
        _checked,
        _reconstruct,
        _run_root,
        cell_state_document,
        frozen_inputs,
    )
    from backend.app.services.cell_state_figure import render_cell_state

    if source_root is not None:
        # A worker verifies a sealed staging manifest before any DB publication.
        # Staged registrations are local; the pipeline registers the published bundle.
        artifacts = [SimpleNamespace(
            kind="manifest", relative_path=f"{run_id}/manifest.json",
            sha256=file_sha256(source_root / "manifest.json"),
        )]

        def register(run: str, kind: str, relative: str, sha: str, size: int, mime: str) -> None:
            artifacts.append(SimpleNamespace(kind=kind, relative_path=relative, sha256=sha))

        container = SimpleNamespace(
            registry=container.registry, settings=container.settings,
            _cell_state_staging_root=source_root,
            store=SimpleNamespace(
                get=container.store.get, artifacts=lambda _: artifacts, register_artifact=register,
            ),
        )
    inputs = frozen_inputs(container, run_id)
    root = _run_root(container, run_id)
    final = root / "cell_state"
    existing = [a for a in container.store.artifacts(run_id) if getattr(a, "kind", None) == ARTIFACT_KIND]
    if existing:
        bundle = prepared_manifest(container, inputs)
        assert bundle is not None
        for name, sha in bundle[1]["outputs"].items():
            _checked(final / name, sha)
        return bundle[1]
    # Recover a fully published bundle if registration was interrupted.
    if final.exists():
        manifest = json.loads((final / "prepared.json").read_text(encoding="utf-8"))
        if manifest.get("source_manifest_sha256") != inputs["manifest_sha256"]:
            raise CellStateUnavailable("Prepared source manifest changed")
        for name, sha in manifest["outputs"].items():
            _checked(final / name, sha)
    else:
        partial = root / f".cell_state-{uuid.uuid4().hex}.partial"
        partial.mkdir()
        figures = {}
        skipped = {}
        try:
            # Keep a strong local reference, independent of the four-run request LRU.
            data = _reconstruct(inputs)
            for space, kind in (("expression", "gene"), ("metabolic", "task")):
                for embedding in ("pca", "umap"):
                    try:
                        document = cell_state_document(
                            container, run_id, kind, "", embedding, space, _prepared_data=data
                        )
                    except CellStateUnavailable as exc:
                        if space == "expression":
                            raise
                        skipped[space] = str(exc)
                        break
                    key = f"{space}_{embedding}"
                    atomic_write_json(partial / f"{key}.json", document)
                    (partial / f"{key}.svg").write_bytes(render_cell_state(document, "svg"))
                    figures[key] = {
                        "kind": kind, "feature": document["feature"]["id"],
                        "document_feature": document["feature"],
                    }
            _save_data(partial / "plot_data.npz", data)
            if frozen_inputs(container, run_id)["fingerprint"] != inputs["fingerprint"]:
                raise CellStateUnavailable("Frozen inputs changed during figure preparation")
            manifest = {
                "schema_version": VERSION, "run_id": run_id,
                "source_manifest_sha256": inputs["manifest_sha256"],
                "figures": figures, "unavailable": skipped,
                "outputs": {p.name: file_sha256(p) for p in partial.iterdir()},
            }
            atomic_write_json(partial / "prepared.json", manifest)
            partial.rename(final)
        except Exception:
            # Keep failure evidence outside the completed bundle; never publish incomplete figures.
            atomic_write_json(partial / "failure.json", {"status": "failed"})
            raise
    path = final / "prepared.json"
    container.store.register_artifact(
        run_id, ARTIFACT_KIND, f"{run_id}/cell_state/prepared.json",
        file_sha256(path), path.stat().st_size, "application/json",
    )
    return manifest
