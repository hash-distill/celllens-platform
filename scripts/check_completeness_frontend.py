"""Verify official completeness on four real backgrounds and unavailable legacy results."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "reports/frontend/official-completeness"
    root.mkdir(parents=True, exist_ok=True)
    checks, errors, failures = [], [], []
    runs = {
        "K562": "run_4d0b3038ea8642af",
        "RPE1": "run_30dc0a6410ca4e2d",
        "Jurkat": "run_5e06e0fd0b9140a7",
        "HepG2": "run_1b544f2cff4d400a",
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "response", lambda response: failures.append(response.url) if response.status >= 400 else None
        )
        for context, run_id in runs.items():
            for tab in ["response", "metabolism"]:
                page.goto(f"{args.url}/workbench?run={run_id}&tab={tab}", wait_until="networkidle")
                official = page.get_by_role("region", name="scCellFie 官方完整性分析")
                expect(official.locator(".official-cards")).to_contain_text("131 / 931")
                expect(official.locator(".official-cards")).to_contain_text("7 / 218")
                expect(official.locator(".official-cards")).to_contain_text("38.7%")
                expect(page.get_by_role("radiogroup", name="任务覆盖等级筛选")).to_have_count(0)
                expect(page.get_by_role("combobox", name="筛选任务覆盖等级")).to_have_count(0)
                official.locator(".official-details > summary").click()
                expect(official.locator(".official-details")).to_contain_text("192 项任务")
                search = official.get_by_role("textbox", name="搜索官方完整性任务")
                search.fill("ATP generation from glucose (hypoxic conditions)")
                expect(official.locator(".official-task-row")).to_have_count(1)
                official.locator(".task-link").click()
                expect(official.locator(".official-missing")).to_contain_text("缺失关联基因")
                search.fill("no-such-task")
                expect(official).to_contain_text("没有匹配的任务")
                search.fill("")
                page.screenshot(path=str(root / f"{context}-{tab}.png"), full_page=True)
                checks.append(
                    f"{context}/{tab}: official summary, no project filters, missing genes and search"
                )
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_function("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(root / f"{context}-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})
        official = page.get_by_role("region", name="scCellFie 官方完整性分析")
        official.locator(".official-provenance > summary").click()
        with page.expect_download() as download_event:
            official.get_by_role("button", name="下载完整 JSON（含反应明细）").click()
        download = download_event.value
        path = root / download.suggested_filename
        download.save_as(path)
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["run_id"] == runs["HepG2"]
        assert len(document["tasks"]) == 218 and len(document["reactions"]) == 787
        checks.append("JSON download preserves run identity and all 218 tasks/787 reactions")
        before = len(failures)
        page.goto(args.url + "/workbench?run=run_386e07d2897f4e0f&tab=metabolism", wait_until="networkidle")
        expect(page.locator(".official-completeness")).to_contain_text("未提供官方完整性报告")
        expect(page.get_by_role("radiogroup", name="任务覆盖等级筛选")).to_be_visible()
        assert len(failures) == before
        checks.append("legacy demo explicitly unavailable without a failing completeness request")
        browser.close()
    assert not errors and not failures, (errors, failures)
    result = {"checks": checks, "page_errors": errors, "failed_responses": failures}
    (root / "checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
