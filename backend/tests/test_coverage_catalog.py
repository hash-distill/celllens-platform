import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.core.run_manifest import file_sha256
from backend.app.main import create_app
from backend.app.services.completeness import compute_official_completeness
from backend.app.services.coverage_catalog import cached_completeness, coverage_catalog


@pytest.fixture
def coverage_app(tmp_path, monkeypatch):
    database = {
        "rxn_info": pd.DataFrame({"Reaction": ["complex_rxn", "single_rxn"], "GPR-symbol": ["A and B", "C"]}),
        "task_by_rxn": pd.DataFrame(
            {"complex_rxn": [1, 0], "single_rxn": [0, 1]}, index=["complex", "single"]
        ),
        "task_info": pd.DataFrame({"Task": ["complex", "single"], "System": ["ENERGY", "ENERGY"]}),
        "_celllens_provenance": {"manifest_sha256": "a" * 64, "files": {}},
    }
    root = tmp_path / "data" / "registry"
    root.mkdir(parents=True)
    models = []
    for cell_line, names in (("K562", "A\n"), ("Jurkat", "A\nC\n")):
        path = root / (cell_line + ".txt")
        path.write_text(names)
        models.append(
            {
                "id": "model-" + cell_line,
                "cell_line": cell_line,
                "enabled": True,
                "supported_perturbations": ["MYC", "TPI1", "MYC_LIKE"],
                "gene_list_path": str(path.relative_to(tmp_path)),
                "gene_list_sha256": file_sha256(path),
            }
        )
    (root / "models.json").write_text(json.dumps({"models": models}))
    (root / "datasets.json").write_text('{"datasets": []}')
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        database_url=f"sqlite+pysqlite:///{tmp_path / 'test.db'}",
        create_database_schema=True,
        worker_enabled=False,
    )
    cached_completeness.cache_clear()

    def loader(*_):
        return database, "fixture-v1"

    monkeypatch.setattr("backend.app.api.coverage._load_frozen_database", loader)
    monkeypatch.setattr("backend.app.services.scientific_analysis._load_frozen_database", loader)
    app = create_app(settings)
    yield app, settings, database
    cached_completeness.cache_clear()


def test_registered_panel_coverage_changes_without_creating_experiments(coverage_app):
    app, _, _ = coverage_app
    with TestClient(app) as client:
        first = client.get("/api/v1/coverage").json()
        second = client.get("/api/v1/coverage?cell_line=Jurkat").json()
        assert first["source"]["kind"] == "model"
        assert first["overall_summary"]["n_genes_in_db_present_in_adata"] == 1
        assert second["overall_summary"]["n_genes_in_db_present_in_adata"] == 2
        assert second["overall_summary"]["n_tasks_fully_covered_all"] == 1
        assert {task["id"]: task["coverage_status"] for task in first["tasks"]} == {
            "complex": "partial",
            "single": "absent",
        }
        assert second["tasks"][1]["present_genes_all"] == "C"
        assert next(gene for gene in second["genes"] if gene["symbol"] == "B")["tasks"] == ["complex"]
        assert client.get("/api/v1/experiments").json()["total"] == 0


def test_cached_model_coverage_still_rejects_tampered_panel(coverage_app):
    app, settings, _ = coverage_app
    with TestClient(app) as client:
        assert client.get("/api/v1/coverage").status_code == 200
        (settings.registry_root / "K562.txt").write_text("A\nB\nC\n")
        response = client.get("/api/v1/coverage")
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "COVERAGE_UNAVAILABLE"


def test_database_snapshot_change_invalidates_cached_computation(coverage_app):
    app, _, database = coverage_app
    with TestClient(app) as client:
        assert client.get("/api/v1/coverage").json()["overall_summary"]["n_genes_in_db_total"] == 3
        database["rxn_info"].loc[0, "GPR-symbol"] = "A and B and D"
        database["_celllens_provenance"]["manifest_sha256"] = "b" * 64
        assert client.get("/api/v1/coverage").json()["overall_summary"]["n_genes_in_db_total"] == 4


def test_sources_cannot_be_combined_or_unknown(coverage_app):
    app, _, _ = coverage_app
    with TestClient(app) as client:
        assert client.get("/api/v1/coverage?cell_line=K562&run_id=run_example").status_code == 422
        assert client.get("/api/v1/coverage?cell_line=unknown").status_code == 404
        assert client.get("/api/v1/coverage?analysis_id=invalid").status_code == 422




def test_catalogue_rejects_report_from_a_different_panel(coverage_app):
    _, _, database = coverage_app
    report = compute_official_completeness(["A"], database, "fixture-v1")
    with pytest.raises(ValueError, match="associations differ"):
        coverage_catalog(["C"], database, report)


def test_perturbation_classification_never_changes_available_targets(coverage_app):
    app, settings, _ = coverage_app
    snapshot = Path(__file__).resolve().parents[2] / "data/registry/gene_annotations"
    shutil.copytree(snapshot, settings.registry_root / "gene_annotations")
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/perturbations?cell_line=K562").json()
        assert response["items"] == ["MYC", "MYC_LIKE", "TPI1"]
        assert response["classification"]["available"] is True
        assert {row["symbol"]: row["category_ids"] for row in response["genes"]} == {
            "MYC": ["PC00264"],
            "TPI1": ["PC00135"],
            "MYC_LIKE": ["unclassified"],
        }
        path = settings.registry_root / "gene_annotations/human.json.gz"
        path.write_bytes(path.read_bytes() + b"tampered")
        unavailable = client.get("/api/v1/catalog/perturbations?cell_line=K562").json()
        assert unavailable["items"] == response["items"]
        assert unavailable["classification"]["available"] is False
        assert unavailable["classification"]["warning"]
        assert all(row["category_ids"] == ["unclassified"] for row in unavailable["genes"])
        assert client.get("/api/v1/experiments").json()["total"] == 0
