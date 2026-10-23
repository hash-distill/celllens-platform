"""Paginated PDF exports of frozen run results; no inference or artifact mutation."""

import csv
import json
import math
import os
import re
from hashlib import sha256
from html import escape
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any

from backend.app.schemas import RunRecord, RunSummary

_REPORT_LOCK = Lock()


def _report_font_candidates() -> list[Path]:
    """Prefer a configured/bundled font, then installed fonts without redistributing them."""
    candidates = []
    configured = os.environ.get("CELLLENS_PDF_FONT")
    if configured:
        candidates.append(Path(configured).expanduser())
    bundled = Path(__file__).resolve().parents[1] / "resources" / "fonts"
    candidates.extend(sorted(bundled.glob("*.ttf")))
    if os.environ.get("WINDIR"):
        directory = Path(os.environ["WINDIR"]) / "Fonts"
        candidates.extend(directory / name for name in (
            "simhei.ttf", "simfang.ttf", "msyh.ttc", "NotoSansSC-Regular.ttf", "NotoSansSC-VF.ttf",
        ))
    for directory in (Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
                      Path.home() / ".local/share/fonts", Path("/Library/Fonts")):
        if directory.is_dir():
            candidates.extend(sorted(directory.rglob("*NotoSans*CJK*.ttc")))
            candidates.extend(sorted(directory.rglob("*NotoSans*SC*.ttf")))
            candidates.extend(sorted(directory.rglob("*wqy*.ttc")))
    return candidates


def _report_font() -> tuple[str, str | None]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFError, TTFont

    for path in _report_font_candidates():
        if not path.is_file():
            continue
        name = "CellLensCJK_" + sha256(str(path.resolve()).encode()).hexdigest()[:12]
        if name in pdfmetrics.getRegisteredFontNames():
            return name, None
        try:
            candidate = TTFont(name, str(path))
            face = candidate.face
            # OS/2 fsType: restricted embedding, no subsetting, or bitmap-only.
            if "OS/2" in face.table and int.from_bytes(face.get_table("OS/2")[8:10], "big") & 0x0302:
                continue
            if not all(ord(char) in face.charToGlyph for char in "细胞知镜分析报告覆盖实测"):
                continue
            pdfmetrics.registerFont(candidate)
            return name, None
        except (OSError, ValueError, TTFError):
            continue
    fallback = "STSong-Light"
    if fallback not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(fallback))
    return fallback, (
        "中文字体未嵌入：本报告使用 STSong-Light 阅读器字体替代，跨设备显示取决于阅读器。"
        "可通过 CELLLENS_PDF_FONT 配置允许嵌入的中文 TTF/TTC 字体后重新导出。"
    )


def _task_gene_counts(trace: dict[str, Any] | None, task_id: str) -> tuple[int, int] | None:
    """Count distinct associated genes only when the frozen trace is complete."""
    if not trace or not all(isinstance(trace.get(key), dict) for key in ("tasks", "reactions", "genes")):
        return None
    task = trace["tasks"].get(task_id, {})
    if "reaction_ids" not in task:
        return None
    associated = set()
    for reaction_id in task["reaction_ids"]:
        reaction = trace["reactions"].get(reaction_id)
        if not isinstance(reaction, dict) or "gene_ids" not in reaction:
            return None
        associated.update(reaction["gene_ids"])
    if not all(gene in trace["genes"] for gene in associated):
        return None
    present = sum(
        all(trace["genes"][gene].get(source) is not None
            and math.isfinite(float(trace["genes"][gene][source])) for source in ("control", "predicted"))
        for gene in associated
    )
    return present, len(associated)


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
    *,
    task_trace: dict[str, Any] | None = None,
    population_counts: dict[str, int] | None = None,
    figure_context: list[dict[str, Any]] | None = None,
) -> bytes:
    from pypdf import PdfWriter
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    from backend.app.services.gene_education import TASK_GUIDES

    with _REPORT_LOCK:
        font, font_warning = _report_font()
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
            return Paragraph(escape(str(value if value is not None else "—")).replace("\n", "<br/>"), style)

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
            topMargin=21 * mm, bottomMargin=19 * mm,
            title=f"CellLens {record.request.cell_line} / {record.request.perturbation}",
            author="CellLens", pageCompression=1,
        )

        def table(headers: list[str], rows: list[list[Any]], widths: list[float]) -> Any:
            data = [[text(value, cell) for value in headers]]

            def table_cell(value: Any, column: int) -> Any:
                style = cell if column == 0 else numeric
                if column and re.fullmatch(r"[+-]?\d+(?:\.\d+)?(?:e[+-]?\d+)?", str(value), re.I):
                    size = min(style.fontSize, (widths[column] - 14) / stringWidth(str(value), font, 1))
                    style = ParagraphStyle("fitted_number", parent=style, fontSize=size, splitLongWords=0)
                return text(value, style)

            data.extend([
                [table_cell(value, i) for i, value in enumerate(row)]
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
        story.append(text("原分析表／附图与匹配实测诊断采用各自保存的群体，不能直接视为同一群体；"
                          "以下原分析表保留本次运行的均值，实测指标采用后文的诊断群体。", small))
        if population_counts:
            story.append(text("原分析表细胞数：" + " / ".join(
                f"{label} {population_counts.get(key, '—')}"
                for key, label in (("control", "对照"), ("predicted", "预测"), ("observed", "实测"))
                if key in population_counts
            ), small))
        else:
            story.append(text(
                "原分析表群体数量：冻结产物未提供可核验计数；请求预测细胞数不是评价人数。", small
            ))

        def result_table(items: list[Any], label: str, units: str) -> None:
            if not items:
                return
            story.extend([text(label, heading), text(units, small)])
            observed = any(item.observed_delta is not None for item in items)
            is_task = not label.startswith("基因")
            headers = ["代谢任务 / 稳定 ID" if is_task else "基因", "对照", "预测", "预测变化"]
            if observed:
                headers.append("观测变化")
            if is_task:
                headers.extend(["关联基因覆盖", "覆盖证据"])
            rows = []
            for item in items[:20]:
                name = item.label
                if is_task:
                    guide = TASK_GUIDES.get(item.id, {})
                    name = f"{guide['name_zh']} / {item.id}" if guide.get("name_zh") else (
                        f"{item.label} / {item.id}" if item.label != item.id else item.id
                    )
                row = [name, _number(item.control), _number(item.predicted),
                       _number(item.predicted_delta, signed=True)]
                if observed:
                    row.append(_number(item.observed_delta, signed=True))
                if is_task:
                    counts = _task_gene_counts(task_trace, item.id)
                    coverage = f"{item.coverage:.2%}".replace(".00%", "%")
                    if counts is not None:
                        coverage += f"\n({counts[0]}/{counts[1]})"
                    meanings = {
                        "supported": "覆盖支持", "exploratory": "部分覆盖", "insufficient": "覆盖不足",
                    }
                    row.extend([coverage, f"{item.evidence_level}：{meanings[item.evidence_level]}"])
                rows.append(row)
            if is_task:
                count = 4 if observed else 3
                widths = [doc.width - count * 46 - 150] + [46] * count + [70, 80]
            else:
                numeric_width = 62 if observed else 70
                widths = ([doc.width - numeric_width * (len(headers) - 1)]
                          + [numeric_width] * (len(headers) - 1))
            story.append(table(headers, rows, widths))
            if is_task:
                story.append(text(
                    "关联基因覆盖为当前输入可用关联基因的比例；括号为已有/总关联基因数（按完整冻结关联去重，"
                    "缺少完整关联时不推算数量）。supported 表示覆盖支持；exploratory 表示部分覆盖；"
                    "insufficient 表示覆盖不足，相关任务仍保留。覆盖证据不等于生物学正确性已验证，"
                    "任务分数不等于实测代谢通量。", small
                ))

        assets = provenance.get("assets", {})
        expression_units = (
            "表达单位：mean(log1p(CP10K))"
            if assets.get("dataset_expression_scale") == "log1p_cp10k"
            else "表达值：本次运行保存的平均表达"
        )
        result_table(summary.top_genes, "基因响应 · 已保存的主要变化", expression_units)
        result_table(summary.metabolic_tasks, "代谢任务 · 已保存的主要变化", "分数单位：scCellFie 任务评分")

        if comparison is not None:
            story.append(text("匹配实测诊断", heading))
            for key in ("held_out_validation", "training_exclusion_verified", "protocol_status"):
                value = comparison.get(key)
                display = (str(value).lower() if isinstance(value, bool)
                           else value if value is not None else "unknown")
                story.append(text(f"{key}={display}", small))
            if not (comparison.get("held_out_validation") is True
                    and comparison.get("training_exclusion_verified") is True
                    and comparison.get("protocol_status") in {"held_out_validation", "independent_held_out"}):
                story.append(text("留出协议或训练排除尚未核实，不能作为独立留出评测；"
                                  "这些指标只描述本案例的匹配实测诊断。", small))
            expression = comparison.get("expression", {})
            values = [
                ["变化 Pearson", _number(expression.get("signed_delta_pearson"))],
                ["变化 Spearman", _number(expression.get("signed_delta_spearman"))],
                ["变化 MSE", _number(expression.get("mse"))],
                ["MSE / 不变化基线", _number(expression.get("mse_relative_to_no_change"))],
            ]
            story.append(table(["指标", "本案例结果"], values, [doc.width * 0.6, doc.width * 0.4]))
            ratio = expression.get("mse_relative_to_no_change")
            if ratio is not None and math.isfinite(float(ratio)) and float(ratio) >= 1:
                story.append(text("MSE 比值 ≥ 1：本案例预测未优于不变化基线（预测扰动等于对照）。", small))
            population = comparison.get("parameters", {}).get("population_counts", {})
            if population:
                story.append(text(
                    f"诊断群体细胞数：对照 {population.get('control', '—')} / "
                    f"预测 {population.get('predicted', '—')} / 实测 {population.get('observed', '—')}", small
                ))
            else:
                story.append(text("诊断群体细胞数：未提供，不能从请求细胞数推算。", small))
            matching = comparison.get("population_matching") or {}
            story.append(text(
                f"共同批次选择：{matching.get('status', 'unknown')}；"
                f"批次字段：{matching.get('batch_key', 'unknown')}；"
                f"共同批次：{', '.join(map(str, matching.get('common_batches', []))) or '未提供'}", small
            ))
            if matching.get("input_cells"):
                story.append(text("诊断筛选前群体：" + "; ".join(
                    f"{key}={value}" for key, value in matching["input_cells"].items()
                ), small))
            if matching.get("limitation"):
                story.append(text(f"群体选择限制：{matching['limitation']}", small))
            for warning in comparison.get("warnings") or []:
                story.append(text(f"诊断限制：{warning}", small))
        else:
            story.append(text("匹配实测状态", heading))
            story.append(text("本报告未载入可核验的匹配实测比较，不能据本报告宣称已完成实测验证。", small))

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
            story.append(text("附图群体与范围", heading))
            contexts = figure_context or []
            for index in range(len(figure_pages)):
                context = contexts[index] if index < len(contexts) else {}
                counts = context.get("population_counts", {})
                observed = counts.get("observed", 0)
                scope = ("附图包含实测细胞" if observed
                         else "附图不含实测细胞" if counts else "附图实测群体未核实")
                story.append(text(f"科研图 {index + 1}：{context.get('space', '未声明空间')} / "
                                  f"{context.get('feature_id', '未声明特征')}；{scope}。" + " / ".join(
                                      f"{key}={value}" for key, value in counts.items()), small))
            story.append(text(
                "每个点代表一个细胞的特征投影。点云形状和距离不表示细胞形态、细胞器结构或物理位置；"
                "各群体不逐细胞配对，不能解释为单个细胞的迁移轨迹。"
                "分布差异不能单独证明预测准确，代谢任务分数不等于实测通量。", small
            ))
        if font_warning:
            story.append(text(font_warning, small))

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
    trace = None
    population_counts = None
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
    # Counts come from all saved source rows, never from the requested sample size.
    if "metabolic_task_scores.csv" in outputs:
        expected = outputs["metabolic_task_scores.csv"].get("sha256")
        path = _checked(root / "metabolic_task_scores.csv", expected)
        used_sources.append((path, expected))
        population_counts = {}
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if "source" in (reader.fieldnames or []) and "score" not in (reader.fieldnames or []):
                for row in reader:
                    source = row["source"]
                    if source in {"control", "predicted", "observed"}:
                        population_counts[source] = population_counts.get(source, 0) + 1
    comparison = load_comparison(container.settings.project_root, run_id)
    figures = []
    figure_context = []
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
            figure_context.append({
                "space": space,
                "feature_id": document["feature"]["id"],
                "population_counts": {key: value["n"] for key, value in document["distributions"].items()},
            })
    content = render_report_pdf(
        summary, record, {**manifest, "manifest_sha256": manifest_sha}, comparison, figures,
        task_trace=trace, population_counts=population_counts, figure_context=figure_context,
    )
    _checked(root / "manifest.json", manifest_sha)
    for path, expected in used_sources:
        _checked(path, expected)
    return content
