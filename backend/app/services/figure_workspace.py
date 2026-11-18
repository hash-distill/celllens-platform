"""Figure recipes and deterministic exports over verified, frozen research data.

No model inference, dimensional reduction or statistical analysis occurs here.
"""

import base64
import csv
import html
import io
import json
import textwrap
import threading
import zipfile
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import uuid4

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from backend.app.core.run_manifest import manifest_hash
from backend.app.db.research_models import ResearchFigureModel
from backend.app.services.research_results import ResearchResults, sanitize

RENDER_LOCK = threading.Lock()
COLORS = {"control": "#6d8b80", "observed": "#23856a", "predicted": "#c68f42"}
GROUPS = {"control": "Measured control", "observed": "Measured treatment", "predicted": "Model prediction"}
FORMATS = {
    "svg": "image/svg+xml",
    "png": "image/png",
    "pdf": "application/pdf",
    "csv": "text/csv; charset=utf-8",
    "html": "text/html; charset=utf-8",
    "zip": "application/zip",
}


class FigureSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chart: Literal["projection", "distribution", "pathways"] = "projection"
    embedding: Literal["pca", "umap"] = "pca"
    gene: str = Field("", max_length=500)
    group: Literal["all", "control", "observed", "predicted"] = "all"
    title: str = Field("", max_length=120)
    note: str = Field("", max_length=2000)
    direction: Literal["both", "up", "down"] = "both"
    limit: int = Field(10, ge=1, le=30)


def checked_json(path):
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("图表元数据超过读取上限")
    return json.loads(path.read_text(encoding="utf-8"))


def archive_bound(path):
    with zipfile.ZipFile(path) as archive:
        if sum(entry.file_size for entry in archive.infolist()) > 1024**3:
            raise ValueError("图表数据超过单次读取上限")


def saved_document(row):
    created = row.created_at
    if created.tzinfo is None:  # SQLite drops the UTC offset from DateTime(timezone=True).
        created = created.replace(tzinfo=UTC)
    return {
        "id": row.id,
        "spec": row.spec_json,
        "created_at": created.isoformat(),
        "manifest_sha256": row.manifest_sha256,
        "figure_source_sha256": row.figure_source_sha256,
    }


def validate_expression_metadata(metadata, kind):
    genes, cells = metadata.get("genes"), metadata.get("cells")
    if (
        not isinstance(genes, list)
        or not 0 < len(genes) <= 60000
        or any(not isinstance(gene, str) or not gene or len(gene) > 500 for gene in genes)
        or len(set(genes)) != len(genes)
    ):
        raise ValueError("表达图表基因标识无效、重复或超过读取上限")
    if not isinstance(cells, list) or not 0 < len(cells) <= 100000:
        raise ValueError("表达图表细胞数无效或超过读取上限")
    allowed = {"control", "observed"} if kind == "measured" else set(COLORS)
    identities = set()
    for cell in cells:
        if (
            not isinstance(cell, dict)
            or cell.get("source") not in allowed
            or not isinstance(cell.get("cell_id"), str)
            or not cell["cell_id"]
        ):
            raise ValueError("表达图表细胞身份或群体来源未知")
        identity = (cell["source"], cell["cell_id"])
        if identity in identities:
            raise ValueError("表达图表细胞身份重复")
        identities.add(identity)
    if metadata.get("units") != "log1p(CP10K)":
        raise ValueError("表达图表单位未知或不受支持")
    return metadata


class FigureWorkspace:
    def __init__(self, container):
        self.container = container
        self.results = ResearchResults(container)
        self.sessions = container.store.session_factory

    def source(self, kind, identifier):
        result, directory, summary, manifest = self.results.source(kind, identifier)
        if result["state"] != "completed" or directory is None:
            raise ValueError("图表工作区仅接受已完成并通过来源校验的结果")
        return result, directory, summary, manifest

    def expression_metadata(self, kind, identifier, directory):
        if kind == "measured":
            path = directory / "expression_preview.json"
            if not path.exists() or not (directory / "expression_preview.npz").exists():
                return None, None
            metadata = checked_json(path)
            if metadata.get("schema") != "celllens-expression-preview-v1":
                raise ValueError("不支持的表达图表数据版本")
            return validate_expression_metadata(metadata, kind), directory / "expression_preview.npz"
        from backend.app.services.cell_state import frozen_inputs
        from backend.app.services.cell_state_preparation import prepared_manifest

        # Missing historical artifacts stay unavailable. A present or registered
        # bundle must pass all existing hash checks, with no reconstruction.
        registered = [
            artifact
            for artifact in self.container.store.artifacts(identifier)
            if getattr(artifact, "kind", None) == "cell_state_preparation"
        ]
        if not registered and not (directory / "cell_state").exists():
            return None, None
        bundle = prepared_manifest(self.container, frozen_inputs(self.container, identifier))
        if bundle is None:
            return None, None
        path = bundle[0] / "plot_data.npz"
        archive_bound(path)
        with np.load(path, allow_pickle=False) as archive:
            original = json.loads(str(archive["metadata"].item()))
        metadata = {
            "genes": original["genes"],
            "units": "log1p(CP10K)",
            "cells": [
                {"cell_id": cell, "source": group}
                for cell, group in zip(original["ids"], original["sources"], strict=True)
            ],
        }
        return validate_expression_metadata(metadata, kind), path

    def context(self, kind, identifier):
        result, directory, summary, _ = self.source(kind, identifier)
        metadata, _ = self.expression_metadata(kind, identifier, directory)
        genes = metadata["genes"] if metadata else []
        if not genes:
            path = directory / ("genes.csv" if kind == "measured" else "gene_deltas.csv")
            if path.exists():
                genes = pd.read_csv(path, usecols=cast(Any, [0])).iloc[:, 0].astype(str).tolist()
        available = {
            "projection": bool(result["availability"]["projection"]["available"]),
            "distribution": bool(metadata),
            # Only measured manifests currently register and verify ORA output.
            # A stray file in a historical prediction directory is not evidence.
            "pathways": kind == "measured" and (directory / "pathways.json").is_file(),
        }
        reasons = {
            "distribution": "此历史结果未保存逐细胞表达；保留原结果，可重新分析生成新版本。",
            "pathways": "此结果没有冻结的通路富集产物。新建实测分析可生成适用的通路结果。",
            "projection": "此结果未保存可用的二维表达投影。",
        }
        if kind != "measured":
            reasons["pathways"] = "预测结果尚未接入经登记的通路分析，当前不提供通路图。"
        if available["pathways"]:
            pathways = checked_json(directory / "pathways.json")
            available["pathways"] = bool(pathways.get("results"))
            if not available["pathways"]:
                reasons["pathways"] = "本次未生成可检验的通路结果：" + str(
                    pathways.get("status", "unavailable")
                )
        return {
            "result": sanitize(result),
            "genes": genes,
            "availability": available,
            "reasons": reasons,
            "pathways": summary.get("pathways"),
        }

    def payload(self, kind, identifier, spec):
        result, directory, _, _ = self.source(kind, identifier)
        payload: dict[str, Any] = {
            "schema": "celllens-figure-v1",
            "record_kind": kind,
            "record_id": identifier,
            "result": sanitize(result),
            "spec": spec.model_dump(),
            "rows": [],
            "limitations": list(result.get("limitations", [])),
        }
        if spec.chart == "projection":
            projection = cast(dict[str, Any], self.results.projection(kind, identifier, spec.embedding))
            if not projection.get("available"):
                raise ValueError(projection.get("reason") or "所选投影尚未保存")
            payload["rows"] = [
                dict(point)
                for point in projection["points"]
                if spec.group == "all" or point["source"] == spec.group
            ]
            payload["method"] = projection["method"]
            payload["units"] = "expression embedding coordinates"
            payload["limitations"].append("二维坐标为表达降维，不表示真实细胞空间位置或动态轨迹。")
        elif spec.chart == "distribution":
            metadata, path = self.expression_metadata(kind, identifier, directory)
            if metadata is None or path is None:
                raise ValueError("此结果没有冻结的逐细胞表达，不能绘制分布")
            if spec.gene not in metadata["genes"]:
                raise ValueError("请选择本次分析面板内的基因")
            index = metadata["genes"].index(spec.gene)
            archive_bound(path)
            if kind == "measured":
                from scipy.sparse import load_npz

                matrix = load_npz(path)
                if matrix.shape != (len(metadata["cells"]), len(metadata["genes"])):
                    raise ValueError("表达矩阵与逐细胞身份不一致")
                values = matrix[:, index].toarray().ravel()
            else:
                values = np.full(len(metadata["cells"]), np.nan)
                with np.load(path, allow_pickle=False) as archive:
                    for group in COLORS:
                        positions = [i for i, cell in enumerate(metadata["cells"]) if cell["source"] == group]
                        if positions:
                            matrix = archive[f"expression_{group}"]
                            if matrix.shape != (len(positions), len(metadata["genes"])):
                                raise ValueError("预测表达矩阵与逐细胞身份不一致")
                            values[positions] = matrix[:, index]
            if not np.isfinite(values).all():
                raise ValueError("表达数据包含非有限值")
            payload["rows"] = [
                {**cell, "gene": spec.gene, "value": float(value)}
                for cell, value in zip(metadata["cells"], values, strict=True)
                if spec.group == "all" or cell["source"] == spec.group
            ]
            payload["units"] = metadata["units"]
            payload["limitations"].append("展示本次分析实际纳入的细胞；细胞数量不等于独立生物学重复数。")
        else:
            if kind != "measured":
                raise ValueError("预测结果尚未接入经登记的通路分析，当前不提供通路图")
            if not (directory / "pathways.json").exists():
                raise ValueError("此结果没有冻结的通路分析")
            document = checked_json(directory / "pathways.json")
            rows = [
                row
                for row in document.get("results", [])
                if row["hit_count"] > 0 and (spec.direction == "both" or row["direction"] == spec.direction)
            ]
            rows.sort(key=lambda row: (row["fdr"], row["p_value"], row["direction"], row["pathway_id"]))
            payload["rows"] = rows[: spec.limit]
            payload["pathway_analysis"] = {key: value for key, value in document.items() if key != "results"}
            payload["units"] = "-log10(global BH FDR); point size = candidate hits"
            payload["limitations"].append(
                "基于表达变化排序的探索性 ORA；FDR 为通路富集校正，不是处理效应的差异表达显著性。"
            )
        if not payload["rows"]:
            raise ValueError("所选条件没有可绘制的数据；请更换分组、方向或图表")
        payload["limitations"] = list(dict.fromkeys(payload["limitations"]))
        payload["figure_source_sha256"] = manifest_hash(
            {
                "rows": payload["rows"],
                "provenance": payload["result"]["provenance"],
                "method": payload.get("method"),
                "units": payload["units"],
                "pathway_analysis": payload.get("pathway_analysis"),
            }
        )
        return payload

    def save(self, kind, identifier, spec):
        payload = self.payload(kind, identifier, spec)
        with self.sessions.begin() as session:
            count = session.scalar(
                select(func.count())
                .select_from(ResearchFigureModel)
                .where(ResearchFigureModel.record_kind == kind, ResearchFigureModel.record_id == identifier)
            )
            if count >= 100:
                raise ValueError("每份结果最多保存 100 幅图表，请先导出或整理现有图表")
            row = ResearchFigureModel(
                id="figure_" + uuid4().hex[:24],
                record_kind=kind,
                record_id=identifier,
                manifest_sha256=payload["result"]["provenance"]["manifest_sha256"],
                figure_source_sha256=payload["figure_source_sha256"],
                spec_json=spec.model_dump(),
                created_at=datetime.now(UTC),
            )
            session.add(row)
            return saved_document(row)

    def saved(self, kind, identifier):
        self.source(kind, identifier)
        with self.sessions() as session:
            rows = session.scalars(
                select(ResearchFigureModel)
                .where(ResearchFigureModel.record_kind == kind, ResearchFigureModel.record_id == identifier)
                .order_by(ResearchFigureModel.created_at.desc())
                .limit(100)
            ).all()
            return {"items": [saved_document(row) for row in rows], "total": len(rows)}

    def saved_payload(self, kind, identifier, figure_id):
        with self.sessions() as session:
            row = session.get(ResearchFigureModel, figure_id)
            if row is None or row.record_kind != kind or row.record_id != identifier:
                raise KeyError(figure_id)
            spec = FigureSpec.model_validate(row.spec_json)
            fingerprint = row.manifest_sha256
            figure_fingerprint = row.figure_source_sha256
        payload = self.payload(kind, identifier, spec)
        if payload["result"]["provenance"]["manifest_sha256"] != fingerprint:
            raise ValueError("结果指纹已改变，无法将旧图表配方用于当前数据")
        if payload["figure_source_sha256"] != figure_fingerprint:
            raise ValueError("图表数据指纹已改变，无法导出原已保存图表")
        return payload

    def remove(self, kind, identifier, figure_id) -> None:
        """Remove one annotation recipe; immutable analysis artifacts are untouched."""
        self.source(kind, identifier)
        with self.sessions.begin() as session:
            row = session.get(ResearchFigureModel, figure_id)
            if row is None or row.record_kind != kind or row.record_id != identifier:
                raise KeyError(figure_id)
            session.delete(row)


def csv_bytes(payload):
    rows = payload["rows"]
    columns = list(dict.fromkeys(key for row in rows for key in row))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        cleaned = {}
        for key, value in row.items():
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                value = "'" + value
            cleaned[key] = value
        writer.writerow(cleaned)
    return stream.getvalue().encode("utf-8-sig")


def figure_bytes(payload, format):
    from matplotlib import rc_context
    from matplotlib.figure import Figure
    from matplotlib.font_manager import FontProperties, findfont

    spec = FigureSpec.model_validate(payload["spec"])
    rows = payload["rows"]
    with (
        RENDER_LOCK,
        rc_context(
            {
                "svg.hashsalt": "celllens-figure-v1",
                "pdf.fonttype": 42,
                "axes.unicode_minus": False,
                "text.parse_math": False,
            }
        ),
    ):
        family = next(
            (
                name
                for name in ("Microsoft YaHei", "Noto Sans CJK SC", "SimHei")
                if _font_exists(findfont, FontProperties, name)
            ),
            "DejaVu Sans",
        )
        font = FontProperties(family=family)
        note_lines = textwrap.wrap(" ".join(spec.note.split()), 90)
        footer_height = 0.9 + 0.13 * max(0, len(note_lines) - 3)
        plot_height = max(5.3, 2.0 + len(rows) * 0.3) if spec.chart == "pathways" else 5.3
        figure_height = plot_height + footer_height
        figure = Figure(
            figsize=(10, figure_height),
            facecolor="white",
        )
        axes = figure.add_subplot(111)
        axes.set_facecolor("#f8fbf8")
        if spec.chart == "projection":
            for group, color in COLORS.items():
                selected = [row for row in rows if row["source"] == group]
                if selected:
                    axes.scatter(
                        [row["x"] for row in selected],
                        [row["y"] for row in selected],
                        s=9,
                        alpha=0.65,
                        color=color,
                        linewidths=0,
                        label=f"{GROUPS[group]} (n={len(selected)})",
                        rasterized=False,
                    )
            axes.set_xlabel(f"{spec.embedding.upper()} 1")
            axes.set_ylabel(f"{spec.embedding.upper()} 2")
            axes.legend(frameon=False, fontsize=9)
        elif spec.chart == "distribution":
            groups = [group for group in COLORS if any(row["source"] == group for row in rows)]
            values = [[row["value"] for row in rows if row["source"] == group] for group in groups]
            boxes = axes.boxplot(values, patch_artist=True, showfliers=False, widths=0.45)
            rng = np.random.default_rng(42)
            for i, (group, series) in enumerate(zip(groups, values, strict=True)):
                boxes["boxes"][i].set_facecolor(COLORS[group])
                boxes["boxes"][i].set_alpha(0.35)
                axes.scatter(
                    i + 1 + rng.uniform(-0.17, 0.17, len(series)),
                    series,
                    s=5,
                    alpha=0.25,
                    color=COLORS[group],
                    linewidths=0,
                )
            axes.set_xticks(
                range(1, len(groups) + 1),
                [f"{GROUPS[group]}\n(n={len(series)})" for group, series in zip(groups, values, strict=True)],
            )
            axes.set_ylabel(payload["units"])
            axes.set_xlabel(spec.gene)
        else:
            for i, row in enumerate(rows):
                axes.scatter(
                    -np.log10(max(float(row["fdr"]), 1e-300)),
                    i,
                    s=25 + 9 * np.sqrt(row["hit_count"]),
                    color="#23856a" if row["direction"] == "up" else "#b88850",
                )
            axes.set_yticks(
                range(len(rows)),
                ["\n".join(textwrap.wrap(f"{row['pathway_name']} [{row['direction']}]", 50)) for row in rows],
                fontsize=8,
            )
            axes.invert_yaxis()
            axes.set_xlabel("−log10(global BH FDR) · size: candidate hits")
            axes.axvline(-np.log10(0.05), color="#99aaa1", linestyle="--", linewidth=0.8)
        default_title = {
            "projection": "Cell expression landscape",
            "distribution": f"{spec.gene} · expression distribution",
            "pathways": "Reactome · exploratory pathway enrichment",
        }[spec.chart]
        axes.set_title(
            "\n".join(textwrap.wrap(spec.title.strip() or default_title, 45)),
            loc="left",
            pad=20,
            fontproperties=font,
            fontsize=14,
            parse_math=False,
        )
        axes.spines[["top", "right"]].set_visible(False)
        axes.grid(axis="y", alpha=0.12)
        axes.set_axisbelow(True)
        footer = f"{payload['record_id']}  |  {payload['result']['provenance']['manifest_sha256'][:12]}\n"
        footer += "Descriptive / exploratory analysis. See accompanying data and provenance."
        if spec.note:
            footer += "\n" + "\n".join(note_lines)
        figure.text(0.04, 0.025, footer, fontsize=7, color="#5f766c", fontproperties=font, parse_math=False)
        figure.tight_layout(rect=(0, footer_height / figure_height, 1, 1))
        output = io.BytesIO()
        figure.savefig(
            output,
            format=format,
            dpi=180,
            facecolor="white",
            metadata={"Date": None}
            if format == "svg"
            else {"CreationDate": None}
            if format == "pdf"
            else None,
        )
        figure.clear()
        return output.getvalue()


def _font_exists(findfont, font_properties, family):
    try:
        findfont(font_properties(family=family), fallback_to_default=False)
        return True
    except ValueError:
        return False


def html_bytes(payload, svg, data):
    escape = html.escape
    spec = payload["spec"]
    limitations = "".join(f"<li>{escape(str(item))}</li>" for item in payload["limitations"])
    encoded_svg = base64.b64encode(svg).decode()
    encoded_csv = base64.b64encode(data).decode()
    recipe = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    encoded_json = base64.b64encode(recipe.encode()).decode()
    return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(spec["title"] or "CellLens 研究图表")}</title><style>
body{{font:15px system-ui;max-width:1080px;margin:40px auto;padding:24px;background:#edf4ee;color:#234e42}}
main{{background:white;padding:30px;border-radius:16px}}img{{width:100%}}p,li{{line-height:1.8}}
a{{color:#208268;margin-right:20px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}}
</style><main>
<p>CELLLENS / RESEARCH FIGURE</p><h1>{escape(spec["title"] or "研究图表")}</h1><p>{escape(spec["note"])}</p>
<img alt="研究图表" src="data:image/svg+xml;base64,{encoded_svg}"><p>
<a download="figure-data.csv" href="data:text/csv;base64,{encoded_csv}">下载图中数据 CSV</a>
<a download="figure-recipe.json" href="data:application/json;base64,{encoded_json}">下载图表配方与来源</a></p>
<h2>解读边界</h2><ul>{limitations}</ul><details><summary>数据、参数与结果指纹</summary>
<pre>{escape(recipe)}</pre></details></main></html>""".encode()


def export_payload(payload, format):
    if format not in FORMATS:
        raise ValueError("不支持的导出格式")
    if format in {"svg", "png", "pdf"}:
        return figure_bytes(payload, format)
    data = csv_bytes(payload)
    if format == "csv":
        return data
    svg = figure_bytes(payload, "svg")
    report = html_bytes(payload, svg, data)
    if format == "html":
        return report
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("index.html", report)
        archive.writestr("figure.svg", svg)
        archive.writestr("figure.png", figure_bytes(payload, "png"))
        archive.writestr("figure.pdf", figure_bytes(payload, "pdf"))
        archive.writestr("figure-data.csv", data)
        archive.writestr(
            "figure-recipe.json", json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
        )
        archive.writestr(
            "README.txt",
            "Open index.html offline. CSV contains exactly the displayed cells/pathways.\n"
            "Recipe records figure settings, immutable result fingerprint and interpretation limits.\n"
            "Figures are descriptive/exploratory; predictions remain distinct from measurements.\n",
        )
    return output.getvalue()


def export_report(container, kind: str, identifier: str, format: Literal["html", "zip"]) -> bytes:
    """Export all saved recipes as one offline report, without modifying sources."""
    if format not in {"html", "zip"}:
        raise ValueError("研究报告仅支持 HTML 或 ZIP")
    workspace = FigureWorkspace(container)
    saved = workspace.saved(kind, identifier)["items"]
    if not saved:
        raise ValueError("尚未保存图表，请先将图表加入清单")
    if len(saved) > 20:
        raise ValueError("单份研究报告最多包含 20 幅已保存图表；当前清单超过上限，未截断导出")
    # Verify every recipe before rendering anything. Each check binds the original
    # result manifest and the actual plotted-data fingerprint independently.
    payloads = [workspace.saved_payload(kind, identifier, row["id"]) for row in saved]
    fingerprints = {payload["result"]["provenance"]["manifest_sha256"] for payload in payloads}
    if len(fingerprints) != 1:
        raise ValueError("图表来源版本不一致，不能合并为同一研究报告")
    limitations = list(dict.fromkeys(note for payload in payloads for note in payload["limitations"]))
    report_manifest = {
        "schema": "celllens-figure-report-v1",
        "record_kind": kind,
        "record_id": identifier,
        "figure_count": len(saved),
        "result": payloads[0]["result"],
        "limitations": limitations,
        "figures": [{"number": number, **row} for number, row in enumerate(saved, 1)],
        "scope": "All saved figures in saved-list order; each CSV contains exactly its displayed rows",
    }
    manifest_data = json.dumps(report_manifest, ensure_ascii=False, indent=2, allow_nan=False).encode()
    max_bytes = 64 * 1024 * 1024
    total_bytes = len(manifest_data)
    artifacts: dict[str, bytes] = {}
    sections = []

    def data_uri(media: str, content: bytes) -> str:
        return f"data:{media};base64," + base64.b64encode(content).decode("ascii")

    for number, (row, payload) in enumerate(zip(saved, payloads, strict=True), 1):
        prefix = f"figures/{number:02d}"
        svg, data = figure_bytes(payload, "svg"), csv_bytes(payload)
        recipe = json.dumps(
            {**payload, "saved_figure": row}, ensure_ascii=False, indent=2, allow_nan=False
        ).encode()
        total_bytes += len(svg) + len(data) + len(recipe)
        if total_bytes > max_bytes:
            raise ValueError("研究报告超过 64 MiB 导出上限，请改用单图导出")
        artifacts.update({prefix + ".svg": svg, prefix + ".csv": data, prefix + ".json": recipe})
        title = (
            payload["spec"]["title"].strip()
            or {
                "projection": "表达投影",
                "distribution": payload["spec"]["gene"] + " 表达分布",
                "pathways": "探索性通路富集",
            }[payload["spec"]["chart"]]
        )
        sections.append(
            f'<section id="figure-{number}"><h2>{number}. {html.escape(title)}</h2>'
            f'<p class="note">{html.escape(payload["spec"]["note"])}</p>'
            f'<img alt="{html.escape(title, quote=True)}" src="{data_uri("image/svg+xml", svg)}">'
            f'<p><a download="{number:02d}.svg" href="{data_uri("image/svg+xml", svg)}">图表 SVG</a>'
            f'<a download="{number:02d}.csv" href="{data_uri("text/csv", data)}">图中数据 CSV</a>'
            f'<a download="{number:02d}.json" href="{data_uri("application/json", recipe)}">'
            '配方与来源 JSON</a></p><p class="fingerprint">图表数据指纹：'
            f"{html.escape(payload['figure_source_sha256'])}</p></section>"
        )
    manifest_uri = data_uri("application/json", manifest_data)
    limits_html = "".join(f"<li>{html.escape(str(note))}</li>" for note in limitations)
    overview = html.escape(
        json.dumps(report_manifest["result"], ensure_ascii=False, indent=2, allow_nan=False)
    )
    document = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>CellLens 研究报告</title>
<style>body{{font:15px system-ui;max-width:1080px;margin:36px auto;padding:20px;
color:#234e42;background:#edf4ee}}
main,section{{background:white;padding:28px;margin-bottom:24px;border-radius:14px}}img{{width:100%}}
p,li{{line-height:1.8}}a{{color:#208268;margin-right:20px}}.note,pre{{white-space:pre-wrap;overflow-wrap:anywhere}}
pre,.fingerprint{{font-size:11px;overflow-wrap:anywhere}}section{{break-inside:avoid}}</style></head><body>
<main><p>CELLLENS / RESEARCH REPORT</p><h1>研究图表报告</h1>
<p>研究记录：{html.escape(kind)} / {html.escape(identifier)}；已保存图表：{len(saved)} 幅。</p>
<p>完整保留当前图表清单；每份 CSV 与对应图中的群体、基因、通路及排序一致。</p>
<h2>研究范围与解读边界</h2><ul>{limits_html}</ul>
<p><a download="report-manifest.json" href="{manifest_uri}">报告来源与图表清单 JSON</a></p>
<details><summary>研究概览、来源与结果指纹</summary><pre>{overview}</pre></details></main>
{"".join(sections)}</body></html>'''.encode()
    if len(document) > max_bytes:
        raise ValueError("自包含研究报告超过 64 MiB 导出上限，请改用单图导出")
    if format == "html":
        return document
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("index.html", document)
        archive.writestr("report-manifest.json", manifest_data)
        for name, content in artifacts.items():
            archive.writestr(name, content)
        archive.writestr(
            "README.txt",
            "Open index.html offline. All saved figures are included in saved-list order.\n"
            "Each numbered CSV matches that figure's displayed rows. JSON retains full notes, "
            "source provenance and both result/figure fingerprints.\n"
            "SVG, PNG and PDF for individual figures remain available from the workspace.\n",
        )
    return output.getvalue()
