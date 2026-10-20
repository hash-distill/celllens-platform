"""Paginated PDF exports of frozen run results; no inference or artifact mutation."""

import csv
import json
import math
from html import escape
from io import BytesIO
from threading import Lock
from typing import Any

from backend.app.schemas import RunRecord, RunSummary

_REPORT_LOCK = Lock()


def _number(value: Any, *, signed: bool = False) -> str:
    if value is None or not math.isfinite(float(value)):
        return "—"
    value = float(value)
    if value == 0:
        return "0"
    return format(value, "+.5g" if signed else ".5g")


def render_report_pdf(
    summary: RunSummary,
    record: RunRecord,
    provenance: dict[str, Any],
    comparison: dict[str, Any] | None = None,
    figure_pages: list[bytes] | None = None,
) -> bytes:
    from pypdf import PdfWriter
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    with _REPORT_LOCK:
        font = "STSong-Light"
        if font not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont(font))
        ink, green = colors.HexColor("#253437"), colors.HexColor("#247a70")
        body = ParagraphStyle("body", fontName=font, fontSize=10, leading=15, textColor=ink,
                              wordWrap="CJK", spaceAfter=6)
        title = ParagraphStyle("title", parent=body, fontSize=22, leading=30, textColor=green,
                               spaceAfter=10)
        heading = ParagraphStyle("section", parent=body, fontSize=13, leading=19, textColor=green,
                                 spaceBefore=16, spaceAfter=8, keepWithNext=True)
        cell = ParagraphStyle("cell", parent=body, fontSize=9, leading=13, spaceAfter=0)
        numeric = ParagraphStyle("numeric", parent=cell, alignment=TA_RIGHT)
        small = ParagraphStyle("small", parent=body, fontSize=8, leading=12)

        def text(value: Any, style: Any = body) -> Any:
            return Paragraph(escape(str(value if value is not None else "—")), style)

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
            topMargin=21 * mm, bottomMargin=19 * mm,
            title=f"CellLens {record.request.cell_line} / {record.request.perturbation}",
            author="CellLens", pageCompression=1,
        )

        def table(headers: list[str], rows: list[list[Any]], widths: list[float]) -> Any:
            data = [[text(value, cell) for value in headers]]
            data.extend([
                [text(value, cell if i == 0 else numeric) for i, value in enumerate(row)]
                for row in rows
            ])
            result = LongTable(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
            result.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5efea")),
                ("LINEBELOW", (0, 0), (-1, 0), 0.7, green),
                ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#ddded7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]))
            return result

        kind = provenance.get("source_type")
        source_label = (
            "合成演示数据" if kind == "synthetic_precomputed" or summary.result_kind == "synthetic_demo"
            else "历史模型结果" if kind == "frozen_precomputed" else "在线模型预测"
        )
        story: list[Any] = [
            text("细胞知镜 · 分析报告", title),
            text(f"CellLens  /  {record.request.cell_line}  /  {record.request.perturbation}", heading),
            text(source_label), Spacer(1, 6 * mm),
        ]
        parameters = [
            ("运行编号", record.run_id), ("细胞背景", record.request.cell_line),
            ("扰动基因", record.request.perturbation), ("请求预测细胞数", record.request.n_cells),
            ("随机种子", record.request.seed),
            ("创建时间（服务端记录）", record.created_at.isoformat(sep=" ", timespec="seconds")),
        ]
        story.append(table(["实验参数", "本次记录"], [list(row) for row in parameters],
                           [doc.width * 0.37, doc.width * 0.63]))

        def result_table(items: list[Any], label: str, units: str) -> None:
            if not items:
                return
            story.extend([text(label, heading), text(units, small)])
            observed = any(item.observed_delta is not None for item in items)
            headers = ["基因" if label.startswith("基因") else "代谢任务", "对照", "预测", "预测变化"]
            if observed:
                headers.append("观测变化")
            rows = []
            for item in items[:20]:
                row = [item.label, _number(item.control), _number(item.predicted),
                       _number(item.predicted_delta, signed=True)]
                if observed:
                    row.append(_number(item.observed_delta, signed=True))
                rows.append(row)
            numeric_width = 62 if observed else 70
            story.append(table(headers, rows, [doc.width - numeric_width * (len(headers) - 1)]
                               + [numeric_width] * (len(headers) - 1)))

        assets = provenance.get("assets", {})
        expression_units = (
            "表达单位：mean(log1p(CP10K))"
            if assets.get("dataset_expression_scale") == "log1p_cp10k"
            else "表达值：本次运行保存的平均表达"
        )
        result_table(summary.top_genes, "基因响应 · 已保存的主要变化", expression_units)
        result_table(summary.metabolic_tasks, "代谢任务 · 已保存的主要变化", "分数单位：scCellFie 任务评分")

        if comparison is not None:
            story.append(text("匹配实测比较", heading))
            expression = comparison.get("expression", {})
            values = [
                ["变化 Pearson", _number(expression.get("signed_delta_pearson"))],
                ["变化 Spearman", _number(expression.get("signed_delta_spearman"))],
                ["变化 MSE", _number(expression.get("mse"))],
                ["MSE / 不变化基线", _number(expression.get("mse_relative_to_no_change"))],
            ]
            story.append(table(["指标", "本案例结果"], values, [doc.width * 0.6, doc.width * 0.4]))
            population = comparison.get("parameters", {}).get("population_counts", {})
            if population:
                story.append(text(
                    f"评价细胞数：对照 {population.get('control', '—')} / "
                    f"预测 {population.get('predicted', '—')} / 实测 {population.get('observed', '—')}", small
                ))

        story.append(text("运行来源", heading))
        for label, value in (
            ("模型", assets.get("model_id")), ("数据", assets.get("dataset_id")),
            ("原始运行", provenance.get("source_run_id")),
            ("Manifest SHA-256", provenance.get("manifest_sha256")),
        ):
            if value:
                story.append(text(f"{label}：{value}", small))
        if comparison is not None:
            source = comparison.get("source", {})
            for label, key in (("实测来源", "repo"), ("固定版本", "revision")):
                if source.get(key):
                    story.append(text(f"{label}：{source[key]}", small))
        if figure_pages:
            story.append(text("后附表达与代谢空间科研图。", small))

        def page_chrome(canvas: Any, document: Any) -> None:
            canvas.saveState()
            canvas.setFont(font, 8)
            canvas.setFillColor(green)
            canvas.drawString(18 * mm, A4[1] - 12 * mm, "CellLens / 细胞知镜")
            canvas.setFillColor(ink)
            canvas.drawString(18 * mm, 10 * mm, record.run_id)
            canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"第 {document.page} 页")
            canvas.restoreState()

        doc.build(story, onFirstPage=page_chrome, onLaterPages=page_chrome)
        if not figure_pages:
            return buffer.getvalue()
        writer = PdfWriter()
        writer.append(BytesIO(buffer.getvalue()), outline_item="分析报告")
        for i, content in enumerate(figure_pages, 1):
            writer.append(BytesIO(content), outline_item=f"科研图 {i}")
        writer.add_metadata({"/Title": f"CellLens {record.run_id}", "/Author": "CellLens"})
        output = BytesIO()
        writer.write(output)
        return output.getvalue()


def build_report_pdf(container: Any, run_id: str) -> bytes:
    from backend.app.services.cell_state import CellStateUnavailable, _checked, _manifest, frozen_inputs
    from backend.app.services.cell_state_figure import render_cell_state
    from backend.app.services.cell_state_preparation import (
        ARTIFACT_KIND,
        prepared_document,
        prepared_manifest,
    )
    from backend.app.services.measured_comparison import load_comparison

    root, manifest, manifest_sha = _manifest(container, run_id)
    summary_sha = manifest.get("outputs", {}).get("summary.json", {}).get("sha256")
    summary_path = _checked(root / "summary.json", summary_sha)
    summary = RunSummary.model_validate_json(summary_path.read_text(encoding="utf-8"))
    record = container.store.get(run_id)
    if (summary.run_id, summary.cell_line, summary.perturbation) != (
        run_id, record.request.cell_line, record.request.perturbation
    ):
        raise CellStateUnavailable("Report identity differs from the frozen run")
    used_sources = [(summary_path, summary_sha)]
    outputs = manifest.get("outputs", {})
    # Historic summaries contain only ranked deltas. Read their saved means
    # from the complete, hash-verified outputs rather than leaving blank columns.
    for name, items in (("gene_deltas.csv", summary.top_genes),
                        ("task_trace.json", summary.metabolic_tasks)):
        if name not in outputs:
            continue
        expected = outputs[name].get("sha256")
        path = _checked(root / name, expected)
        used_sources.append((path, expected))
        if name.endswith(".csv"):
            with path.open(encoding="utf-8", newline="") as stream:
                rows = {row["gene"]: row for row in csv.DictReader(stream)}
        else:
            trace = json.loads(path.read_text(encoding="utf-8"))
            if trace.get("run_id") != run_id:
                raise CellStateUnavailable("Task trace does not match report run")
            rows = trace.get("tasks", {})
        for item in items:
            row = rows.get(item.id, {})
            for field in ("control", "predicted", "observed_delta"):
                value = row.get(field)
                if value is not None and value != "":
                    setattr(item, field, float(value))
    comparison = load_comparison(container.settings.project_root, run_id)
    figures = []
    if any(a.kind == ARTIFACT_KIND for a in container.store.artifacts(run_id)):
        inputs = frozen_inputs(container, run_id)
        bundle = prepared_manifest(container, inputs)
        assert bundle is not None
        for space, kind in (("expression", "gene"), ("metabolic", "task")):
            if f"{space}_umap" not in bundle[1]["figures"]:
                continue
            document = prepared_document(container, inputs, kind, "", "umap", space)
            assert document is not None
            figures.append(render_cell_state(document, "pdf"))
    content = render_report_pdf(
        summary, record, {**manifest, "manifest_sha256": manifest_sha}, comparison, figures
    )
    _checked(root / "manifest.json", manifest_sha)
    for path, expected in used_sources:
        _checked(path, expected)
    return content
