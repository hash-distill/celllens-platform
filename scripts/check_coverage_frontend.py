"""Read-only methods/data navigation, gene panels and metabolic coverage acceptance."""

import argparse
import copy
import csv
import io
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default="reports/methods-data")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    errors, writes, checks = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        page.set_default_timeout(30_000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request",
            lambda request: writes.append(request.url) if request.method not in ("GET", "HEAD") else None,
        )
        before = page.request.get(base + "/api/v1/experiments").json()["total"]
        page.goto(base, wait_until="networkidle")
        expect(page.locator(".coverage-entry")).to_have_count(0)
        expect(page.locator(".header-nav").get_by_role("link", name="方法数据", exact=True)).to_be_visible()
        page.get_by_role("link", name="了解方法与数据", exact=True).click()
        expect(page).to_have_url(re.compile(r"/methods/models$"))
        expect(page.get_by_role("heading", name="方法数据", exact=True)).to_be_visible()
        expect(page.locator(".method-figure-image")).to_have_count(2)
        expect(page.locator(".method-section")).to_contain_text(["STATE", "scCellFie"])
        for index, figure in enumerate(page.locator(".method-diagram").all()):
            svg = figure.locator(".method-figure-image")
            svg.scroll_into_view_if_needed()
            expect(svg).to_be_visible()
            expect(svg).to_have_attribute("viewBox", "0 0 1440 730")
            assert svg.evaluate("node=>node.namespaceURI") == "http://www.w3.org/2000/svg"
            assert svg.locator("text").count() > 30
            expect(svg.locator("image")).to_have_count(0)
            preview = figure.get_by_role("button", name=re.compile("放大查看"))
            preview.click()
            modal = figure.get_by_role("dialog")
            expect(modal).to_be_visible()
            expect(modal.locator("svg title")).to_have_text(svg.locator("title").text_content() or "")
            ids = page.locator(".method-diagram svg [id]").evaluate_all("nodes=>nodes.map(n=>n.id)")
            assert len(ids) == len(set(ids)), "SVG marker/title IDs must be unique across preview and dialog"
            page.screenshot(path=str(output / f"architecture-expanded-{index}.png"))
            page.keyboard.press("Escape")
            expect(modal).not_to_be_visible()
            expect(preview).to_be_focused()
            preview.click()
            modal.get_by_role("button", name="关闭架构图", exact=True).click()
            expect(modal).not_to_be_visible()
            with page.expect_download() as figure_download:
                figure.get_by_role("button", name="下载 SVG 架构图 ↓", exact=True).click()
            content = Path(figure_download.value.path()).read_bytes()
            root = ET.fromstring(content)
            namespace = {"svg": "http://www.w3.org/2000/svg"}
            assert root.tag == "{http://www.w3.org/2000/svg}svg"
            assert len(root.findall(".//svg:text", namespace)) > 30
            assert root.find(".//svg:style", namespace) is not None
            assert not root.findall(".//svg:image", namespace)
            figure_download.value.save_as(output / figure_download.value.suggested_filename)
            assert figure_download.value.suggested_filename.startswith("CellLens-")
            assert figure_download.value.suggested_filename.endswith(".svg")
        resources = page.evaluate("() => performance.getEntriesByType('resource').map(e=>e.name)")
        assert not any("/api/v1/coverage" in name or "/catalog/data-summary" in name for name in resources)
        page.reload(wait_until="networkidle")
        expect(page.locator(".model-methods")).to_be_visible()
        page.screenshot(path=str(output / "model-methods.png"), full_page=True)
        checks.append(
            "Homepage CTA, two native vector architectures, unique SVG IDs, keyboard/dialog/SVG-download "
            "interactions and direct model-page refresh"
        )

        page.locator(".methods-nav").get_by_role("link", name="细胞背景", exact=True).click()
        expect(page).to_have_url(re.compile(r"/methods/backgrounds$"))
        expect(page.locator(".data-overview")).to_be_visible()
        expect(page.locator(".coverage-page")).to_have_count(0)
        summary = page.request.get(base + "/api/v1/catalog/data-summary").json()["contexts"]
        expect(page.locator(".background-choice")).to_have_count(len(summary))
        expect(page.locator(".methods-nav a")).to_have_text(["01模型方法", "02细胞背景", "03覆盖范围"])
        expression = page.locator(".expression-explorer")
        expression.locator("summary").click()
        first_context = next(row for row in summary if row["cell_line"] == summary[0]["cell_line"])
        selected_gene = first_context["expression_genes"][0]
        page.get_by_label("搜索表达基因", exact=True).fill(selected_gene)
        expect(page.locator(".expression-genes span").get_by_text(selected_gene, exact=True)).to_be_visible()
        with page.expect_download() as download:
            page.get_by_role("button", name="下载表达面板", exact=True).click()
        rows = list(csv.reader(io.StringIO(Path(download.value.path()).read_text(encoding="utf-8-sig"))))
        assert rows[0] == ["gene"] and [row[0] for row in rows[1:]] == first_context["expression_genes"]
        expression.locator("summary").click()
        checks.append("Live registry counts, expression/target distinction and complete expression-panel CSV")

        for row in summary:
            page.locator(".background-choice").filter(has_text=re.compile("^" + row["cell_line"])).click()
            expect(page.locator(".background-choice.selected")).to_contain_text(row["cell_line"])
            biography = page.locator(".background-biography")
            if not biography.evaluate("node=>node.open"):
                biography.locator("summary").click()
            card = biography.get_by_role("article", name=row["cell_line"] + " 细胞背景介绍", exact=True)
            expect(card).to_be_visible()
            expect(card.locator("section p[lang=en]")).to_have_count(3)
            expect(card.get_by_role("link", name=re.compile("Cellosaurus"))).to_be_visible()
        checks.append(
            "All registered cell backgrounds: selected state, biology, bilingual detail and sources"
        )
        page.screenshot(path=str(output / "cell-backgrounds.png"), full_page=True)
        with page.expect_response(
            lambda response: "/api/v1/coverage" in response.url, timeout=120_000
        ) as pending:
            page.locator(".methods-nav").get_by_role("link", name="覆盖范围", exact=True).click()
        assert pending.value.status == 200
        document = pending.value.json()
        expect(page.locator(".coverage-loading")).to_have_count(0, timeout=120_000)
        summary = page.request.get(base + "/api/v1/catalog/data-summary").json()["contexts"]
        genes = [row for row in document["genes"] if row["in_panel"]]
        assert all(re.search(r"[\u4e00-\u9fff]", row.get("name_zh") or "") for row in genes)
        for task in document["tasks"]:
            assert task.get("guide"), task["id"]
            assert re.search(r"[\u4e00-\u9fff]", task["guide"]["name_zh"]), task["id"]
            assert task["guide"]["name_zh"] != task["guide"]["name_en"]
            assert re.search(r"[\u4e00-\u9fff]", task["guide"]["description_zh"]), task["id"]
        tasks = [row for row in document["tasks"] if row["coverage_status"] == "full"]
        available = [row for row in document["tasks"] if row["n_present_all"] > 0
                     and row["coverage_status"] in ("full", "partial")]
        reactions = [row for row in document["reactions"] if row["n_genes_all"] and not row["n_missing_all"]]
        metric_text = page.locator(".coverage-metrics strong").all_text_contents()
        normalized = [re.sub(r"[\s,]+", "", text) for text in metric_text]
        assert normalized == [
            str(document["panel_gene_count"]),
            str(len(genes)),
            str(len(available)),
            str(len(reactions)),
        ]
        expect(page.locator(".data-overview")).to_have_count(0)
        hashes = {row["panel_sha256"] for row in document["models"]}
        if len(hashes) == 1 and None not in hashes:
            expect(page.locator(".coverage-context select")).to_have_count(0)
            expect(page.locator(".coverage-page > .page-heading")).to_have_count(1)
            expect(page.locator(".coverage-context h2")).to_have_text("模型覆盖范围")
            expect(page.locator(".coverage-page > section.coverage-context")).to_have_count(0)
            for model in document["models"]:
                expect(page.locator(".shared-backgrounds")).to_contain_text(model["cell_line"])
            expect(page.locator(".shared-panel-note")).to_have_count(0)
        page.screenshot(path=str(output / "shared-coverage.png"), full_page=True)
        checks.append("Verified identical panels share one coverage view with no redundant cell selector")
        page.get_by_label("搜索基因", exact=True).fill("NO_MATCH_GENE_FIXTURE")
        expect(page.locator(".catalogue-list tbody tr")).to_have_count(0)
        page.get_by_label("搜索基因", exact=True).fill(genes[0]["name_zh"])
        page.get_by_role("button", name=genes[0]["symbol"], exact=True).click()
        expect(page.get_by_role("complementary", name="基因范围详情")).to_contain_text(genes[0]["symbol"])
        expect(page.get_by_role("complementary", name="基因范围详情").locator(".gene-name-zh")).to_have_text(
            genes[0]["name_zh"]
        )
        with page.expect_download() as bilingual_download:
            page.get_by_role("button", name="下载已覆盖基因", exact=True).click()
        translated_rows = list(csv.DictReader(io.StringIO(
            Path(bilingual_download.value.path()).read_text(encoding="utf-8-sig")
        )))
        assert len(translated_rows) == len(genes)
        assert all(row["name_zh"] and row["name_en"] for row in translated_rows)
        checks.append(
            "Every frozen task and visible metabolic gene is bilingual, with Chinese search and CSV"
        )
        page.locator(".coverage-tabs").get_by_role("button", name=re.compile("代谢任务介绍")).click()
        expect(page.get_by_label("任务覆盖范围", exact=True)).to_have_value("covered")
        expect(page.get_by_label("任务覆盖范围", exact=True).locator("option")).to_have_count(3)
        expect(page.locator(".catalogue-count")).to_contain_text(str(len(available)))
        expect(page.locator(".task-guide-card")).to_have_count(min(20, len(available)))
        expect(page.locator(".task-dot")).to_have_count(len(available))
        # Select a task outside the first list page: the chart must synchronise pagination.
        last_task = available[-1]
        dot_label = (last_task["guide"]["name_zh"] if last_task.get("guide") else last_task["label"])
        dot_label += f'：已覆盖 {last_task["n_present_all"]} / {last_task["n_genes_all"]} 个关联基因'
        page.get_by_role("button", name=dot_label, exact=True).click()
        expect(page.locator(".task-guide-card.chosen")).to_have_count(1)
        expect(page.locator(".task-dot.selected")).to_have_attribute("aria-label", dot_label)
        expect(page.get_by_role("complementary", name="任务范围详情")).to_contain_text(
            last_task["guide"]["name_zh"] if last_task.get("guide") else last_task["label"]
        )
        partial = [row for row in document["tasks"] if row["coverage_status"] == "partial"]
        if partial:
            page.get_by_label("任务覆盖范围", exact=True).select_option("partial")
            expect(page.locator(".catalogue-count")).to_contain_text(str(len(partial)))
            expect(page.get_by_role("complementary", name="任务范围详情")).to_contain_text("缺失")
            page.locator(".task-guide-card").first.click()
            expect(page.get_by_role("complementary", name="任务范围详情")).to_contain_text("缺失")
        page.get_by_label("任务覆盖范围", exact=True).select_option("full")
        expect(page.locator(".task-guide-card")).to_have_count(min(20, len(tasks)))
        expect(page.locator(".task-dot")).to_have_count(len(tasks))
        page.get_by_label("任务覆盖范围", exact=True).select_option("covered")
        absent = next((row for row in document["tasks"] if not row["n_present_all"]), None)
        if absent:
            page.get_by_label("搜索任务", exact=True).fill(absent["id"])
            assert absent["id"] not in [row.get_attribute("title") for row in page.locator(".task-dot").all()]
            for card in page.locator(".task-guide-card").all():
                assert card.locator(".task-guide-title").inner_text() != absent["label"]
            page.get_by_label("搜索任务", exact=True).fill("")
        page.screenshot(path=str(output / "task-coverage-overview.png"), full_page=True)
        checks.append("Only full/partial tasks, actual-coverage dot chart and linked detail pagination")

        # Response fixture exercises future mixed-panel presentation without touching real assets.
        mixed = copy.deepcopy(document)
        for index, model in enumerate(mixed["models"]):
            model["panel_sha256"] = "a" * 64 if index < 2 else "b" * 64
        mixed["models"][-1]["panel_sha256"] = None
        page.route(
            "**/api/v1/coverage*",
            lambda route: route.fulfill(status=200, json=mixed),
        )
        page.reload(wait_until="networkidle")
        selector = page.get_by_label("覆盖目录基因面板", exact=True)
        expect(selector.locator("option")).to_have_count(3)
        expect(selector.locator("option").first).to_contain_text(mixed["models"][1]["cell_line"])
        expect(selector.locator("option").last).to_contain_text("暂不可用")
        page.unroute("**/api/v1/coverage*")
        checks.append("Response fixture: different or unverified panels remain separate groups")

        legacy_query = urlencode({"cell_line": document["source"]["cell_line"], "task": tasks[0]["id"]})
        page.goto(base + "/coverage?" + legacy_query, wait_until="networkidle")
        expect(page).to_have_url(re.compile(r"/methods/coverage\?"))
        expect(page.locator(".catalogue-detail h2")).to_have_text(tasks[0]["guide"]["name_zh"])
        page.reload(wait_until="networkidle")
        expect(page.locator(".coverage-page")).to_be_visible()
        checks.append("Legacy coverage query/task links and direct data-page refresh")
        page.route(
            "**/api/v1/coverage*",
            lambda route: route.fulfill(
                status=503,
                content_type="application/json",
                body=json.dumps({"detail": {"message": "测试覆盖暂不可用"}}),
            ),
        )
        page.reload(wait_until="networkidle")
        expect(page.get_by_role("alert")).to_contain_text("测试覆盖暂不可用")
        expect(page.locator(".methods-nav")).to_be_visible()
        page.unroute("**/api/v1/coverage*")
        page.get_by_role("button", name="重试", exact=True).click()
        expect(page.locator(".coverage-metrics")).to_be_visible(timeout=120_000)
        checks.append("Coverage failure preserves navigation and supports retry")
        page.goto(base + "/methods/data?cell_line=HepG2", wait_until="networkidle")
        expect(page).to_have_url(re.compile(r"/methods/backgrounds\?cell_line=HepG2$"))
        expect(page.locator(".background-choice.selected")).to_contain_text("HepG2")
        page.reload(wait_until="networkidle")
        expect(page.locator(".data-overview")).to_be_visible()
        checks.append("Old data bookmarks preserve background selection and direct refresh")
        assert page.request.get(base + "/api/v1/experiments").json()["total"] == before
        assert not errors and not writes, (errors, writes)
        report = {
            "checks": checks,
            "contexts": len(summary),
            "expression_genes": document["panel_gene_count"],
            "metabolic_genes": len(genes),
            "full_tasks": len(tasks),
            "visible_tasks": len(available),
            "all_tasks": len(document["tasks"]),
            "page_errors": errors,
            "write_requests": writes,
        }
        (output / "checks.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False))
        browser.close()


if __name__ == "__main__":
    main()
