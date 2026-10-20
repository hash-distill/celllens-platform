import json
from types import SimpleNamespace

import pytest

from backend.app.core.run_manifest import file_sha256
from backend.app.services import cell_state
from backend.tests.test_cell_state import fixture_container


def prepared_container(tmp_path):
    container, root, registered = fixture_container(tmp_path)

    def register(run_id, kind, relative_path, sha256, size_bytes, mime_type):
        registered[run_id].append(
            SimpleNamespace(kind=kind, relative_path=relative_path, sha256=sha256)
        )

    container.store.register_artifact = register
    return container, root


def test_prepared_plot_survives_process_cache_loss_without_reconstruction_or_embedding(tmp_path, monkeypatch):
    from backend.app.services.cell_state_preparation import prepare_cell_state_artifacts, prepared_figure

    container, root = prepared_container(tmp_path)
    original = {p.name: file_sha256(p) for p in root.iterdir()}
    prepare_cell_state_artifacts(container, "run_cells")
    before = cell_state.cell_state_document(container, "run_cells", "gene", "MYC", "umap")
    image = prepared_figure(container, before)
    assert image is not None and b"UMAP 1" in image
    cell_state._CACHE.clear()

    def forbidden(*args, **kwargs):
        pytest.fail("Reading a prepared result must not reconstruct or fit PCA/UMAP")

    monkeypatch.setattr(cell_state, "_reconstruct", forbidden)
    monkeypatch.setattr(cell_state, "joint_umap", forbidden)
    monkeypatch.setattr(cell_state, "reference_pca", forbidden)
    after = cell_state.cell_state_document(container, "run_cells", "gene", "MYC", "umap")
    assert before == after
    assert prepared_figure(container, after) == image
    first = cell_state.cell_state_document(container, "run_cells", "task", "T", "umap", "metabolic")
    other = cell_state.cell_state_document(container, "run_cells", "task", "U", "umap", "metabolic")
    assert [(p["x"], p["y"]) for p in first["points"]] == [
        (p["x"], p["y"]) for p in other["points"]
    ]
    assert all(file_sha256(root / name) == sha for name, sha in original.items())


def test_prepared_artifacts_and_original_inputs_are_checked_even_after_cache_hit(tmp_path):
    from backend.app.services.cell_state_preparation import prepare_cell_state_artifacts

    container, root = prepared_container(tmp_path)
    prepare_cell_state_artifacts(container, "run_cells")
    cell_state.cell_state_document(container, "run_cells", "gene", "MYC", "umap")
    with (root / "cell_state" / "plot_data.npz").open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(cell_state.CellStateUnavailable, match="changed"):
        cell_state.cell_state_document(container, "run_cells", "gene", "MYC", "umap")


def test_preparation_is_idempotent_and_failures_do_not_register_partial_results(tmp_path, monkeypatch):
    from backend.app.services.cell_state_preparation import prepare_cell_state_artifacts

    container, root = prepared_container(tmp_path)

    def failed(*args, **kwargs):
        raise RuntimeError("UMAP preparation failed")

    monkeypatch.setattr(cell_state, "joint_umap", failed)
    with pytest.raises(RuntimeError, match="UMAP preparation failed"):
        prepare_cell_state_artifacts(container, "run_cells")
    assert not (root / "cell_state").exists()
    assert len(container.store.artifacts("run_cells")) == 1


def test_prepared_manifest_binds_original_frozen_run(tmp_path):
    from backend.app.services.cell_state_preparation import prepare_cell_state_artifacts

    container, root = prepared_container(tmp_path)
    prepare_cell_state_artifacts(container, "run_cells")
    manifest = json.loads((root / "cell_state" / "prepared.json").read_text())
    assert manifest["source_manifest_sha256"] == file_sha256(root / "manifest.json")
    assert len(manifest["figures"]) == 4
    assert all((root / "cell_state" / f"{key}.svg").is_file() for key in manifest["figures"])
    original = file_sha256(root / "cell_state" / "prepared.json")
    prepare_cell_state_artifacts(container, "run_cells")
    assert file_sha256(root / "cell_state" / "prepared.json") == original
    assert len(container.store.artifacts("run_cells")) == 2


def test_expression_figures_can_finish_when_metabolic_analysis_is_unavailable(tmp_path):
    from backend.app.core.run_manifest import atomic_write_json
    from backend.app.services.cell_state_preparation import prepare_cell_state_artifacts

    container, root = prepared_container(tmp_path)
    manifest = json.loads((root / "manifest.json").read_text())
    for name in ("metabolic_task_scores.csv", "gene_identity.json"):
        del manifest["outputs"][name]
        (root / name).unlink()
    atomic_write_json(root / "manifest.json", manifest)
    container.store.artifacts("run_cells")[0].sha256 = file_sha256(root / "manifest.json")
    prepared = prepare_cell_state_artifacts(container, "run_cells")
    assert set(prepared["figures"]) == {"expression_pca", "expression_umap"}
    cell_state._CACHE.clear()
    assert cell_state.cell_state_document(container, "run_cells", "gene", "MYC", "umap")["points"]
    with pytest.raises(cell_state.CellStateUnavailable):
        cell_state.cell_state_document(container, "run_cells", "task", "T", "umap", "metabolic")


def test_svg_api_returns_prepared_default_without_calling_renderer(tmp_path, monkeypatch):
    from backend.app.api import runs
    from backend.app.services.cell_state_preparation import prepare_cell_state_artifacts

    container, _ = prepared_container(tmp_path)
    prepare_cell_state_artifacts(container, "run_cells")
    document = cell_state.cell_state_document(container, "run_cells", "gene", "MYC", "umap")
    monkeypatch.setattr(runs, "_cell_state", lambda *args: document)

    def forbidden(*args):
        pytest.fail("Default SVG should already have been rendered by the worker")

    monkeypatch.setattr(runs, "render_cell_state", forbidden)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(container=container)))
    response = runs.get_cell_state_figure(
        "run_cells", request, "gene", "MYC", "svg", "umap", "expression"
    )
    assert b"UMAP 1" in response.body


def test_staged_preparation_survives_atomic_publication(tmp_path):
    from backend.app.services.cell_state_preparation import prepare_cell_state_artifacts

    container, root = prepared_container(tmp_path)
    partial = root.with_name("run_cells.attempt-1.partial")
    root.rename(partial)
    prepare_cell_state_artifacts(container, "run_cells", source_root=partial)
    assert not root.exists()
    assert len(container.store.artifacts("run_cells")) == 1  # No premature DB publication.
    partial.rename(root)
    path = root / "cell_state" / "prepared.json"
    container.store.register_artifact(
        "run_cells", "cell_state_preparation", "run_cells/cell_state/prepared.json",
        file_sha256(path), path.stat().st_size, "application/json",
    )
    cell_state._CACHE.clear()
    document = cell_state.cell_state_document(container, "run_cells", "gene", "MYC", "umap")
    assert document["provenance"]["manifest_sha256"] == file_sha256(root / "manifest.json")


def test_preparation_does_not_depend_on_request_lru_residency(tmp_path, monkeypatch):
    from backend.app.services import cell_state_figure
    from backend.app.services.cell_state_preparation import prepare_cell_state_artifacts

    container, _ = prepared_container(tmp_path)
    render = cell_state_figure.render_cell_state

    def render_and_evict(*args):
        cell_state._CACHE.clear()
        return render(*args)

    monkeypatch.setattr(cell_state_figure, "render_cell_state", render_and_evict)
    assert len(prepare_cell_state_artifacts(container, "run_cells")["figures"]) == 4
