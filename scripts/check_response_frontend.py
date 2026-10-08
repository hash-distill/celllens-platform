"""Verify the response workbench against real runs; injected failures are explicitly labeled."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--run-id", required=True, help="Completed run with frozen task_trace.json")
    parser.add_argument("--historical-run-id", default="run_05708065c9414005")
    args = parser.parse_args()
    out = Path(__file__).resolve().parents[1] / "reports/frontend/response"
    out.mkdir(parents=True, exist_ok=True)
    results: list[str] = []
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.set_default_timeout(15000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        base = args.url
        run_id = args.run_id
        record_response = page.request.get(f"{base}/api/v1/runs/{run_id}")
        assert record_response.ok
        record = record_response.json()
        assert record["status"] == "completed", record
        genes = page.request.get(f"{base}/api/v1/runs/{run_id}/genes?limit=2000").json()["items"]
        expected_top_gene = max(genes, key=lambda g: abs(float(g["predicted_delta"])))

        page.goto(base + "/workbench", wait_until="networkidle")
        expect(page.get_by_role("heading", name="实验工作台", exact=True)).to_be_visible()
        expect(page.locator(".workspace-empty")).to_be_visible()
        expect(page.locator(".delta-row")).to_have_count(0)
        expect(page.locator("canvas")).to_have_count(0)
        page.screenshot(path=str(out / "empty-desktop.png"), full_page=True)
        results.append("empty state has no fabricated results or eagerly loaded 3D canvas")

        page.goto(base + "/records", wait_until="networkidle")
        page.locator("#manual-run-id").fill(run_id)
        page.get_by_role("button", name="打开", exact=True).click()
        expect(page).to_have_url(base + "/workbench?run=" + run_id)
        expect(page.locator(".gene-row").first).to_contain_text(expected_top_gene["gene"])
        expect(page.locator(".task-row").first).to_be_visible()
        expect(page.locator(".trace-network")).to_be_visible()
        expect(page.locator(".active-experiment")).to_contain_text(record["request"]["perturbation"])
        expect(page.locator(".trace-provenance")).to_contain_text("scCellFie")
        projection = page.request.get(f"{base}/api/v1/runs/{run_id}/projection").json()
        selection = projection["population_selection"]
        assert selection["status"] == "matched"
        assert selection["perturbation"] == record["request"]["perturbation"]
        assert selection["selected_prediction_cells"] == record["request"]["n_cells"]
        source_counts = {
            source: sum(point["source"] == source for point in projection["points"])
            for source in ["control", "predicted", "observed"]
        }
        expect(page.locator(".state-overview")).to_be_visible()
        expect(page.locator(".state-population")).to_have_count(
            sum(count > 0 for count in source_counts.values())
        )
        for label, source in [("对照群体", "control"), ("扰动后预测群体", "predicted")]:
            expect(
                page.locator(".state-population").filter(has=page.get_by_role("heading", name=label))
            ).to_contain_text(f"{source_counts[source]} 个显示点")
        expect(page.locator(".state-overview .note")).to_contain_text("不表示同一个细胞")
        expect(page.locator(".state-overview")).to_contain_text("预测群体已按")
        page.get_by_role("button", name="叠加比较", exact=True).click()
        expect(page.locator(".state-overview .projection-chart")).to_have_count(1)
        page.get_by_role("button", name="并排比较", exact=True).click()
        results.append(
            "single-cell comparison uses actual source counts; overlay and pairing boundary are explicit"
        )
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=str(out / "live-desktop.png"), full_page=True)
        results.append("manual run selection loads real expression, metabolism and frozen trace")

        page.locator(".workspace-configuration > summary").click()
        page.locator("#perturbation-input").fill("MYC")
        expect(page.locator(".active-experiment")).to_contain_text(record["request"]["perturbation"])
        expect(page.locator(".run-identity")).to_have_text(run_id)
        page.locator(".gene-row").nth(1).click()
        selected_gene = page.locator(".gene-row").nth(1).locator(".row-name").inner_text()
        expect(page.locator(".gene-detail h3")).to_have_text(selected_gene)
        results.append("draft editing does not mutate result identity; gene selection updates details")

        page.locator(".task-row").nth(1).click()
        task_name = (
            page.locator(".task-row")
            .nth(1)
            .locator(".row-name")
            .evaluate("el => el.firstChild.textContent.trim()")
        )
        expect(page.locator(".trace-task h3")).to_have_text(task_name)
        page.locator(".task-row").first.click()
        expect(page.locator(".trace-network")).to_be_visible()
        page.get_by_role("button", name="探索三维功能网络").click()
        expect(page.locator(".spatial-canvas canvas")).to_be_visible()
        assert page.locator(".spatial-trace .notice-warn").count() == 0
        canvas = page.locator(".spatial-canvas canvas")
        before = canvas.screenshot()
        bounds = canvas.bounding_box()
        assert bounds
        page.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
        page.mouse.down()
        page.mouse.move(
            bounds["x"] + bounds["width"] / 2 + 100, bounds["y"] + bounds["height"] / 2 + 40, steps=8
        )
        page.mouse.up()
        assert before != canvas.screenshot(), "Network rotation must change rendered output"
        page.get_by_role("button", name="复位视角", exact=True).click()
        page.locator(".task-trace").screenshot(path=str(out / "live-trace-network.png"))
        results.append("task selection replaces trace; real-data 3D graph renders and responds to rotation")

        page.locator("select[id^='evidence-filter']").select_option("supported")
        for row in page.locator(".task-row").all():
            expect(row).to_contain_text("覆盖支持")
        page.locator("select[id^='evidence-filter']").select_option("all")
        page.reload(wait_until="networkidle")
        expect(page.locator(".run-identity")).to_have_text(run_id)
        expect(page.locator(".gene-row").first).to_be_visible()
        results.append("coverage filter and reload preserve URL-bound identity")

        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.locator(".gene-row").first).to_be_visible()
        assert not page.evaluate("document.documentElement.scrollWidth > innerWidth"), "Mobile overflow"
        page.screenshot(path=str(out / "live-mobile.png"), full_page=True)
        results.append("390px mobile layout has no horizontal overflow")
        page.set_viewport_size({"width": 1440, "height": 1000})

        for step, heading in enumerate(
            [
                "一次扰动，会带来什么变化？",
                "一次扰动，怎样改变表达？",
                "从表达变化，追踪功能响应。",
                "每一个结论，都有出处。",
            ]
        ):
            page.goto(f"{base}/demo?run={run_id}&step={step}", wait_until="networkidle")
            expect(page.locator(".demo-title h1")).to_have_text(heading)
            expect(page.locator(".cell-viewport")).to_have_count(0)
            if step == 1:
                expect(page.locator(".gene-row").first).to_be_visible()
                expect(page.locator(".state-overview")).to_be_visible()
            if step == 2:
                expect(page.locator(".trace-network")).to_be_visible()
                page.screenshot(path=str(out / "demo-metabolism.png"), full_page=True)
        page.locator(".demo-title h1").click()
        page.keyboard.press("Escape")
        expect(page).to_have_url(base + "/workbench?run=" + run_id)
        results.append("four chapters use selected results; Escape restores selected workbench")

        page.goto(f"{base}/runs/{run_id}", wait_until="networkidle")
        expect(page.get_by_role("tab", name="响应概览")).to_have_attribute("aria-selected", "true")
        expect(page.locator(".gene-row").first).to_be_visible()
        expect(page.get_by_role("tab", name="结构示意")).to_have_count(0)
        expect(page.locator(".cell-viewport")).to_have_count(0)
        page.goto(f"{base}/runs/{run_id}?tab=structure", wait_until="networkidle")
        expect(page.get_by_role("tab", name="响应概览")).to_have_attribute("aria-selected", "true")
        results.append("legacy detail redirects to the unified workbench; structural view is removed")

        page.goto(f"{base}/workbench?run={args.historical_run_id}", wait_until="networkidle")
        expect(page.locator(".state-overview")).to_contain_text("旧分析未记录扰动细胞筛选协议")
        expect(page.locator(".task-trace")).to_contain_text("本次运行尚无关联追溯记录")
        expect(page.locator(".trace-network")).to_have_count(0)
        results.append("historical run does not borrow current database relationships")

        # Deliberate API failure injection only in this isolated browser context.
        route_pattern = f"**/api/v1/runs/{run_id}/genes*"
        page.route(
            route_pattern,
            lambda route: route.fulfill(status=503, json={"detail": {"message": "test outage"}}),
        )
        page.goto(f"{base}/workbench?run={run_id}", wait_until="networkidle")
        expect(page.get_by_role("button", name="重试基因结果")).to_be_visible()
        expect(page.locator(".task-row").first).to_be_visible()
        page.unroute(route_pattern)
        page.get_by_role("button", name="重试基因结果").click()
        expect(page.locator(".gene-row").first).to_be_visible()
        results.append("injected gene API failure stays local; retry restores actual data")

        fake_record = {**record, "status": "state_running", "stage_progress": 15}
        record_pattern = f"**/api/v1/runs/{run_id}"
        page.route(record_pattern, lambda route: route.fulfill(json=fake_record))
        page.reload(wait_until="networkidle")
        expect(page.get_by_role("progressbar")).to_have_attribute("aria-valuenow", "15")
        expect(page.locator(".gene-row")).to_have_count(0)
        page.unroute(record_pattern)
        results.append("injected running state uses server progress and hides completed data")

        page.goto(base + "/workbench?run=missing_response_test", wait_until="networkidle")
        expect(page.get_by_role("heading", name="运行不存在")).to_be_visible()
        expect(page.locator(".gene-row")).to_have_count(0)
        results.append("missing run shows explicit empty state")
        projection_pattern = f"**/api/v1/runs/{run_id}/projection"
        page.route(
            projection_pattern,
            lambda route: route.fulfill(status=404, json={"detail": {"code": "ARTIFACT_NOT_FOUND"}}),
        )
        page.goto(f"{base}/workbench?run={run_id}", wait_until="networkidle")
        expect(page.locator(".state-overview")).to_contain_text("本次结果未提供二维投影")
        expect(page.locator(".gene-row").first).to_be_visible()
        expect(page.locator(".task-row").first).to_be_visible()
        page.unroute(projection_pattern)
        results.append(
            "injected missing projection does not hide independent expression or metabolism results"
        )
        assert not errors, errors
        report = {"run_id": run_id, "url": base, "checks": results, "pageerrors": errors}
        (out / "browser-checks.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
