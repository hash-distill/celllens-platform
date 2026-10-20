"""Acceptance against stored results: unified records, direct analysis, live status, responsive UI."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--empty", action="store_true")
    args = parser.parse_args()
    output = Path("reports/records-status-2026-10-11")
    output.mkdir(parents=True, exist_ok=True)
    errors, checks = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url + "/records", wait_until="networkidle")
        expect(page.locator("#record-mode")).to_have_count(0)
        checks.append("online experiment history")
        if args.empty:
            expect(page.get_by_role("heading", name="还没有实验记录", exact=True)).to_be_visible()
            assert page.request.get(args.url + "/api/v1/experiments").json()["total"] == 0
            page.screenshot(path=str(output / "records-empty.png"), full_page=True)
            checks.append("database and UI history empty")
        else:
            page.goto(args.url + "/records?source=online", wait_until="networkidle")
            expect(page.locator(".record-source").first).to_have_text("在线推演")
            run_id = page.locator(".record-id").first.inner_text()
            run_title = page.locator(".record-title").first.inner_text()
            page.get_by_role("link", name="实验分析", exact=True).first.click()
            expect(page).to_have_url(args.url + "/demo?run=" + run_id)
            expect(page.locator("main h1")).to_contain_text(run_title)
            expect(page.locator(".workspace-configuration")).to_have_count(0)
            expect(page.locator("main .page-heading")).to_have_count(0)
            expect(page.get_by_role("region", name="扰动响应概览")).to_be_visible()
            page.get_by_role("tab", name="基因响应", exact=True).click()
            expect(page).to_have_url(args.url + "/demo?run=" + run_id + "&tab=genes")
            page.reload(wait_until="networkidle")
            expect(page.locator("main h1")).to_contain_text(run_title)
            page.screenshot(path=str(output / "experiment-result.png"), full_page=True)
            checks.append(
                "online analysis opens bound experiment without workbench title/settings; tabs survive reload"
            )
            page.goto(args.url + "/records", wait_until="networkidle")
        page.locator(".service-indicator").click()
        expect(page).to_have_url(args.url + "/status")
        expect(page.get_by_role("heading", name="服务状态", exact=True)).to_be_visible()
        expect(page.get_by_role("region", name="数据库配置")).to_be_visible(timeout=20000)
        expect(page.get_by_role("heading", name="使用说明", exact=True)).to_have_count(0)
        expect(page.get_by_role("region", name="GPU 配置")).to_be_visible()
        expect(page.get_by_role("region", name="运行环境")).to_be_visible()
        assert page.locator("progress").count() >= 2
        page.get_by_role("button", name="重新检查", exact=True).click()
        expect(page.get_by_role("button", name="重新检查", exact=True)).to_be_enabled(timeout=20000)
        page.screenshot(path=str(output / "service-status.png"), full_page=True)
        checks.append("connection indicator opens dedicated live service/configuration page")
        page.get_by_role("button", name="切换深色", exact=True).click()
        page.screenshot(path=str(output / "service-status-dark.png"), full_page=True)
        for width in (390, 768):
            page.set_viewport_size({"width": width, "height": 844})
            page.reload(wait_until="networkidle")
            expect(page.locator(".service-indicator")).to_be_visible()
            expect(page.get_by_role("region", name="数据库配置")).to_be_visible(timeout=20000)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            page.screenshot(path=str(output / f"status-{width}.png"), full_page=True)
        checks.append("mobile/tablet status link visible; no horizontal page overflow")
        assert not errors, errors
        browser.close()
    result = {"checks": checks, "page_errors": errors}
    (output / ("empty-acceptance.json" if args.empty else "acceptance.json")).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
