import json
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.schemas import CreateRunRequest, RunStatus, RunSummary
from backend.tests.test_api_runs import _settings, _write_registry


def report_app(tmp_path, full_results=False):
    from backend.app.main import create_app

    _write_registry(tmp_path)
    app = create_app(_settings(tmp_path))
    store = app.state.container.store
    store.create("run_pdf", CreateRunRequest(cell_line="K562", perturbation="MYC", n_cells=64))
    store.transition("run_pdf", RunStatus.COMPLETED, 100)
    root = app.state.container.settings.derived_root / "run_pdf"
    root.mkdir(parents=True)
    summary = RunSummary(
        run_id="run_pdf", cell_line="K562", perturbation="MYC", status="completed", stage_progress=100,
        top_genes=[{
            "id": "MYC", "label": "MYC", "control": 0, "predicted": 1.25, "predicted_delta": 1.25,
            "coverage": 1, "evidence_level": "supported",
        }],
        metabolic_tasks=[{
            "id": "task_a", "label": "葡萄糖代谢 / Glucose & ATP <summary>",
            "control": 1, "predicted": 0, "predicted_delta": -1,
            "coverage": 0.5, "evidence_level": "exploratory",
        }],
    )
    if full_results:
        summary.top_genes[0].control = summary.top_genes[0].predicted = None
        summary.metabolic_tasks[0].control = summary.metabolic_tasks[0].predicted = None
        (root / "gene_deltas.csv").write_text(
            "gene,control,predicted,predicted_delta\nMYC,2.345,3.595,1.25\n", encoding="utf-8"
        )
        atomic_write_json(root / "task_trace.json", {
            "run_id": "run_pdf", "tasks": {"task_a": {"control": 4.567, "predicted": 3.567}},
        })
    atomic_write_json(root / "summary.json", summary.model_dump(mode="json"))
    (root / "report.html").write_text("<html>Original report remains frozen</html>", encoding="utf-8")
    atomic_write_json(root / "manifest.json", {
        "request": store.get("run_pdf").request.model_dump(mode="json"),
        "assets": {"model_id": "state-test", "dataset_id": "data-test"},
        "outputs": {p.name: {"sha256": file_sha256(p)} for p in root.iterdir()},
    })
    path = root / "manifest.json"
    store.register_artifact("run_pdf", "manifest", "run_pdf/manifest.json", file_sha256(path),
                            path.stat().st_size, "application/json")
    return app, root


def test_report_endpoint_returns_real_chinese_pdf_and_preserves_frozen_files(tmp_path):
    app, root = report_app(tmp_path)
    before = {p.name: file_sha256(p) for p in root.iterdir()}
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/run_pdf/report")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert '.pdf"' in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF-")
    reader = PdfReader(BytesIO(response.content))
    text = "\n".join(page.extract_text() for page in reader.pages)
    for expected in ("CellLens", "细胞知镜", "run_pdf", "K562", "MYC", "葡萄糖", "1.25", "state-test"):
        assert expected in text
    assert "<summary>" in text and "& ATP" in text
    assert "观测变化" not in text
    assert before == {p.name: file_sha256(p) for p in root.iterdir()}


@pytest.mark.parametrize("target", ["summary.json", "manifest.json"])
def test_report_rejects_changed_frozen_source(tmp_path, target):
    app, root = report_app(tmp_path)
    with (root / target).open("a", encoding="utf-8") as stream:
        stream.write(" ")
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/run_pdf/report")
    assert response.status_code == 409


def test_pdf_report_handles_long_tables_and_observed_columns(tmp_path):
    from backend.app.services.pdf_report import render_report_pdf

    app, root = report_app(tmp_path)
    document = json.loads((root / "summary.json").read_text())
    document["top_genes"] = [
        {**document["top_genes"][0], "id": f"GENE_{i}", "label": f"GENE_{i}", "observed_delta": 0}
        for i in range(20)
    ]
    document["metabolic_tasks"] = [
        {**document["metabolic_tasks"][0], "id": f"task_{i}",
         "label": f"Task {i}: " + "A long metabolic task description " * 4}
        for i in range(20)
    ]
    content = render_report_pdf(
        RunSummary.model_validate(document), app.state.container.store.get("run_pdf"),
        {"manifest_sha256": "a" * 64, "assets": {}},
    )
    reader = PdfReader(BytesIO(content))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert len(reader.pages) >= 3
    assert "GENE_19" in text and "Task 19" in text and "观测变化" in text


def test_report_fills_summary_means_from_verified_full_results(tmp_path):
    app, root = report_app(tmp_path, full_results=True)
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/run_pdf/report")
        assert response.status_code == 200
        text = "\n".join(p.extract_text() for p in PdfReader(BytesIO(response.content)).pages)
        assert "2.345" in text and "3.595" in text and "4.567" in text and "3.567" in text
        with (root / "gene_deltas.csv").open("a") as stream:
            stream.write(" ")
        assert client.get("/api/v1/runs/run_pdf/report").status_code == 409
