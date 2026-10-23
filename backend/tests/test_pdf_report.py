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
            "run_id": "run_pdf", "tasks": {"task_a": {
                "control": 4.567, "predicted": 3.567, "reaction_ids": ["r1", "r2"],
            }},
            "reactions": {"r1": {"gene_ids": ["A", "B", "C"]},
                          "r2": {"gene_ids": ["A", "D"]}},
            "genes": {"A": {"control": 0, "predicted": 0},
                      "B": {"control": 1, "predicted": 2},
                      "C": {"control": None, "predicted": None},
                      "D": {"control": None, "predicted": None}},
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


def pdf_text(content):
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(content)).pages)


def test_report_keeps_partial_tasks_with_coverage_evidence_and_deduplicated_gene_counts(tmp_path):
    app, _ = report_app(tmp_path, full_results=True)
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/run_pdf/report")
    assert response.status_code == 200
    text = pdf_text(response.content)
    for expected in ("葡萄糖代谢", "50%", "2/4", "exploratory", "部分覆盖", "supported",
                     "覆盖支持", "不等于生物学正确性", "不等于实测代谢通量"):
        assert expected in text


def test_report_uses_existing_bilingual_task_guide_and_keeps_stable_id(tmp_path):
    from backend.app.services.pdf_report import render_report_pdf

    app, root = report_app(tmp_path)
    summary = RunSummary.model_validate_json((root / "summary.json").read_text(encoding="utf-8"))
    summary.metabolic_tasks[0].id = "Fructose degradation (to glucose-3-phosphate)"
    summary.metabolic_tasks[0].label = summary.metabolic_tasks[0].id
    before = summary.model_dump()
    text = pdf_text(render_report_pdf(summary, app.state.container.store.get("run_pdf"), {}))
    assert "果糖降解相关步骤" in text
    assert "".join(summary.metabolic_tasks[0].id.split()) in "".join(text.split())
    assert summary.model_dump() == before


@pytest.mark.parametrize("ratio", [1, 1.5529])
def test_report_attaches_diagnostic_protocol_population_and_baseline_limitations(tmp_path, ratio):
    from backend.app.services.pdf_report import render_report_pdf

    app, root = report_app(tmp_path)
    summary = RunSummary.model_validate_json((root / "summary.json").read_text(encoding="utf-8"))
    comparison = {
        "expression": {"mse_relative_to_no_change": ratio},
        "held_out_validation": False, "training_exclusion_verified": False,
        "protocol_status": "matched_observation_diagnostic",
        "parameters": {"population_counts": {"control": 840, "predicted": 209, "observed": 96}},
        "population_matching": {"status": "common_batches_only", "batch_key": "gem_group",
                                "common_batches": ["1", "3"],
                                "input_cells": {"control": 1024, "predicted": 256, "observed": 120},
                                "limitation": "Batch frequencies are not reweighted"},
        "warnings": ["Diagnostic warning kept verbatim & <safe>"],
    }
    text = pdf_text(render_report_pdf(summary, app.state.container.store.get("run_pdf"), {}, comparison))
    for expected in ("held_out_validation=false", "training_exclusion_verified=false",
                     "protocol_status=matched_observation_diagnostic", "匹配实测诊断",
                     "不能作为独立留出评测", "840", "209", "96", "gem_group", "1, 3",
                     "common_batches_only", "Batch frequencies are not reweighted",
                     "Diagnostic warning kept verbatim & <safe>", "未优于不变化基线",
                     "原分析表", "诊断群体", "不能直接视为同一群体"):
        assert expected in text


def test_report_marks_unverified_protocol_and_missing_comparison_explicitly(tmp_path):
    from backend.app.services.pdf_report import render_report_pdf

    app, root = report_app(tmp_path)
    summary = RunSummary.model_validate_json((root / "summary.json").read_text(encoding="utf-8"))
    record = app.state.container.store.get("run_pdf")
    missing = pdf_text(render_report_pdf(summary, record, {}))
    assert "本报告未载入可核验的匹配实测比较" in missing
    unknown = pdf_text(render_report_pdf(summary, record, {}, {"expression": {}}))
    assert "held_out_validation=unknown" in unknown
    assert "training_exclusion_verified=unknown" in unknown
    assert "不能作为独立留出评测" in unknown


def test_report_only_claims_observed_figures_when_figure_metadata_confirms_them(tmp_path):
    from reportlab.pdfgen.canvas import Canvas

    from backend.app.services.pdf_report import render_report_pdf

    app, root = report_app(tmp_path)
    summary = RunSummary.model_validate_json((root / "summary.json").read_text(encoding="utf-8"))
    buffer = BytesIO()
    canvas = Canvas(buffer)
    canvas.drawString(10, 30, "Existing figure")
    canvas.save()
    text = pdf_text(render_report_pdf(
        summary, app.state.container.store.get("run_pdf"), {}, {"expression": {}}, [buffer.getvalue()],
        figure_context=[{"space": "expression", "feature_id": "MYC",
                         "population_counts": {"control": 1024, "predicted": 256}}],
    ))
    assert "附图不含实测细胞" in text
    assert "1024" in text and "256" in text
    assert "原分析表／附图与匹配实测诊断采用各自保存的群体" in text


def test_report_embeds_available_system_cjk_font(tmp_path):
    import os
    from pathlib import Path

    font = Path(os.environ.get("WINDIR", "/nonexistent")) / "Fonts" / "simhei.ttf"
    if not font.is_file():
        pytest.skip("System embedding fixture is only available on Windows")
    app, _ = report_app(tmp_path)
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/run_pdf/report")
    reader = PdfReader(BytesIO(response.content))
    descriptors = [font.get_object().get("/FontDescriptor")
                   for page in reader.pages for font in page["/Resources"]["/Font"].values()]
    assert any(descriptor and descriptor.get_object().get("/FontFile2") for descriptor in descriptors)


def test_report_discloses_font_fallback_when_no_embeddable_font_exists(tmp_path, monkeypatch):
    from backend.app.services import pdf_report

    monkeypatch.setattr(pdf_report, "_report_font_candidates", lambda: [])
    app, _ = report_app(tmp_path)
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/run_pdf/report")
    assert response.status_code == 200
    assert "中文字体未嵌入" in pdf_text(response.content)
    assert "CELLLENS_PDF_FONT" in pdf_text(response.content)


def test_legacy_task_aggregate_rows_are_not_reported_as_cell_counts(tmp_path, monkeypatch):
    from backend.app.services import cell_state
    from backend.app.services.pdf_report import build_report_pdf

    app, root = report_app(tmp_path)
    path = root / "metabolic_task_scores.csv"
    path.write_text("task,source,score\nT1,control,1\nT1,predicted,2\n", encoding="utf-8")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["outputs"][path.name] = {"sha256": file_sha256(path)}
    atomic_write_json(root / "manifest.json", manifest)
    sha = file_sha256(root / "manifest.json")
    monkeypatch.setattr(cell_state, "_manifest", lambda *args: (root, manifest, sha))
    text = pdf_text(build_report_pdf(app.state.container, "run_pdf"))
    assert "原分析表细胞数" not in text
    assert "冻结产物未提供可核验计数" in text


def test_report_keeps_numeric_values_on_one_line(tmp_path):
    from backend.app.services.pdf_report import render_report_pdf

    app, root = report_app(tmp_path)
    summary = RunSummary.model_validate_json((root / "summary.json").read_text(encoding="utf-8"))
    summary.metabolic_tasks[0].predicted_delta = -0.31541
    text = pdf_text(render_report_pdf(summary, app.state.container.store.get("run_pdf"), {}))
    assert "-0.31541" in text
