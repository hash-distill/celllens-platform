"""Read-only browser acceptance of result pagination and manually sampled local status."""

import argparse
import json
import math
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def exercise(scope, rows):
    pager = scope.get_by_role("navigation", name="表格分页", exact=True)
    size = pager.get_by_label("每页条数", exact=True)
    expect(size).to_have_value("20")
    expect(size.locator("option")).to_have_text(["10 条 / 页", "20 条 / 页", "50 条 / 页", "100 条 / 页"])
    match = re.search(r"共 (\d+) 条", pager.inner_text())
    assert match, "Pagination total is missing"
    total = int(match[1])
    expect(rows).to_have_count(min(total, 20))
    first = rows.first.inner_text() if total else None
    if total > 20:
        pager.get_by_role("button", name="下一页", exact=True).click()
        expect(pager).to_contain_text(f"第 2 / {math.ceil(total / 20)} 页")
        assert rows.first.inner_text() != first
    for number in (10, 50, 100):
        size.select_option(str(number))
        expect(pager).to_contain_text(f"第 1 / {max(1, math.ceil(total / number))} 页")
        expect(rows).to_have_count(min(total, number))
        if first:
            assert rows.first.inner_text() == first
        expect(pager.get_by_role("button", name="上一页", exact=True)).to_be_disabled()
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    output = Path("reports/pagination-status-2026-10-11")
    output.mkdir(parents=True, exist_ok=True)
    checks, errors = {}, []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        page.on("pageerror", lambda error: errors.append(str(error)))
        requests = []
        status_snapshots = []
        endpoints = ("/api/v1/system-status", "/api/v1/health", "/api/v1/ready")
        page.on(
            "request",
            lambda request: requests.append(request.url) if request.url.endswith(endpoints) else None,
        )
        page.on(
            "response",
            lambda response: (
                status_snapshots.append(response) if response.url.endswith("/system-status") else None
            ),
        )
        page.goto(args.url + "/status", wait_until="networkidle")
        expect(page.get_by_role("button", name="重新检查", exact=True)).to_be_enabled(timeout=20000)
        snapshot = status_snapshots[-1].json()
        environment = page.get_by_role("region", name="运行环境")
        expect(environment.get_by_text(snapshot["system"]["os_version"], exact=True)).to_be_visible()
        expect(environment.get_by_text(snapshot["system"]["python"], exact=True)).to_be_visible()
        if snapshot["system"]["cpu_model"]:
            expect(page.get_by_text(snapshot["system"]["cpu_model"], exact=True)).to_be_visible()
        database = page.get_by_role("region", name="数据库配置")
        expect(database.get_by_text(snapshot["database"]["engine"], exact=True)).to_be_visible()
        expect(database.get_by_text(snapshot["database"]["version"], exact=True)).to_be_visible()
        before = list(requests)
        # Cross the former 30-second poll interval; all three service endpoints must stay idle.
        page.wait_for_timeout(32000)
        assert requests == before, "Service status must not refresh automatically"
        assert len(status_snapshots) == 1
        with page.expect_response(lambda response: response.url.endswith("/system-status")) as rechecked:
            page.get_by_role("button", name="重新检查", exact=True).click()
        refreshed = rechecked.value.json()
        expect(page.get_by_role("button", name="重新检查", exact=True)).to_be_enabled(timeout=20000)
        assert len(status_snapshots) == 2
        assert refreshed["checked_at"] != snapshot["checked_at"]
        checks["local_status"] = {
            "os": snapshot["system"],
            "auto_refresh": False,
        }
        page.screenshot(path=str(output / "local-status-manual.png"), full_page=True)
        records = page.request.get(args.url + "/api/v1/experiments?source=online&status=completed").json()
        run_id = records["items"][0]["id"]
        page.goto(args.url + "/records", wait_until="networkidle")
        expect(page.get_by_label("每页条数")).to_have_value("20")
        page.get_by_label("每页条数").select_option("100")
        expect(page).to_have_url(re.compile(r"size=100"))
        checks["history_page_size"] = "20 default; 100 selectable"
        page.goto(args.url + "/demo?run=" + run_id + "&tab=genes", wait_until="networkidle")
        genes = page.locator(".analysis-panel")
        checks["online_genes"] = exercise(genes, genes.locator("tbody tr.clickable"))
        genes.get_by_role("button", name="下一页", exact=True).click()
        page.get_by_label("搜索基因", exact=True).fill("NO_MATCH_PAGINATION_FIXTURE")
        expect(genes.get_by_role("navigation", name="表格分页")).to_contain_text("共 0 条 · 第 1 / 1 页")
        expect(genes.get_by_role("button", name="下一页", exact=True)).to_be_disabled()
        page.get_by_label("搜索基因", exact=True).fill("")
        page.screenshot(path=str(output / "online-genes-selectable.png"), full_page=True)
        page.get_by_role("tab", name="响应概览", exact=True).click()
        page.goto(args.url + "/coverage?run=" + run_id, wait_until="networkidle")
        catalogue = page.locator(".catalogue-list")
        checks["covered_metabolic_genes"] = exercise(catalogue, catalogue.locator("tbody tr"))
        page.goto(args.url + "/demo?run=" + run_id, wait_until="networkidle")
        page.get_by_role("tab", name="代谢功能", exact=True).click()
        tasks = page.get_by_role("complementary", name="功能任务列表")
        checks["function_tasks"] = exercise(tasks, tasks.locator(".task-option"))
        reactions = page.locator(".reaction-browser")
        expect(reactions.get_by_role("navigation", name="表格分页")).to_be_visible(timeout=20000)
        checks["function_reactions"] = exercise(reactions, reactions.locator(".reaction-options button"))
        page.get_by_role("button", name="任务与反应分数", exact=True).click()
        task_table = (
            page.get_by_role("heading", name="代谢任务差异（scCellFie 任务分数变化）", exact=True)
            .locator("..")
            .locator("..")
        )
        reaction_table = (
            page.get_by_role("heading", name="反应聚合表", exact=True).locator("..").locator("..")
        )
        checks["metabolic_tasks"] = exercise(task_table, task_table.locator("tbody tr"))
        checks["metabolic_reactions"] = exercise(reaction_table, reaction_table.locator("tbody tr"))
        for width in (390, 768):
            page.set_viewport_size({"width": width, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.set_viewport_size({"width": 1440, "height": 1000})
        assert not errors, errors
        browser.close()
    output.joinpath("acceptance.json").write_text(
        json.dumps({"checks": checks, "page_errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "tables": {k: v for k, v in checks.items() if isinstance(v, int)},
                "auto_refresh": False,
                "page_errors": errors,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
