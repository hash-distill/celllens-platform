import json

import pandas as pd
from fastapi.testclient import TestClient

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.measured_results import read_table, table_page
from backend.tests.test_task_trace import completed_app


def test_measured_function_order_uses_coverage_then_identity_but_genes_keep_delta_order(tmp_path):
    pd.DataFrame(
        [
            {"task": "z_big", "observed_delta": 999, "gene_fraction": 0.1},
            {"task": "b_small", "observed_delta": 0.1, "gene_fraction": 1},
            {"task": "a_small", "observed_delta": 0.2, "gene_fraction": 1},
        ]
    ).to_csv(tmp_path / "tasks.csv", index=False)
    assert read_table(tmp_path, "tasks")["task"].tolist() == ["a_small", "b_small", "z_big"]
    pd.DataFrame([{"reaction": "z", "observed_delta": 999}, {"reaction": "a", "observed_delta": 0.1}]).to_csv(
        tmp_path / "reactions.csv", index=False
    )
    assert read_table(tmp_path, "reactions")["reaction"].tolist() == ["a", "z"]
    pd.DataFrame([{"gene": "a", "observed_delta": 0.1}, {"gene": "z", "observed_delta": -999}]).to_csv(
        tmp_path / "genes.csv", index=False
    )
    assert read_table(tmp_path, "genes")["gene"].tolist() == ["z", "a"]


def test_prediction_task_limit_applies_after_coverage_order_not_raw_task_delta(tmp_path):
    app, root = completed_app(tmp_path)
    pd.DataFrame(
        {"small_covered": [1.0, 1.1], "large_partial": [1.0, 10000.0], "source": ["control", "predicted"]},
        index=["c", "p"],
    ).to_csv(root / "metabolic_task_scores.csv")
    pd.DataFrame(
        {"gene_fraction": [1.0, 0.1], "evidence_level": ["supported", "insufficient"]},
        index=["small_covered", "large_partial"],
    ).to_csv(root / "metabolic_coverage.csv")
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/run_trace/metabolic-tasks?scope=all&limit=1")
        assert response.status_code == 200, response.text
        assert response.json()["items"][0]["id"] == "small_covered"
        assert response.json()["total"] == 2


def test_measured_task_categories_require_exact_frozen_knowledge_version(tmp_path):
    result = tmp_path / "data/derived/measured/measured_fixture"
    result.mkdir(parents=True)
    pd.DataFrame(
        [
            {"task": "known", "observed_delta": 1, "gene_fraction": 1},
            {"task": "unknown", "observed_delta": 999, "gene_fraction": 1},
        ]
    ).to_csv(result / "tasks.csv", index=False)
    database = tmp_path / "data/registry/sccellfie/human"
    database.mkdir(parents=True)
    (database / "Task-Info.csv").write_text("Task,System,Subsystem\nknown,LIPID METABOLISM,FATTY ACID\n")
    digest = file_sha256(database / "Task-Info.csv")
    manifest = {"version": "frozen-v1", "files": {"Task-Info.csv": digest}}
    atomic_write_json(database / "manifest.json", manifest)
    summary = {
        "metabolism": {
            "database_version": "frozen-v1",
            "database_provenance": {
                "manifest_sha256": file_sha256(database / "manifest.json"),
                "files": {"Task-Info.csv": digest},
            },
        }
    }
    original = file_sha256(result / "tasks.csv")
    rows = table_page(result, summary, "tasks", "", 10, 0)["items"]
    known = next(row for row in rows if row["task"] == "known")
    assert known["category"] == "LIPID METABOLISM" and known["subcategory"] == "FATTY ACID"
    assert next(row for row in rows if row["task"] == "unknown")["category"] is None
    assert file_sha256(result / "tasks.csv") == original
    summary["metabolism"]["database_version"] = "different-version"
    assert all(row["category"] is None for row in table_page(result, summary, "tasks", "", 10, 0)["items"])
    summary["metabolism"]["database_version"] = "frozen-v1"
    manifest["version"] = "new-v2"
    atomic_write_json(database / "manifest.json", manifest)
    assert all(row["category"] is None for row in table_page(result, summary, "tasks", "", 10, 0)["items"])
    assert json.loads((database / "manifest.json").read_bytes())["version"] == "new-v2"
