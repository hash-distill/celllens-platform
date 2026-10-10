"""Verify independent pages, server history and the unified experiment workflow."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def expand_projection(page):
    """Projection is an auxiliary view, opened explicitly before checking it."""
    preview = page.locator(".projection-preview")
    if preview.count() and preview.get_attribute("open") is None:
        preview.locator(":scope > summary").click()
        page.wait_for_load_state("networkidle")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    out = Path(__file__).resolve().parents[1] / "reports/frontend/navigation"
    out.mkdir(parents=True, exist_ok=True)
    checks, errors, widths = [], [], {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.set_default_timeout(15000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        base, run_id = args.url, args.run_id
        page.goto(base, wait_until="networkidle")
        expect(page.locator(".home-page")).to_be_visible()
        expect(page.locator(".param-panel, aside, canvas")).to_have_count(0)
        nav = page.locator(".app-header nav")
        for name in ["首页", "实验工作台", "实验记录", "实验比较", "结果解读", "使用说明"]:
            expect(nav.get_by_role("link", name=name, exact=True)).to_be_visible()
        page.screenshot(path=str(out / "home.png"), full_page=True)
        checks.append("independent homepage and six top navigation entries; no experiment form")

        expected = page.request.get(base + "/api/v1/runs?limit=20").json()
        page.goto(base + "/records", wait_until="networkidle")
        expect(page.locator(".records-count")).to_contain_text(f"共 {expected['total']} 个实验")
        assert page.locator(".records-table tbody tr").count() == len(expected["items"])
        assert page.evaluate("localStorage.getItem('celllens.recent.v1')") is None
        expect(page.locator(".records-table tbody tr").first).to_have_attribute(
            "data-run-id", expected["items"][0]["run_id"]
        )
        page.screenshot(path=str(out / "records.png"), full_page=True)
        checks.append("fresh browser loads complete server history in descending creation order")

        if expected["total"] > 10:
            page.locator("#record-size").select_option("10")
            expect(page.locator(".records-table tbody tr")).to_have_count(10)
            page.get_by_role("button", name="下一页", exact=True).click()
            expect(page).to_have_url(base + "/records?size=10&page=2")
            page.reload(wait_until="networkidle")
            expected_second = page.request.get(base + "/api/v1/runs?limit=10&offset=10").json()
            expect(page.locator(".records-table tbody tr").first).to_have_attribute(
                "data-run-id", expected_second["items"][0]["run_id"]
            )
            page.go_back(wait_until="networkidle")
            expect(page.locator(".record-pagination")).to_contain_text("第 1 /")
        checks.append("history pagination, page-size, reload and browser-back preserve URL state")

        page.locator("#record-search").fill(run_id)
        page.locator("#record-status").select_option("completed")
        page.locator("#record-mode").select_option("online")
        page.get_by_role("button", name="检索", exact=True).click()
        expect(page.locator(".records-table tbody tr")).to_have_count(1)
        expect(page.locator(".records-table tbody tr")).to_have_attribute("data-run-id", run_id)
        page.reload(wait_until="networkidle")
        expect(page.locator("#record-search")).to_have_value(run_id)
        page.locator("#record-search").fill("NO_SUCH_EXPERIMENT")
        page.get_by_role("button", name="检索", exact=True).click()
        expect(page.get_by_role("heading", name="没有符合条件的实验")).to_be_visible()
        checks.append("combined gene/id search, status/source filters, empty result and reload")

        page.locator("#manual-run-id").fill(run_id)
        page.get_by_role("button", name="打开", exact=True).click()
        expect(page).to_have_url(base + "/workbench?run=" + run_id)
        expand_projection(page)
        expect(page.locator(".state-overview")).to_contain_text("64 个显示点")
        expect(page.locator(".workspace-configuration")).not_to_have_attribute("open", "")
        expect(page.locator(".cell-viewport, .instrument-rail, .experiment-dock")).to_have_count(0)
        page.get_by_role("button", name="复用参数", exact=True).click()
        expect(page.locator("#perturbation-input")).to_have_value("AAMP")
        page.locator(".workspace-configuration > summary").click()
        page.get_by_role("button", name="加入比较", exact=True).click()
        expect(page.get_by_role("button", name="已加入比较", exact=True)).to_be_disabled()
        page.screenshot(path=str(out / "analysis.png"), full_page=True)
        page.locator(".app-header nav").get_by_role("link", name="实验比较").click()
        expect(page.get_by_text("已加载", exact=True)).to_be_visible()
        page.goto(base + "/workbench?run=" + run_id, wait_until="networkidle")
        page.locator(".app-header nav").get_by_role("link", name="结果解读", exact=True).click()
        expect(page).to_have_url(base + "/demo?run=" + run_id)
        checks.append("workbench binds real results; parameter reuse, comparison and demo keep run identity")

        page.goto(base + "/runs/" + run_id + "?tab=structure", wait_until="networkidle")
        expect(page).to_have_url(base + "/workbench?run=" + run_id)
        expand_projection(page)
        expect(page.locator(".state-overview")).to_be_visible()
        expect(page.locator(".cell-viewport")).to_have_count(0)
        checks.append("legacy result and structure links redirect to unified workbench")

        page.goto(base + "/workbench", wait_until="networkidle")
        page.locator("input[type=radio][value=precomputed]").check()
        page.locator("#perturbation-input").fill("ALDOA")
        page.locator("#perturbation-input").press("Enter")
        page.screenshot(path=str(out / "setup.png"), full_page=True)
        with page.expect_response(
            lambda response: response.url.endswith("/api/v1/runs") and response.request.method == "POST"
        ) as created_response:
            page.get_by_role("button", name="开始实验", exact=True).click()
        created = created_response.value.json()
        expect(page).to_have_url(base + "/workbench?run=" + created["run_id"])
        expect(page.locator(".active-experiment")).to_contain_text("真实结果回放")
        expect(page.locator(".active-experiment")).to_contain_text("分析完成", timeout=30000)
        expect(page.locator(".task-row").first).to_be_visible()
        expect(page.locator(".active-experiment")).not_to_contain_text("合成")
        page.goto(base + "/records?q=" + created["run_id"], wait_until="networkidle")
        expect(page.locator(".records-table tbody tr")).to_have_count(1)
        checks.append("actual ALDOA real-result replay opens analysis and persists in server history")

        failed_context = browser.new_context()
        failed_context.route(
            "**/api/v1/runs?*",
            lambda route: route.fulfill(
                status=503,
                json={"detail": {"code": "navigation_test_failure", "message": "injected history failure"}},
            ),
        )
        failed = failed_context.new_page()
        failed.goto(base + "/records", wait_until="networkidle")
        expect(failed.get_by_role("heading", name="实验记录读取失败")).to_be_visible()
        expect(failed.locator(".records-table tbody tr")).to_have_count(0)
        failed_context.unroute("**/api/v1/runs?*")
        failed.get_by_role("button", name="重试记录", exact=True).click()
        expect(failed.locator(".records-table tbody tr").first).to_be_visible()
        failed_context.close()
        checks.append("injected history failure remains explicit and retry restores server records")

        paths = ["/", "/workbench", "/records", "/compare", "/demo", "/about"]
        for width in [1440, 768, 390]:
            page.set_viewport_size({"width": width, "height": 1000})
            dimensions = []
            for path in paths:
                page.goto(base + path, wait_until="networkidle")
                dimensions.append(page.locator(".page").bounding_box())
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), (width, path)
            assert max(item["width"] for item in dimensions) - min(item["width"] for item in dimensions) < 1
            assert max(item["x"] for item in dimensions) - min(item["x"] for item in dimensions) < 1
            widths[str(width)] = dimensions
        page.goto(base + "/records", wait_until="networkidle")
        page.screenshot(path=str(out / "records-mobile.png"), full_page=True)
        checks.append("all six pages share widths at 1440/768/390 with no document overflow")
        assert not errors, errors
        report = {
            "checks": checks,
            "page_errors": errors,
            "dimensions": widths,
            "analysis_run_id": run_id,
            "precomputed_submission": created,
        }
        (out / "checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
