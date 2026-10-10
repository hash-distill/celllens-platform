import json
from types import SimpleNamespace

import anndata as ad
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.tests.test_task_trace import completed_app


def database():
    return {
        "rxn_info": pd.DataFrame({"Reaction": ["r_or", "r_and"], "GPR-symbol": ["A or B", "A and B"]}),
        "task_by_rxn": pd.DataFrame({"r_or": [1, 0], "r_and": [0, 1]}, index=["alternative", "complex"]),
        "_celllens_provenance": {"manifest_sha256": "a" * 64, "files": {"db.csv": "b" * 64}},
    }


def test_official_report_preserves_gpr_scopes_and_empty_essential_sets():
    from sccellfie.reports import compute_dataset_completeness

    from backend.app.services.completeness import compute_official_completeness

    db = database()
    result = compute_official_completeness(["a"], db, "fixture-v1")
    native = compute_dataset_completeness(
        ad.AnnData(np.zeros((0, 1)), var=pd.DataFrame(index=["A"])),
        {"r_or": "A or B", "r_and": "A and B"},
        db["task_by_rxn"],
    )
    assert result["overall_summary"] == native["overall_summary"].iloc[0].to_dict()
    by_id = {row["id"]: row for row in result["tasks"]}
    assert by_id["alternative"]["fraction_present_all"] == 0.5
    assert by_id["alternative"]["n_genes_essential"] == 0
    assert by_id["complex"]["n_missing_essential"] == 1
    assert (
        by_id["alternative"]["impact_weighted_completeness_all"]
        > by_id["complex"]["impact_weighted_completeness_all"]
    )
    assert result["method"] == "sccellfie.reports.compute_dataset_completeness"
    assert "evidence_level" not in by_id["alternative"]
    json.dumps(result, allow_nan=False)


def test_official_report_requires_unambiguous_gene_panel():
    from backend.app.services.completeness import compute_official_completeness

    with pytest.raises(ValueError, match="Duplicate"):
        compute_official_completeness(["a", "A"], database(), "fixture-v1")


def test_project_legacy_levels_do_not_block_official_scoring(monkeypatch):
    import sccellfie

    from backend.app.engines.metabolic_engine import ScCellFieEngine

    cells = ad.AnnData(np.ones((1, 1)), var=pd.DataFrame(index=["A"]))
    from backend.app.services.expression_scale import mark_cp10k

    mark_cp10k(cells)
    task_scores = pd.DataFrame({"alternative": [1.0]}, index=cells.obs_names)
    reaction_scores = pd.DataFrame({"r_or": [1.0]}, index=cells.obs_names)
    output = SimpleNamespace(
        metabolic_tasks=SimpleNamespace(to_df=lambda: task_scores),
        reactions=SimpleNamespace(to_df=lambda: reaction_scores),
        uns={},
    )
    monkeypatch.setattr(sccellfie, "run_sccellfie_pipeline", lambda *args, **kwargs: {"adata": output})
    db = database()
    db["thresholds"] = pd.DataFrame({"sccellfie_threshold": [1.0]}, index=["A"])
    legacy = pd.DataFrame({"evidence_level": ["insufficient"]}, index=["alternative"])
    result = ScCellFieEngine().run(cells, database=db, database_version="test-v1", completeness=legacy)
    assert result.task_scores.loc[cells.obs_names[0], "alternative"] == 1.0


def test_completeness_api_requires_registered_run_bound_report(tmp_path):
    from backend.app.services.completeness import compute_official_completeness

    app, root = completed_app(tmp_path)
    genes = root / "gene_deltas.csv"
    genes.write_text("gene,predicted_delta\nA,1\n", encoding="utf-8")
    doc = compute_official_completeness(["A"], database(), "fixture-v1")
    doc.update(run_id="run_trace", source_gene_sha256=file_sha256(genes))
    path = root / "official_completeness.json"
    with TestClient(app) as client:
        assert client.get("/api/v1/runs/run_trace/completeness").status_code == 404
        atomic_write_json(path, doc)
        assert client.get("/api/v1/runs/run_trace/completeness").status_code == 500
        app.state.container.store.register_artifact(
            "run_trace",
            "official_completeness",
            "run_trace/official_completeness.json",
            file_sha256(path),
            path.stat().st_size,
            "application/json",
        )
        response = client.get("/api/v1/runs/run_trace/completeness")
        assert response.status_code == 200, response.text
        assert response.json()["run_id"] == "run_trace"
        genes.write_text("gene,predicted_delta\nB,2\n", encoding="utf-8")
        assert client.get("/api/v1/runs/run_trace/completeness").status_code == 500
