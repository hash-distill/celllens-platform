"""Scientific exchange packages must preserve the frozen population and units."""

import hashlib
import importlib.util
import io
import json
import zipfile
from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.tests.test_cell_state import fixture_container
from backend.tests.test_task_trace import build_document

ad = pytest.importorskip("anndata")


def seal(container, root, registered):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["outputs"] = {
        p.name: {"sha256": file_sha256(p)}
        for p in root.iterdir()
        if p.is_file() and p.name != "manifest.json"
    }
    atomic_write_json(root / "manifest.json", manifest)
    registered["run_cells"][0].sha256 = file_sha256(root / "manifest.json")


def bundle_fixture(tmp_path, *, hvg=False):
    container, root, registered = fixture_container(tmp_path)
    final = tmp_path / "data/derived/runs/run_cells"
    final.parent.mkdir(parents=True)
    root.rename(final)
    root = final
    container.settings.derived_root = final.parent
    record = container.store.get("run_cells")
    record.status = "completed"
    container.store.get = lambda _: record
    control = ad.read_h5ad(tmp_path / "control.h5ad")
    predicted = ad.read_h5ad(root / "predicted.h5ad")
    control.obs["gem_group"] = ["b1", "b1", "b2", "b2"]
    predicted.obs["gem_group"] = ["b1", "b2", "b2"]
    control.obs["credentials"] = "secret"
    if hvg:
        control.obsm["X_hvg"] = control.X.copy()
        predicted.obsm["X_hvg"] = predicted.X.copy()
        control.X[:] = 999
        predicted.X[:] = 999
    control.write_h5ad(tmp_path / "control.h5ad")
    predicted.write_h5ad(root / "predicted.h5ad")
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["assets"]["control_sha256"] = file_sha256(tmp_path / "control.h5ad")
    if hvg:
        manifest["assets"]["expression_key"] = "X_hvg"
    atomic_write_json(root / "manifest.json", manifest)
    identity = json.loads((root / "gene_identity.json").read_text())
    for source in identity["sources"].values():
        for i, gene in enumerate(source["columns"]):
            gene.update(hgnc_id=f"HGNC:{i + 1}", approved_symbol=gene["analysis_symbol"])
    atomic_write_json(root / "gene_identity.json", identity)
    trace = build_document()
    trace["run_id"] = "run_cells"
    atomic_write_json(root / "task_trace.json", trace)
    atomic_write_json(root / "summary.json", {"run_id": "run_cells", "status": "completed"})
    pd.DataFrame(
        {"rxn_a": [1, 2, 3, 4, 5, 6], "source": ["control"] * 4 + ["predicted"] * 2},
        index=["c0-0", "c1-0", "c2-0", "c3-0", "p0-1", "p2-1"],
    ).to_csv(root / "reaction_scores.csv")
    (root / "command.log").write_text("TOKEN=secret", encoding="utf-8")
    seal(container, root, registered)
    return container, root, registered


def build(container, package, **kwargs):
    assert importlib.util.find_spec("backend.app.services.export_bundle") is not None, (
        "missing exchange-package service"
    )
    from backend.app.services import export_bundle

    assert callable(getattr(export_bundle, "build_export_bundle", None)), "missing exchange-package builder"
    payload, filename = export_bundle.build_export_bundle(container, "run_cells", package, **kwargs)
    assert filename.endswith(".zip")
    stream = zipfile.ZipFile(io.BytesIO(payload))
    assert stream.testzip() is None
    assert len(stream.namelist()) == len(set(stream.namelist()))
    manifest = json.loads(stream.read("manifest.json"))
    for name, digest in manifest["payload_sha256"].items():
        assert hashlib.sha256(stream.read(name)).hexdigest() == digest
    assert set(manifest["payload_sha256"]) == set(stream.namelist()) - {"manifest.json"}
    return stream, manifest


def test_analysis_is_whitelisted_hashed_readonly_zip(tmp_path):
    container, root, _ = bundle_fixture(tmp_path)
    before = {p: file_sha256(p) for p in tmp_path.rglob("*") if p.is_file()}
    archive, manifest = build(container, "analysis")
    assert archive.read("original/gene_deltas.csv") == (root / "gene_deltas.csv").read_bytes()
    assert archive.read("original/task_trace.json") == (root / "task_trace.json").read_bytes()
    assert not any("command" in n or "credential" in n or "predicted.h5ad" in n for n in archive.namelist())
    assert manifest["source_manifest_sha256"] == file_sha256(root / "manifest.json")
    assert manifest["units"]["expression"] == "log1p_cp10k"
    assert manifest["gene_identity"]["hgnc_resolved_count"] == 3
    assert manifest["populations"]["original"]["counts"] == {"control": 4, "predicted": 2}
    assert any(x["item"] == "comparison" for x in manifest["optional_omissions"])
    assert "实测" in archive.read("README.md").decode("utf-8")
    assert before == {p: file_sha256(p) for p in tmp_path.rglob("*") if p.is_file()}


def test_table_metadata_supports_default_and_configured_api_prefix(tmp_path):
    from backend.app.services.export_tables import table_metadata

    container, _, _ = bundle_fixture(tmp_path)
    assert table_metadata(container, "run_cells")["metadata_url"] == (
        "/api/v1/research/results/prediction/run_cells/export"
    )
    container.settings.api_prefix = "/custom/v2"
    assert table_metadata(container, "run_cells")["metadata_url"] == (
        "/custom/v2/research/results/prediction/run_cells/export"
    )


def test_single_cell_exports_real_hvg_target_cells_batch_and_identity(tmp_path, monkeypatch):
    container, _, _ = bundle_fixture(tmp_path, hvg=True)
    from backend.app.services import cell_state

    monkeypatch.setattr(cell_state, "reference_pca", lambda *a, **k: pytest.fail("GET fitted PCA"))
    monkeypatch.setattr(cell_state, "joint_umap", lambda *a, **k: pytest.fail("GET fitted UMAP"))
    archive, manifest = build(container, "single-cell")
    exported = tmp_path / "readback.h5ad"
    exported.write_bytes(archive.read("original/expression_log1p_cp10k.h5ad"))
    matrix = ad.read_h5ad(exported)
    assert matrix.shape == (6, 3) and matrix.raw is None and not matrix.layers
    assert matrix.obs["celllens_source"].astype(str).tolist() == ["control"] * 4 + ["predicted"] * 2
    assert matrix.obs["source_cell_id"].tolist() == ["c0", "c1", "c2", "c3", "p0", "p2"]
    assert matrix.obs["gem_group"].tolist() == ["b1", "b1", "b2", "b2", "b1", "b2"]
    assert "credentials" not in matrix.obs
    np.testing.assert_array_equal(matrix.X[-2:], [[2, 2, 4], [3, 4, 6]])
    assert matrix.var["hgnc_id"].tolist() == ["HGNC:1", "HGNC:2", "HGNC:3"]
    assert matrix.uns["celllens_export"]["expression_scale"] == "log1p_cp10k"
    assert manifest["populations"]["original"]["expression_slots"] == {
        "control": "obsm[X_hvg]",
        "predicted": "obsm[X_hvg]",
    }
    assert "original/reaction_scores.csv" in archive.namelist()
    assert set(matrix.obsm) == set()


def test_network_closes_all_endpoints_preserves_gpr_and_missing_scores(tmp_path):
    container, _, _ = bundle_fixture(tmp_path)
    archive, manifest = build(container, "network", task_id="task_a")
    nodes = pd.read_csv(archive.open("network/nodes.csv"))
    edges = pd.read_csv(archive.open("network/edges.csv"))
    assert len(nodes) == 5 and len(edges) == 4
    assert set(edges.source) | set(edges.target) <= set(nodes.id)
    assert nodes.loc[nodes.id == "reaction:rxn_a", "gene_rule"].item() == "GENE1 and MISSING"
    assert nodes.loc[nodes.id == "gene:MISSING", "predicted_delta"].isna().all()
    assert set(edges.interaction) == {"knowledge_association"}
    trace = json.loads(archive.read("network/task_trace.json"))
    assert trace["reactions"]["rxn_a"]["gene_rule"] == "GENE1 and MISSING"
    assert manifest["selection"]["task_id"] == "task_a"
    assert manifest["selection"]["scope"] == "task_subnetwork"


def test_ranking_has_every_signed_delta_and_exact_panel_background(tmp_path):
    container, root, _ = bundle_fixture(tmp_path)
    archive, manifest = build(container, "ranking")
    ranks = pd.read_csv(
        archive.open("ranking/predicted_delta.rnk"), sep="\t", header=None, names=["gene", "score"]
    )
    expected = pd.read_csv(root / "gene_deltas.csv", index_col=0).predicted_delta
    assert ranks.gene.is_unique and set(ranks.gene) == set(expected.index)
    np.testing.assert_allclose(ranks.set_index("gene").score.reindex(expected.index), expected)
    assert ranks.score.is_monotonic_decreasing
    assert archive.read("ranking/panel_background.txt").decode().splitlines() == expected.index.tolist()
    assert manifest["ranking"]["score"] == "signed predicted_delta"
    assert manifest["ranking"]["is_log2_fold_change"] is False
    assert manifest["ranking"]["is_p_value"] is False


@pytest.mark.parametrize("mutation", ["output", "input", "manifest", "status", "synthetic"])
def test_changed_or_noncompleted_sources_are_rejected(tmp_path, mutation):
    container, root, registered = bundle_fixture(tmp_path)
    if mutation == "output":
        (root / "reaction_scores.csv").write_text("tampered")
    elif mutation == "input":
        (tmp_path / "control.h5ad").write_bytes(b"tampered")
    elif mutation == "manifest":
        (root / "manifest.json").write_text("{}")
    elif mutation == "status":
        container.store.get("run_cells").status = "state_running"
    else:
        manifest = json.loads((root / "manifest.json").read_text())
        manifest["source_type"] = "synthetic_precomputed"
        atomic_write_json(root / "manifest.json", manifest)
        registered["run_cells"][0].sha256 = file_sha256(root / "manifest.json")
    from backend.app.services import export_bundle

    with pytest.raises(ValueError):
        export_bundle.build_export_bundle(container, "run_cells", "analysis")


def comparison_fixture(container, root):
    comparison = container.settings.project_root / "data/derived/comparisons/run_cells"
    comparison.mkdir(parents=True)
    report = {
        "run_id": "run_cells",
        "status": "available",
        "cell_line": "K562",
        "perturbation": "MYC",
        "held_out_validation": False,
        "training_exclusion_verified": False,
        "parameters": {"population_counts": {"control": 2, "predicted": 2, "observed": 2}},
        "population_matching": {"status": "common_batches_only", "common_batches": ["b1"]},
        "genes": [{"id": "MYC", "control": 1.5, "predicted": 2.5, "observed": 1.6}],
        "tasks": [],
        "binding": {"prediction_manifest_sha256": file_sha256(root / "manifest.json")},
    }
    atomic_write_json(comparison / "comparison.json", report)
    pd.DataFrame({"control": [1.5], "predicted": [2.5], "observed": [1.6]}, index=["MYC"]).to_csv(
        comparison / "gene_deltas.csv"
    )
    pd.DataFrame({"predicted_pvals_adj": [0.02], "observed_pvals_adj": [0.3]}, index=["MYC"]).to_csv(
        comparison / "differential_expression.csv"
    )
    atomic_write_json(
        comparison / "manifest.json",
        {
            "run_id": "run_cells",
            "source_manifest_sha256": file_sha256(root / "manifest.json"),
            "inputs": {},
            "outputs": {p.name: file_sha256(p) for p in comparison.iterdir()},
        },
    )
    return comparison


def test_comparison_stays_separate_and_exports_de_gene_statistics(tmp_path):
    container, root, _ = bundle_fixture(tmp_path)
    comparison = comparison_fixture(container, root)
    archive, manifest = build(container, "analysis")
    assert archive.read("comparison/gene_deltas.csv") == (comparison / "gene_deltas.csv").read_bytes()
    assert "comparison/differential_expression.csv" in archive.namelist()
    assert manifest["populations"]["comparison"]["counts"]["control"] == 2
    assert manifest["populations"]["original"]["counts"]["control"] == 4
    assert manifest["populations"]["comparison"]["held_out_validation"] is False


def test_comparison_hash_mismatch_is_not_silently_exported(tmp_path):
    container, root, _ = bundle_fixture(tmp_path)
    comparison = comparison_fixture(container, root)
    (comparison / "differential_expression.csv").write_text("tampered")
    from backend.app.services import export_bundle

    with pytest.raises(ValueError, match="hash"):
        export_bundle.build_export_bundle(container, "run_cells", "analysis")


def test_output_manifest_cannot_export_paths_or_command_logs(tmp_path):
    container, root, registered = bundle_fixture(tmp_path)
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["outputs"]["../../credentials.json"] = {"sha256": "a" * 64}
    atomic_write_json(root / "manifest.json", manifest)
    registered["run_cells"][0].sha256 = file_sha256(root / "manifest.json")
    archive, _ = build(container, "analysis")
    assert not any(".." in n or "credential" in n or "command" in n for n in archive.namelist())


def test_network_rejects_dangling_references_instead_of_silent_filtering(tmp_path):
    container, root, registered = bundle_fixture(tmp_path)
    trace = json.loads((root / "task_trace.json").read_text())
    del trace["genes"]["MISSING"]
    atomic_write_json(root / "task_trace.json", trace)
    seal(container, root, registered)
    from backend.app.services import export_bundle

    with pytest.raises(ValueError, match="reference|missing|closure"):
        export_bundle.build_export_bundle(container, "run_cells", "network")


def prepared_fixture(container, root, registered):
    prepared = root / "cell_state"
    prepared.mkdir()
    ids = ["c0-0", "c1-0", "c2-0", "c3-0", "p0-1", "p2-1"]
    sources = ["control"] * 4 + ["predicted"] * 2
    metadata = {
        "genes": ["MYC", "ENO1", "ENO2"],
        "gene_order": ["MYC", "ENO1", "ENO2"],
        "task_order": ["T"],
        "ids": ids,
        "sources": sources,
        "expression_slots": {"control": "X", "predicted": "X"},
        "task_columns": ["T"],
        "projections": {"expression": {"variance": [0.6, 0.3], "umap_parameters": {"random_state": 42}}},
    }
    np.savez_compressed(
        prepared / "plot_data.npz",
        metadata=np.asarray(json.dumps(metadata)),
        expression_control=np.array([[0, 1, 3], [2, 4, 1], [3, 2, 6], [1, 4, 5]]),
        expression_predicted=np.array([[2, 2, 4], [3, 4, 6]]),
        task_scores=np.arange(6).reshape(6, 1),
        expression_pca_control=np.arange(8).reshape(4, 2),
        expression_pca_predicted=np.arange(4).reshape(2, 2) + 20,
        expression_umap_control=np.arange(8).reshape(4, 2) + 40,
        expression_umap_predicted=np.arange(4).reshape(2, 2) + 60,
    )
    (prepared / "expression_pca.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    manifest = {
        "schema_version": 1,
        "run_id": "run_cells",
        "source_manifest_sha256": file_sha256(root / "manifest.json"),
        "figures": {},
        "unavailable": {},
        "outputs": {p.name: file_sha256(p) for p in prepared.iterdir()},
    }
    atomic_write_json(prepared / "prepared.json", manifest)
    registered["run_cells"].append(
        SimpleNamespace(
            kind="cell_state_preparation",
            relative_path="run_cells/cell_state/prepared.json",
            sha256=file_sha256(prepared / "prepared.json"),
        )
    )
    return prepared


def test_single_cell_only_reuses_existing_frozen_coordinates_and_records_metadata(tmp_path):
    container, root, registered = bundle_fixture(tmp_path)
    prepared_fixture(container, root, registered)
    archive, manifest = build(container, "single-cell")
    exported = tmp_path / "readback.h5ad"
    exported.write_bytes(archive.read("original/expression_log1p_cp10k.h5ad"))
    matrix = ad.read_h5ad(exported)
    np.testing.assert_array_equal(matrix.obsm["X_expression_pca"][-2:], [[20, 21], [22, 23]])
    np.testing.assert_array_equal(matrix.obsm["X_expression_umap"][-2:], [[60, 61], [62, 63]])
    assert "original/figures/expression_pca.svg" in archive.namelist()
    assert (
        json.loads(matrix.uns["celllens_export"]["embedding_metadata_json"])["expression"]["umap_parameters"][
            "random_state"
        ]
        == 42
    )
    assert (
        json.loads(archive.read("original/table_metadata.json"))["selection_id"]
        == manifest["populations"]["original"]["selection_id"]
    )


def test_changed_prepared_figure_is_rejected(tmp_path):
    container, root, registered = bundle_fixture(tmp_path)
    prepared = prepared_fixture(container, root, registered)
    (prepared / "expression_pca.svg").write_text("tampered")
    from backend.app.services.export_bundle import build_export_bundle

    with pytest.raises(ValueError, match="hash|changed"):
        build_export_bundle(container, "run_cells", "single-cell")


def test_network_selection_changes_tables_but_keeps_original_trace(tmp_path):
    container, root, registered = bundle_fixture(tmp_path)
    trace = json.loads((root / "task_trace.json").read_text())
    trace["tasks"]["task_other"] = {"id": "task_other", "reaction_ids": ["rxn_other"]}
    trace["reactions"]["rxn_other"] = {"id": "rxn_other", "gene_ids": ["OTHER"], "gene_rule": "OTHER"}
    trace["genes"]["OTHER"] = {"id": "OTHER"}
    atomic_write_json(root / "task_trace.json", trace)
    seal(container, root, registered)
    archive, manifest = build(container, "network", task_id="task_a")
    assert manifest["selection"]["source_counts"]["tasks"] == 2
    assert manifest["selection"]["export_counts"]["tasks"] == 1
    nodes = pd.read_csv(archive.open("network/nodes.csv"))
    assert not any(nodes.entity_id == "OTHER")
    assert "task_other" in json.loads(archive.read("network/task_trace.json"))["tasks"]


def test_original_observed_population_is_target_filtered_even_without_task_table(tmp_path):
    container, root, registered = bundle_fixture(tmp_path)
    observed = ad.AnnData(np.array([[1, 2, 3], [99, 99, 99], [3, 4, 5]], dtype=float))
    observed.var_names = ["MYC", "ENO1", "ENO2"]
    observed.obs_names = ["o0", "o_control", "o2"]
    observed.obs["gene"] = ["MYC", "control", "MYC"]
    observed.obs["gem_group"] = ["b1", "b1", "b2"]
    observed_path = tmp_path / "observed.h5ad"
    observed.write_h5ad(observed_path)
    container.registry.datasets[0]["observed_path"] = "observed.h5ad"
    contract = json.loads((root / "expression_contract.json").read_text())
    contract["source_scales"]["observed"] = "log1p_cp10k"
    atomic_write_json(root / "expression_contract.json", contract)
    identity = json.loads((root / "gene_identity.json").read_text())
    identity["sources"]["observed"] = identity["sources"]["control"]
    atomic_write_json(root / "gene_identity.json", identity)
    genes = pd.read_csv(root / "gene_deltas.csv", index_col=0)
    genes["observed"] = [2, 3, 4]
    genes["observed_delta"] = genes.observed - genes.control
    genes.to_csv(root / "gene_deltas.csv")
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["assets"]["observed_sha256"] = file_sha256(observed_path)
    atomic_write_json(root / "manifest.json", manifest)
    for name in ("metabolic_task_scores.csv", "reaction_scores.csv"):
        (root / name).unlink()
    seal(container, root, registered)
    archive, manifest = build(container, "single-cell")
    assert manifest["populations"]["original"]["counts"] == {"control": 4, "predicted": 2, "observed": 2}
    target = tmp_path / "observed_readback.h5ad"
    target.write_bytes(archive.read("original/expression_log1p_cp10k.h5ad"))
    matrix = ad.read_h5ad(target)
    selected = matrix[matrix.obs.celllens_source.astype(str) == "observed"]
    np.testing.assert_array_equal(selected.X, [[1, 2, 3], [3, 4, 5]])
    assert selected.obs.source_cell_id.tolist() == ["o0", "o2"]


def pdf_fixture(tmp_path):
    container, root, registered = bundle_fixture(tmp_path)
    record = container.store.get("run_cells")
    record.run_id = "run_cells"
    record.created_at = datetime(2026, 10, 22)
    registered["run_cells"][0].kind = "manifest"
    atomic_write_json(
        root / "summary.json",
        {
            "run_id": "run_cells",
            "cell_line": "K562",
            "perturbation": "MYC",
            "status": "completed",
            "stage_progress": 100,
        },
    )
    genes = pd.read_csv(root / "gene_deltas.csv", index_col=0)
    genes.index.name = "gene"
    genes.to_csv(root / "gene_deltas.csv")
    seal(container, root, registered)
    return container, root


def test_analysis_includes_revised_pdf_from_verified_sources(tmp_path):
    from pypdf import PdfReader

    container, _ = pdf_fixture(tmp_path)
    archive, manifest = build(container, "analysis")
    content = archive.read("report.pdf")
    assert content.startswith(b"%PDF-")
    assert "CellLens" in "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)
    assert not any(item["item"] == "pdf_report" for item in manifest["optional_omissions"])


def test_optional_pdf_dependency_failure_records_omission(tmp_path, monkeypatch):
    from backend.app.services import pdf_report

    container, _ = pdf_fixture(tmp_path)

    def unavailable(*args):
        raise ImportError("PDF dependencies unavailable")

    monkeypatch.setattr(pdf_report, "build_report_pdf", unavailable)
    archive, manifest = build(container, "analysis")
    assert "report.pdf" not in archive.namelist()
    assert any(
        item["item"] == "pdf_report" and "PDF" in item["reason"] for item in manifest["optional_omissions"]
    )


def test_optional_pdf_never_swallows_frozen_hash_failure(tmp_path, monkeypatch):
    from backend.app.services import pdf_report
    from backend.app.services.cell_state import CellStateUnavailable
    from backend.app.services.export_bundle import build_export_bundle

    container, _ = pdf_fixture(tmp_path)

    def changed(*args):
        raise CellStateUnavailable("Frozen PDF source hash changed")

    monkeypatch.setattr(pdf_report, "build_report_pdf", changed)
    with pytest.raises(ValueError, match="hash"):
        build_export_bundle(container, "run_cells", "analysis")
