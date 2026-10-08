import json
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.main import create_app
from backend.app.schemas import CreateRunRequest, RunStatus
from backend.app.services import scientific_analysis
from backend.tests.test_api_runs import _settings, _write_registry


def fixture_data():
    database = {
        "task_info": pd.DataFrame(
            {"Task": ["task_a"], "System": ["CARBOHYDRATES METABOLISM"], "Subsystem": ["GLYCOLYSIS"]}
        ),
        "rxn_info": pd.DataFrame({"Reaction": ["rxn_a"], "GPR-symbol": ["GENE1 and MISSING"]}),
        "task_by_rxn": pd.DataFrame({"rxn_a": [1], "rxn_b": [1], "unrelated": [0]}, index=["task_a"]),
        "rxn_by_gene": pd.DataFrame({"GENE1": [1, 0], "MISSING": [1, 0]}, index=["rxn_a", "rxn_b"]),
        "_celllens_provenance": {"manifest_sha256": "a" * 64, "files": {"Task-Info.csv": "b" * 64}},
    }
    tasks = pd.DataFrame({"task_a": [2.0, 5.0], "source": ["control", "predicted"]})
    reactions = pd.DataFrame({"rxn_a": [3.0, 4.0], "source": ["control", "predicted"]})
    genes = pd.DataFrame({"control": [1.0], "predicted": [2.0], "predicted_delta": [1.0]}, index=["GENE1"])
    coverage = pd.DataFrame({"gene_fraction": [0.5], "evidence_level": ["insufficient"]}, index=["task_a"])
    return database, tasks, reactions, genes, coverage


def build_document():
    from backend.app.services.task_trace import build_task_trace

    database, tasks, reactions, genes, coverage = fixture_data()
    return build_task_trace("run_trace", database, "frozen-v1", tasks, reactions, genes, coverage)


def test_trace_uses_only_knowledge_edges_and_matching_scores():
    doc = build_document()
    assert doc["database_version"] == "frozen-v1"
    assert doc["database_provenance"]["manifest_sha256"] == "a" * 64
    task = doc["tasks"]["task_a"]
    assert task["category"] == "CARBOHYDRATES METABOLISM"
    assert task["predicted_delta"] == 3
    assert task["reaction_ids"] == ["rxn_a", "rxn_b"]
    assert doc["reactions"]["rxn_a"]["gene_ids"] == ["GENE1", "MISSING"]
    assert doc["genes"]["MISSING"]["predicted_delta"] is None
    assert doc["reactions"]["rxn_b"]["control"] is None
    assert doc["determinant_status"] == "unavailable"
    assert doc["relationship_kind"] == "knowledge_association"
    assert doc["genes"]["GENE1"]["predicted_delta"] == 1
    json.dumps(doc, allow_nan=False)


def test_summary_has_frozen_category_and_source_means():
    database, tasks, _, _, coverage = fixture_data()
    items = scientific_analysis._summarize_tasks(tasks, coverage, False, database)
    assert items[0]["category"] == "CARBOHYDRATES METABOLISM"
    assert items[0]["control"] == 2
    assert items[0]["predicted"] == 5


def completed_app(tmp_path):
    _write_registry(tmp_path)
    app = create_app(_settings(tmp_path))
    store = app.state.container.store
    store.create("run_trace", CreateRunRequest(cell_line="K562", perturbation="MYC", mode="precomputed"))
    store.transition("run_trace", RunStatus.COMPLETED, 100)
    root = app.state.container.settings.derived_root / "run_trace"
    root.mkdir(parents=True)
    return app, root


def publish(app, root, document):
    path = root / "task_trace.json"
    atomic_write_json(path, document)
    app.state.container.store.register_artifact(
        "run_trace",
        "task_trace",
        "run_trace/task_trace.json",
        file_sha256(path),
        path.stat().st_size,
        "application/json",
    )
    return path


def test_historical_missing_trace_never_falls_back(tmp_path):
    app, _ = completed_app(tmp_path)
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/run_trace/task-trace?task_id=task_a")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "TASK_TRACE_UNAVAILABLE"


def test_trace_api_bounds_lists_and_reports_absent_task(tmp_path):
    app, root = completed_app(tmp_path)
    publish(app, root, build_document())
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/runs/run_trace/task-trace?task_id=task_a&reaction_limit=1&gene_limit=1"
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["run_id"] == "run_trace"
        assert data["total_reactions"] == 2 and data["truncated"]
        assert data["reactions"][0]["total_genes"] == 2 and data["reactions"][0]["truncated"]
        assert len(data["reactions"][0]["genes"]) == 1
        assert data["warnings"]
        assert (
            client.get("/api/v1/runs/run_trace/task-trace?task_id=missing").json()["detail"]["code"]
            == "TASK_NOT_FOUND"
        )
        assert (
            client.get("/api/v1/runs/run_trace/task-trace?task_id=task_a&reaction_limit=101").status_code
            == 422
        )


def test_trace_rejects_tampered_or_cross_run_artifact(tmp_path):
    app, root = completed_app(tmp_path)
    document = build_document()
    document["run_id"] = "another_run"
    path = publish(app, root, document)
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/run_trace/task-trace?task_id=task_a")
        assert response.status_code == 500
        assert response.json()["detail"]["code"] == "INVALID_TASK_TRACE"
        document["run_id"] = "run_trace"
        atomic_write_json(path, document)
        response = client.get("/api/v1/runs/run_trace/task-trace?task_id=task_a")
        assert response.status_code == 500
        assert response.json()["detail"]["code"] == "INVALID_TASK_TRACE"


def test_invalid_optional_trace_does_not_hide_valid_metabolic_scores(tmp_path):
    app, root = completed_app(tmp_path)
    _, scores, _, _, coverage = fixture_data()
    scores.to_csv(root / "metabolic_task_scores.csv")
    coverage.to_csv(root / "metabolic_coverage.csv")
    path = publish(app, root, build_document())
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/run_trace/metabolic-tasks?scope=all")
        assert response.status_code == 200, response.text
        item = response.json()["items"][0]
        assert item["id"] == item["label"] == "task_a"
        assert item["category"] is None
        assert item["predicted_delta"] == 3
        trace = client.get("/api/v1/runs/run_trace/task-trace?task_id=task_a")
        assert trace.status_code == 500
        assert trace.json()["detail"]["code"] == "INVALID_TASK_TRACE"


def test_task_availability_distinguishes_missing_matching_and_corrupt_trace(tmp_path):
    app, root = completed_app(tmp_path)
    _, scores, reactions, _, coverage = fixture_data()
    scores["missing_task"] = [1.0, 2.0]
    coverage.loc["missing_task"] = [0.0, "insufficient"]
    scores.to_csv(root / "metabolic_task_scores.csv")
    coverage.to_csv(root / "metabolic_coverage.csv")
    with TestClient(app) as client:
        missing = client.get("/api/v1/runs/run_trace/metabolic-tasks?scope=all").json()
        assert missing["reactions_available"] is False
        assert all(item["trace_available"] is False for item in missing["items"])

        reactions.to_csv(root / "reaction_scores.csv")
        path = publish(app, root, build_document())
        present = client.get("/api/v1/runs/run_trace/metabolic-tasks?scope=all").json()
        assert present["reactions_available"] is True
        availability = {item["id"]: item["trace_available"] for item in present["items"]}
        assert availability == {"task_a": True, "missing_task": False}

        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        corrupt = client.get("/api/v1/runs/run_trace/metabolic-tasks?scope=all").json()
        assert all(item["trace_available"] is None for item in corrupt["items"])
        assert client.get("/api/v1/runs/run_trace/task-trace?task_id=task_a").status_code == 500


def test_top_tasks_also_expose_optional_result_availability(tmp_path):
    app, root = completed_app(tmp_path)
    atomic_write_json(
        root / "summary.json",
        {
            "run_id": "run_trace",
            "status": "completed",
            "stage_progress": 100,
            "cell_line": "K562",
            "perturbation": "MYC",
            "coverage": None,
            "top_genes": [],
            "metabolic_tasks": [
                {
                    "id": "task_a",
                    "label": "Task A",
                    "predicted_delta": 3,
                    "observed_delta": None,
                    "coverage": 0.5,
                    "evidence_level": "insufficient",
                    "determinant_genes": [],
                }
            ],
            "warnings": [],
            "error_code": None,
        },
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/run_trace/metabolic-tasks?scope=all")
        assert response.status_code == 200
        data = response.json()
        assert data["scope"] == "top"
        assert data["reactions_available"] is False
        assert data["items"][0]["trace_available"] is False


def test_real_frozen_mapping_is_not_invented():
    from backend.app.services.task_trace import build_task_trace

    root = Path(__file__).resolve().parents[2] / "data/registry/sccellfie/human"
    database = {
        "task_info": pd.read_csv(root / "Task-Info.csv"),
        "rxn_info": pd.read_json(root / "Rxn-Info-Recon2-2.json"),
        "task_by_rxn": pd.read_csv(root / "Task_by_Rxn.csv", index_col=0),
        "rxn_by_gene": pd.read_csv(root / "Rxn_by_Gene.csv", index_col=0),
        "_celllens_provenance": {
            "manifest_sha256": file_sha256(root / "manifest.json"),
            "files": json.loads((root / "manifest.json").read_text())["files"],
        },
    }
    task_id = "(R)-3-Hydroxybutanoate synthesis"
    tasks = pd.DataFrame({task_id: [1.0, 2.0], "source": ["control", "predicted"]})
    coverage = pd.DataFrame({"gene_fraction": [0.0], "evidence_level": ["insufficient"]}, index=[task_id])
    result = build_task_trace(
        "real_mapping",
        database,
        "frozen",
        tasks,
        pd.DataFrame({"source": ["control", "predicted"]}),
        pd.DataFrame(),
        coverage,
    )
    ids = result["tasks"][task_id]["reaction_ids"]
    expected = database["task_by_rxn"].loc[task_id]
    assert ids == sorted(str(key) for key, value in expected.items() if value != 0)
    assert ids and result["tasks"][task_id]["category"] == "CARBOHYDRATES METABOLISM"
    assert all(row["control"] is None for row in result["genes"].values())


def test_analysis_persists_trace_and_no_database_has_explicit_warning(tmp_path, monkeypatch):
    import anndata as ad
    import numpy as np

    from backend.app.core.registry import RegistryEntry
    from backend.app.engines.metabolic_engine import MetabolicResult

    database, _, _, _, _ = fixture_data()
    database["task_by_gene"] = pd.DataFrame({"GENE1": [1]}, index=["task_a"])
    control = ad.AnnData(np.array([[1.0, 3.0], [2.0, 2.0]]))
    control.var_names = ["GENE1", "GENE2"]
    predicted = control.copy()
    predicted.X = np.array([[3.0, 1.0], [3.0, 1.0]])
    control.write_h5ad(tmp_path / "control.h5ad")
    predicted.write_h5ad(tmp_path / "predicted.h5ad")

    class Engine:
        def run(self, combined, *, database, database_version, completeness):
            sources = combined.obs["celllens_source"].tolist()
            return MetabolicResult(
                pd.DataFrame(
                    {"task_a": [1.0 if s == "control" else 2.0 for s in sources]}, index=combined.obs_names
                ),
                pd.DataFrame(
                    {"rxn_a": [3.0 if s == "control" else 4.0 for s in sources]}, index=combined.obs_names
                ),
                pd.DataFrame(),
                completeness,
                database_version,
            )

    monkeypatch.setattr(scientific_analysis, "_load_frozen_database", lambda root: (database, "frozen-v1"))
    service = scientific_analysis.ScientificAnalysisService(tmp_path, Engine())
    model = RegistryEntry({}, tmp_path)
    dataset = RegistryEntry({"control_path": "control.h5ad"}, tmp_path)
    request = CreateRunRequest(cell_line="K562", perturbation="MYC")
    output = tmp_path / "result"
    output.mkdir()
    result = service.run("run_new", request, model, dataset, tmp_path / "predicted.h5ad", output)
    assert output / "task_trace.json" in result.artifacts
    document = json.loads((output / "task_trace.json").read_text())
    assert document["run_id"] == "run_new"
    assert document["genes"]["GENE1"]["predicted_delta"] > 0
    assert result.summary["metabolic_tasks"][0]["category"] == "CARBOHYDRATES METABOLISM"

    def missing(root):
        raise FileNotFoundError("disabled database")

    monkeypatch.setattr(scientific_analysis, "_load_frozen_database", missing)
    output2 = tmp_path / "unavailable"
    output2.mkdir()
    unavailable = service.run("run_no_db", request, model, dataset, tmp_path / "predicted.h5ad", output2)
    assert not (output2 / "task_trace.json").exists()
    assert unavailable.summary["metabolic_tasks"] == []
    assert "Metabolic analysis unavailable" in unavailable.summary["warnings"][0]


def test_database_loader_requires_all_consumed_files_be_pinned(tmp_path):
    import pytest

    (tmp_path / "other.csv").write_text("test")
    atomic_write_json(
        tmp_path / "manifest.json",
        {"enabled": True, "files": {"other.csv": file_sha256(tmp_path / "other.csv")}},
    )
    with pytest.raises(ValueError, match="all six"):
        scientific_analysis._load_frozen_database(tmp_path)


def test_trace_does_not_trust_unregistered_file(tmp_path):
    app, root = completed_app(tmp_path)
    atomic_write_json(root / "task_trace.json", build_document())
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/run_trace/task-trace?task_id=task_a")
        assert response.status_code == 500
        assert response.json()["detail"]["code"] == "INVALID_TASK_TRACE"
        assert (
            client.get("/api/v1/runs/missing/task-trace?task_id=task_a").json()["detail"]["code"]
            == "RUN_NOT_FOUND"
        )
