"""Verify covered-only bilingual gene classes and metabolic task explanations."""

import argparse
import csv
import json
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    output = Path("reports/gene-education-2026-10-11")
    output.mkdir(parents=True, exist_ok=True)
    checks, errors, requests = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        page.set_default_timeout(30000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url))
        before = page.request.get(base + "/api/v1/experiments").json()["total"]
        page.goto(base, wait_until="networkidle")
        with page.expect_response(
            lambda response: response.url.endswith("/api/v1/coverage"), timeout=120000
        ) as response:
            page.locator(".coverage-entry").click()
        assert response.value.status == 200
        document = response.value.json()
        genes = [gene for gene in document["genes"] if gene["in_panel"]]
        tasks = [task for task in document["tasks"] if task["coverage_status"] == "full"]
        expect(page.get_by_role("heading", name="模型覆盖范围", exact=True)).to_be_visible()
        background_guide = page.get_by_role("region", name="细胞背景介绍", exact=True)
        expect(background_guide).to_be_visible()
        background_guide.locator(".all-backgrounds summary").click()
        expect(background_guide.locator(".background-grid .cell-background-card")).to_have_count(4)
        expected_backgrounds = {
            "K562": ("髓系白血病", "Myeloid leukemia", "CVCL_0004"),
            "RPE1": ("永生化视网膜", "Immortalized retinal pigment", "CVCL_4388"),
            "Jurkat": ("T 淋巴细胞", "T-cell leukemia", "CVCL_0065"),
            "HepG2": ("肝母细胞瘤", "Hepatoblastoma-derived", "CVCL_0027"),
        }
        for cell_line, (chinese, english, accession) in expected_backgrounds.items():
            card = background_guide.locator(".background-grid").get_by_role(
                "article", name=cell_line + " 细胞背景介绍", exact=True
            )
            expect(card).to_contain_text(chinese)
            expect(card).to_contain_text(english)
            expect(card.locator("section p[lang=en]")).to_have_count(3)
            for paragraph in card.locator("section p[lang=en]").all():
                expect(paragraph).not_to_be_empty()
            expect(card.get_by_role("link", name="Cellosaurus · " + accession)).to_have_attribute(
                "href", "https://www.cellosaurus.org/" + accession
            )
        page.screenshot(path=str(output / "four-bilingual-cell-backgrounds.png"), full_page=True)
        background_guide.locator(".all-backgrounds summary").click()
        checks.append("Four bilingual cell backgrounds: origin, features, uses and primary sources")
        expect(page.locator(".coverage-metrics strong")).to_have_text(["138", "7", "86"])
        text = page.locator(".coverage-page").inner_text()
        assert not re.search(r"\b(931|218|787|2,000|2000)\b", text), text
        assert not re.search(r"\d+\s*/\s*\d+", page.locator(".coverage-metrics").inner_text())
        expect(page.locator(".catalogue-list tbody tr")).to_have_count(20)
        page.get_by_label("每页条数", exact=True).select_option("50")
        expect(page.locator(".catalogue-list tbody tr")).to_have_count(50)
        page.get_by_label("搜索基因", exact=True).fill("NO_MATCH_GENE_FIXTURE")
        expect(page.locator(".catalogue-list")).to_contain_text("没有匹配的已覆盖基因")
        page.get_by_label("搜索基因", exact=True).fill("")
        page.get_by_label("代谢基因功能分类", exact=True).select_option("PC00135")
        expect(page.get_by_role("article", name="当前基因类别介绍")).to_contain_text("异构酶")
        expect(page.get_by_role("article", name="当前基因类别介绍")).to_contain_text("isomerase")
        expect(page.get_by_role("article", name="当前基因类别介绍").locator("p[lang=en]")).not_to_be_empty()
        page.get_by_label("搜索基因", exact=True).fill("TPI1")
        expect(page.locator(".catalogue-list tbody tr")).to_have_count(1)
        page.locator(".catalogue-list tbody .catalogue-link").click()
        expect(page.get_by_role("complementary", name="基因范围详情")).to_contain_text("异构酶")
        expect(page.get_by_role("complementary", name="基因范围详情")).to_contain_text("isomerase")
        with page.expect_download() as download:
            page.get_by_role("button", name="下载已覆盖基因", exact=True).click()
        path = output / download.value.suggested_filename
        download.value.save_as(path)
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == len(genes) == 138
        assert all(row["category_zh"] and row["category_en"] for row in rows)
        page.screenshot(path=str(output / "classified-metabolic-genes.png"), full_page=True)
        checks.append(
            "Covered counts only; bilingual classes, filters, gene details, pagination and 138-gene CSV"
        )
        page.get_by_role("button", name=re.compile("代谢任务介绍")).click()
        expect(page.locator(".task-guide-card")).to_have_count(len(tasks))
        for task in tasks:
            guide = task["guide"]
            card = page.locator(".task-guide-card").filter(has_text=guide["name_zh"])
            expect(card).to_contain_text(guide["name_en"])
            expect(card).to_contain_text(guide["description_en"])
            card.click()
            detail = page.get_by_role("complementary", name="任务范围详情")
            expect(detail).to_contain_text(guide["scope_zh"])
            expect(detail).to_contain_text(guide["scope_en"])
            expect(detail.get_by_role("link", name=re.compile("说明来源"))).to_have_attribute(
                "href", guide["source_url"]
            )
        page.get_by_label("搜索任务", exact=True).fill("过氧化氢")
        expect(page.locator(".task-guide-card")).to_have_count(1)
        page.get_by_label("搜索任务", exact=True).fill("TPI1")
        expect(page.locator(".task-guide-card")).to_have_count(1)
        page.get_by_label("搜索任务", exact=True).fill("")
        page.screenshot(path=str(output / "seven-bilingual-tasks.png"), full_page=True)
        page.locator(".coverage-method summary").click()
        with page.expect_download() as download:
            page.get_by_role("button", name="下载当前覆盖目录 JSON", exact=True).click()
        path = output / download.value.suggested_filename
        download.value.save_as(path)
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert len(saved["genes"]) == 138 and len(saved["tasks"]) == 7 and len(saved["reactions"]) == 86
        assert all(gene["in_panel"] for gene in saved["genes"])
        checks.append("Seven bilingual task names, meaning, scope and sources; covered-only JSON")
        for model in document["models"]:
            if page.get_by_label("覆盖目录细胞背景", exact=True).input_value() != model["cell_line"]:
                page.get_by_label("覆盖目录细胞背景", exact=True).select_option(model["cell_line"])
                expect(page.locator(".coverage-context h2")).to_contain_text(
                    model["cell_line"] + " · STATE", timeout=120000
                )
            expect(page.locator(".coverage-metrics strong")).to_have_text(["138", "7", "86"])
            expect(page.locator(".cell-background-guide > .cell-background-card")).to_have_attribute(
                "aria-label", model["cell_line"] + " 细胞背景介绍"
            )
        records = page.request.get(base + "/api/v1/experiments?source=online&status=completed").json()[
            "items"
        ]
        run_id = records[0]["id"]
        page.goto(base + "/coverage?run=" + run_id, wait_until="networkidle")
        expect(page.get_by_role("heading", name="输入覆盖范围", exact=True)).to_be_visible()
        expect(page.locator(".coverage-metrics strong")).to_have_text(["138", "7", "86"])
        page.goto(base + "/workbench", wait_until="networkidle")
        for cell_line in expected_backgrounds:
            page.get_by_role("radio", name=cell_line, exact=True).check()
            card = page.locator(".param-panel .cell-background-card")
            expect(card).to_have_attribute("aria-label", cell_line + " 细胞背景介绍")
            expect(card).to_contain_text(expected_backgrounds[cell_line][0])
            expect(card).to_contain_text(expected_backgrounds[cell_line][1])
            card.locator("summary").click()
            expect(card.locator("section p[lang=en]")).to_have_count(3)
            expect(card.get_by_role("link", name=re.compile("Cellosaurus"))).to_be_visible()
            card.locator("summary").click()
        page.get_by_role("radio", name="K562", exact=True).check()
        expect(page.get_by_role("link", name="查看各细胞背景介绍 ↗")).to_have_attribute(
            "href", "/coverage?cell_line=K562"
        )
        checks.append("Workbench descriptions follow all four selections without submitting experiments")
        catalogue = page.request.get(base + "/api/v1/catalog/perturbations?cell_line=K562").json()
        assert len(catalogue["items"]) == len(catalogue["genes"])
        classes = page.get_by_label("基因功能分类 · Gene function class", exact=True)
        expect(classes.locator("option")).to_have_count(len(catalogue["categories"]) + 1)
        classes.select_option("PC00264")
        expect(page.get_by_role("article", name="当前基因类别介绍")).to_contain_text(
            "gene-specific transcriptional regulator"
        )
        box = page.get_by_role("combobox", name="扰动基因", exact=True)
        box.fill("MYC")
        option = page.get_by_role("option", name="MYC", exact=True)
        expect(option).to_be_visible()
        expect(option).to_contain_text("基因特异性转录调控因子")
        option.click()
        expect(page.locator(".selected-gene-annotation")).to_contain_text("MYC")
        classes.select_option("PC00144")
        box.fill("ALDOA")
        page.get_by_role("option", name="ALDOA", exact=True).click()
        expect(page.locator(".selected-gene-annotation")).to_contain_text("裂合酶")
        classes.select_option("unclassified")
        box.fill("")
        expected = sum("unclassified" in gene["category_ids"] for gene in catalogue["genes"])
        expect(page.locator("#perturbation-listbox [role=option]")).to_have_count(expected)
        page.screenshot(path=str(output / "classified-perturbation-picker.png"), full_page=True)
        checks.append(
            "Registered backgrounds and saved source; bilingual class filters and unchanged targets"
        )
        for query in ("", "&tab=metabolism", "&tab=metabolism&view=data"):
            start = len(requests)
            page.goto(base + "/demo?run=" + run_id + query, wait_until="networkidle")
            expect(page.locator(".official-completeness")).to_have_count(0)
            assert not any("/completeness" in url for url in requests[start:])
        page.goto(base + "/coverage", wait_until="networkidle")
        for width in (1440, 1920):
            page.set_viewport_size({"width": width, "height": 900})
            page.locator(".all-backgrounds summary").click()
            expect(page.locator(".background-grid .cell-background-card")).to_have_count(4)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            page.screenshot(path=str(output / f"coverage-{width}.png"), full_page=True)
            page.goto(base + "/workbench", wait_until="networkidle")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            page.goto(base + "/coverage", wait_until="networkidle")
        page.get_by_role("button", name="切换深色", exact=True).click()
        page.screenshot(path=str(output / "coverage-dark.png"), full_page=True)
        assert page.request.get(base + "/api/v1/experiments").json()["total"] == before
        assert not errors, errors
        output.joinpath("acceptance.json").write_text(
            json.dumps(
                {
                    "checks": checks,
                    "page_errors": errors,
                    "genes_covered": len(genes),
                    "fully_covered_tasks": len(tasks),
                    "history_unchanged": True,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        browser.close()
    print("Covered-only counts, bilingual gene classification and all seven task guides: OK")


if __name__ == "__main__":
    main()
