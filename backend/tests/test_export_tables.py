"""Exports must retain population/units and reject changed frozen sources."""

import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.schemas import CreateRunRequest, RunStatus
from backend.tests.test_api_runs import _settings, _write_registry


def export_app(tmp_path):
    from backend.app.main import create_app

    _write_registry(tmp_path)
    app = create_app(_settings(tmp_path, worker_enabled=False))
    store = app.state.container.store
    store.create("run_export", CreateRunRequest(cell_line="K562", perturbation="MYC", n_cells=64))
    store.transition("run_export", RunStatus.COMPLETED, 100)
    root = app.state.container.settings.derived_root / "run_export"
    root.mkdir(parents=True)
    (root / "gene_deltas.csv").write_text(
        "gene,control,predicted,predicted_delta\nZERO,1,1,0\nCHANGE,1,2,1\n", encoding="utf-8"
    )
    (root / "metabolic_task_scores.csv").write_text(
        ",task_a,source\nc1,1,control\nc2,3,control\np1,4,predicted\n", encoding="utf-8"
    )
    (root / "reaction_scores.csv").write_text(
        ",R1,source\nc1,2,control\nc2,4,control\np1,6,predicted\n", encoding="utf-8"
    )
    (root / "metabolic_coverage.csv").write_text(
        "task,gene_fraction,evidence_level,missing_genes\ntask_a,0.5,insufficient,B\n", encoding="utf-8"
    )
    atomic_write_json(
        root / "expression_contract.json",
        {
            "analysis_version": "expression-cp10k-v2",
            "gene_units": "mean(log1p(CP10K))",
            "population_selection": {"selected_prediction_cells": 1},
            "source_scales": {"control": "log1p_cp10k", "predicted": "log1p_cp10k"},
        },
    )
    atomic_write_json(
        root / "summary.json",
        {
            "run_id": "run_export",
            "cell_line": "K562",
            "perturbation": "MYC",
            "warnings": [],
            "coverage": {"database_version": "scCellFie-0.6.2-human-Recon2"},
        },
    )
    atomic_write_json(
        root / "manifest.json",
        {
            "request": store.get("run_export").request.model_dump(mode="json"),
            "assets": {"model_id": "state-test", "dataset_id": "data-test"},
            "outputs": {p.name: {"sha256": file_sha256(p)} for p in root.iterdir()},
        },
    )
    manifest = root / "manifest.json"
    store.register_artifact(
        "run_export",
        "manifest",
        "run_export/manifest.json",
        file_sha256(manifest),
        manifest.stat().st_size,
        "application/json",
    )
    return app, root


def test_gene_csv_is_complete_with_zero_and_bound_population_metadata(tmp_path):
    app, root = export_app(tmp_path)
    before = {p.name: file_sha256(p) for p in root.iterdir()}
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/run_export/export/table?table=genes")
    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert [r["gene"] for r in rows] == ["ZERO", "CHANGE"]
    assert float(rows[0]["predicted_delta"]) == 0
    assert rows[0]["units"] == "mean(log1p(CP10K))"
    assert rows[0]["population"] == "original"
    assert rows[0]["n_control"] == "2" and rows[0]["n_predicted"] == "1"
    assert rows[0]["n_observed"] == "0"
    assert rows[0]["run_id"] == "run_export" and rows[0]["model_id"] == "state-test"
    assert len(rows[0]["manifest_sha256"]) == 64
    assert "original" in response.headers["content-disposition"]
    assert before == {p.name: file_sha256(p) for p in root.iterdir()}


@pytest.mark.parametrize(
    "table,identifier,control,predicted", [("tasks", "task_a", 2, 4), ("reactions", "R1", 3, 6)]
)
def test_metabolic_csv_aggregates_cell_rows_and_keeps_units(tmp_path, table, identifier, control, predicted):
    app, _ = export_app(tmp_path)
    with TestClient(app) as client:
        response = client.get(f"/api/v1/runs/run_export/export/table?table={table}")
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0]["id"] == identifier
    assert float(rows[0]["control"]) == control
    assert float(rows[0]["predicted"]) == predicted
    assert float(rows[0]["predicted_delta"]) == predicted - control
    assert "scCellFie" in rows[0]["units"]
    assert rows[0]["observed"] == ""
    if table == "tasks":
        assert rows[0]["coverage"] == "0.5" and rows[0]["evidence_level"] == "insufficient"


@pytest.mark.parametrize(
    "target", ["gene_deltas.csv", "expression_contract.json", "metabolic_task_scores.csv", "manifest.json"]
)
def test_export_rejects_changed_frozen_table_or_metadata(tmp_path, target):
    app, root = export_app(tmp_path)
    with (root / target).open("a", encoding="utf-8") as f:
        f.write(" ")
    with TestClient(app) as client:
        assert client.get("/api/v1/runs/run_export/export/table?table=genes").status_code == 409


def test_export_rejects_missing_comparison_and_invalid_parameters(tmp_path):
    app, _ = export_app(tmp_path)
    with TestClient(app) as client:
        assert (
            client.get("/api/v1/runs/run_export/export/table?table=genes&population=comparison").status_code
            == 409
        )
        assert client.get("/api/v1/runs/run_export/export/table?table=commands").status_code == 422
        assert client.get("/api/v1/runs/missing/export/table?table=genes").status_code == 404
        assert client.get("/api/v1/runs/run_export/export?package=commands").status_code == 422


def test_figure_names_distinguish_features_and_are_ascii_safe():
    from backend.app.services.export_names import figure_filename

    first = figure_filename("run_export", "expression", "umap", "gene", "ALDOA", "svg")
    second = figure_filename("run_export", "expression", "umap", "gene", "TPI1", "svg")
    third = figure_filename("run_export", "metabolic", "pca", "task", "../任务 / a:b", "json")
    assert first != second and "ALDOA" in first
    assert first.endswith(".svg") and third.endswith(".json")
    assert third.isascii() and "/" not in third and "\\" not in third and ".." not in third


def test_csv_uses_final_frozen_validation_population_without_cell_score_rows(tmp_path, monkeypatch):
    from backend.app.services import export_tables

    app, root = export_app(tmp_path)
    contract_path = root / "expression_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["population_selection"]["selected_prediction_cells"] = 11
    contract["validation_population"] = {"selected_cells": {"control": 7, "predicted": 1, "observed": 2}}
    atomic_write_json(contract_path, contract)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["outputs"].pop("metabolic_task_scores.csv")
    manifest["outputs"][contract_path.name]["sha256"] = file_sha256(contract_path)
    atomic_write_json(root / "manifest.json", manifest)
    digest = file_sha256(root / "manifest.json")
    monkeypatch.setattr(export_tables, "_manifest", lambda *a: (root, manifest, digest))
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/run_export/export/table?table=genes")
    assert response.status_code == 200
    row = next(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert (row["n_control"], row["n_predicted"], row["n_observed"]) == ("7", "1", "2")


@pytest.mark.parametrize("unregistered", [None, "comparison.json", "reaction_scores.csv"])
def test_existing_comparison_csv_carries_its_own_selected_population(tmp_path, unregistered):
    app, root = export_app(tmp_path)
    folder = tmp_path / "data/derived/comparisons/run_export"
    folder.mkdir(parents=True)
    atomic_write_json(
        folder / "comparison.json",
        {
            "status": "available",
            "run_id": "run_export",
            "cell_line": "K562",
            "perturbation": "MYC",
            "units": {"expression": "mean(log1p(CP10K))"},
            "parameters": {"population_counts": {"control": 1, "predicted": 1, "observed": 1}},
            "population_matching": {"status": "common_batches_only", "common_batches": ["batch_a"]},
            "genes": [
                {
                    "id": "ZERO",
                    "control": 1,
                    "predicted": 1.5,
                    "observed": 2,
                    "predicted_delta": 0.5,
                    "observed_delta": 1,
                    "absolute_error": 0.5,
                }
            ],
            "tasks": [],
        },
    )
    atomic_write_json(
        folder / "manifest.json",
        {
            "run_id": "run_export",
            "source_manifest_sha256": file_sha256(root / "manifest.json"),
            "inputs": {},
            "outputs": {"comparison.json": file_sha256(folder / "comparison.json")},
        },
    )
    if unregistered == "comparison.json":
        manifest = json.loads((folder / "manifest.json").read_text())
        manifest["outputs"].pop("comparison.json")
        atomic_write_json(folder / "manifest.json", manifest)
    if unregistered == "reaction_scores.csv":
        (folder / "reaction_scores.csv").write_text(
            "cell,R1,source\nc,1,control\np,999,predicted\no,3,observed\n", encoding="utf-8"
        )
    with TestClient(app) as client:
        url = "/api/v1/runs/run_export/comparison/download?table=genes"
        if unregistered == "reaction_scores.csv":
            url = "/api/v1/runs/run_export/export/table?table=reactions&population=comparison"
        response = client.get(url)
    if unregistered:
        assert response.status_code == 409
        return
    assert response.status_code == 200
    row = next(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert row["population"] == "comparison" and row["n_control"] == "1"
    assert row["n_predicted"] == "1" and row["n_observed"] == "1"
    assert row["selection_id"].startswith("comparison:")
    assert float(row["predicted_delta"]) == 0.5 and float(row["absolute_error"]) == 0.5
    assert row["units"] == "mean(log1p(CP10K))"
