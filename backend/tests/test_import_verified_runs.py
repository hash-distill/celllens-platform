import json
from types import SimpleNamespace

import pytest

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.core.storage import RunStore
from backend.app.schemas import RunStatus
from scripts.import_verified_runs import restore, validate


def import_fixture(tmp_path):
    source_project = tmp_path / "original"
    identifier = "run_verified_history"
    source = source_project / "data/derived/runs" / identifier
    source.mkdir(parents=True)
    request = {"cell_line": "K562", "perturbation": "ALDOA", "mode": "online", "n_cells": 64, "seed": 42}
    atomic_write_json(
        source / "summary.json",
        {"run_id": identifier, "status": "completed", "cell_line": "K562", "perturbation": "ALDOA"},
    )
    atomic_write_json(
        source / "expression_contract.json",
        {
            "run_id": identifier,
            "analysis_version": "expression-cp10k-v2",
            "gene_units": "mean(log1p(CP10K))",
            "predicted_values_are_measured_counts": False,
            "source_scales": {"control": "log1p_cp10k", "predicted": "log1p_cp10k", "observed": None},
        },
    )
    (source / "predicted.h5ad").write_bytes(b"opaque frozen test prediction payload")
    (source / "gene_deltas.csv").write_text("gene,control,predicted,predicted_delta\nALDOA,1,2,1\n")
    manifest = {
        "request": request,
        "assets": {
            "model_id": "frozen-state",
            "dataset_id": "frozen-data",
            "checkpoint_sha256": "a" * 64,
            "control_sha256": "b" * 64,
            "gene_list_sha256": "c" * 64,
        },
        "outputs": {p.name: {"sha256": file_sha256(p)} for p in source.iterdir()},
    }
    atomic_write_json(source / "manifest.json", manifest)
    target = tmp_path / "restored"
    target.mkdir()
    settings = SimpleNamespace(project_root=target, derived_root=target / "data/derived/runs")
    store = RunStore(f"sqlite:///{(target / 'test.sqlite').as_posix()}", create_schema=True)
    return SimpleNamespace(settings=settings, store=store), source_project, identifier, source


def rehash(source, name):
    path = source / "manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["outputs"][name]["sha256"] = file_sha256(source / name)
    atomic_write_json(path, manifest)


def test_import_preserves_source_and_atomically_registers_only_completed_history(tmp_path, monkeypatch):
    container, project, identifier, source = import_fixture(tmp_path)
    before = {p.name: file_sha256(p) for p in source.iterdir()}

    def forbidden(*args, **kwargs):
        pytest.fail("Restoring history must not create a queued row or execute a model")

    monkeypatch.setattr(container.store, "create", forbidden)
    result = restore(container, project, identifier)
    assert result["new_inference"] is False
    assert container.store.get(identifier).status == RunStatus.COMPLETED
    assert len(container.store.artifacts(identifier)) == len(before)
    assert container.store.list_recoverable_run_ids() == []
    assert [event.to_status for event in container.store.events(identifier)] == ["completed"]
    assert before == {p.name: file_sha256(p) for p in source.iterdir()}
    destination = container.settings.derived_root / identifier
    assert before == {p.name: file_sha256(p) for p in destination.iterdir()}
    with pytest.raises(ValueError, match="Destination exists"):
        restore(container, project, identifier)
    assert before == {p.name: file_sha256(p) for p in source.iterdir()}


@pytest.mark.parametrize("change", ["failed", "synthetic", "replay", "unknown_scale", "wrong_background"])
def test_import_rejects_noncompleted_synthetic_and_unverified_science(tmp_path, change):
    _, _, identifier, source = import_fixture(tmp_path)
    if change == "replay":
        path = source / "manifest.json"
        manifest = json.loads(path.read_bytes())
        manifest["source_type"] = "synthetic_precomputed"
        atomic_write_json(path, manifest)
    elif change == "unknown_scale":
        path = source / "expression_contract.json"
        contract = json.loads(path.read_bytes())
        contract["gene_units"] = "log2FC"
        atomic_write_json(path, contract)
        rehash(source, path.name)
    else:
        path = source / "summary.json"
        summary = json.loads(path.read_bytes())
        summary.update(
            {
                "failed": {"status": "failed"},
                "synthetic": {"result_kind": "synthetic_demo"},
                "wrong_background": {"cell_line": "RPE1"},
            }[change]
        )
        atomic_write_json(path, summary)
        rehash(source, path.name)
    with pytest.raises(ValueError):
        validate(source, identifier)


def test_import_rejects_tampering_and_path_escape_without_destination_or_database_rows(tmp_path):
    container, project, identifier, source = import_fixture(tmp_path)
    (source / "predicted.h5ad").write_bytes(b"changed")
    with pytest.raises(ValueError, match="integrity"):
        restore(container, project, identifier)
    assert not (container.settings.derived_root / identifier).exists()
    with pytest.raises(KeyError):
        container.store.get(identifier)
    rehash(source, "predicted.h5ad")
    outside = source.parent / "outside.json"
    outside.write_text("private fixture")
    manifest = json.loads((source / "manifest.json").read_bytes())
    manifest["outputs"]["../outside.json"] = {"sha256": file_sha256(outside)}
    atomic_write_json(source / "manifest.json", manifest)
    with pytest.raises(ValueError, match="escapes"):
        restore(container, project, identifier)


def test_import_rechecks_source_changes_during_copy(tmp_path, monkeypatch):
    from scripts import import_verified_runs

    container, project, identifier, source = import_fixture(tmp_path)
    original = import_verified_runs.shutil.copy2

    def changed_copy(file, target):
        original(file, target)
        if file.name == "manifest.json":
            (source / "predicted.h5ad").write_bytes(b"changed while copying")

    monkeypatch.setattr(import_verified_runs.shutil, "copy2", changed_copy)
    with pytest.raises(ValueError, match="differs"):
        restore(container, project, identifier)
    assert not (container.settings.derived_root / identifier).exists()
    with pytest.raises(KeyError):
        container.store.get(identifier)


def test_import_prepared_bundle_must_match_source_and_confine_all_files(tmp_path):
    _, _, identifier, source = import_fixture(tmp_path)
    bundle = source / "cell_state"
    bundle.mkdir()
    (bundle / "plot_data.npz").write_bytes(b"plot fixture")
    prepared = {
        "schema_version": 1,
        "run_id": identifier,
        "figures": {},
        "source_manifest_sha256": "0" * 64,
        "outputs": {"plot_data.npz": file_sha256(bundle / "plot_data.npz")},
    }
    atomic_write_json(bundle / "prepared.json", prepared)
    with pytest.raises(ValueError, match="provenance"):
        validate(source, identifier)
    prepared["source_manifest_sha256"] = file_sha256(source / "manifest.json")
    prepared["outputs"]["../summary.json"] = file_sha256(source / "summary.json")
    atomic_write_json(bundle / "prepared.json", prepared)
    with pytest.raises(ValueError, match="escapes"):
        validate(source, identifier)
