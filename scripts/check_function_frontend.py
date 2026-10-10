"""Verify functional before/after visualization against saved real runs and live UI."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import Error, expect, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / "reports/function-visualization-2026-10-09/browser"
    output.mkdir(parents=True, exist_ok=True)
    replays = {
        "K562": "run_2d7de9d129904b63",
        "RPE1": "run_2151b0c415484f8e",
        "Jurkat": "run_4a24afcd5b084acf",
        "HepG2": "run_0895eccf20f8405d",
    }
    acd = "run_c76a0442621c4e0d"
    errors, failed, checks = [], [], []
    expected_errors = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1100})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "response",
            lambda response: (
                failed.append({"url": response.url, "status": response.status})
                if response.status >= 400
                and "/api/" in response.url
                and not any(fragment in response.url for fragment in expected_errors)
                else None
            ),
        )

        def open_run(run_id, path="workbench", suffix="&tab=function"):
            page.goto(args.url + f"/{path}?run={run_id}{suffix}", wait_until="networkidle", timeout=60000)
            expect(page.locator(".function-workspace")).to_be_visible()
            expect(page.locator(".function-node").first).to_be_visible(timeout=15000)

        def load_trace(run_id, task_id):
            response = page.request.get(
                args.url
                + f"/api/v1/runs/{run_id}/task-trace?"
                + urlencode({"task_id": task_id, "scope": "all"})
            )
            assert response.ok, response.text()
            return response.json()

        def wait_trace(task_id):
            expect(page.locator(".function-node").first).to_be_visible()
            expect(page.locator(".task-heading")).to_contain_text(task_id)
            expect(page.locator('[data-source="predicted"] .function-node').last).to_have_attribute(
                "data-node", "task:" + task_id
            )

        def compare_coordinates():
            coordinates = page.locator(".network-panel").evaluate_all(
                "panels => panels.map(panel => Array.from(panel.querySelectorAll('[data-node]'))"
                ".map(node => [node.dataset.node,node.getAttribute('transform')]))"
            )
            assert len(coordinates) == 2 and coordinates[0] == coordinates[1]

        # Reconnaissance: inspect the fully rendered page before acting on controls.
        open_run(acd)
        (output / "initial-dom.html").write_text(page.content(), encoding="utf-8")
        print("Rendered functional view:", page.locator(".function-heading").inner_text(), flush=True)
        for line, run_id in replays.items():
            open_run(run_id)
            expect(page.locator(".active-experiment")).to_contain_text(line + " / ALDOA")
            expect(page.locator(".function-heading")).to_contain_text("真实结果回放")
            task_id = page.locator(".task-option.active").get_attribute("data-task")
            data = load_trace(run_id, task_id)
            frozen = json.loads(
                (root / "data/derived/runs" / run_id / "task_trace.json").read_text(encoding="utf-8")
            )
            assert data["scope"] == "all" and not data["truncated"]
            assert data["task"]["predicted"] == frozen["tasks"][task_id]["predicted"]
            node = page.locator('[data-source="predicted"] [data-node]').last
            assert float(node.get_attribute("data-value")) == data["task"]["predicted"]
            assert page.locator(
                '[data-score="predicted"]'
            ).inner_text() == f"{data['task']['predicted']:.4f}".rstrip("0").rstrip(".")
            compare_coordinates()
            page.get_by_role("button", name="预测与实测", exact=True).click()
            expect(page.locator('[data-source="observed"]')).to_be_visible()
            observed = page.locator('[data-source="observed"] [data-node]').last
            assert (
                float(observed.get_attribute("data-value"))
                == data["task"]["control"] + data["task"]["observed_delta"]
            )
            compare_coordinates()
            page.screenshot(path=str(output / f"{line}-observed.png"), full_page=True)
            page.get_by_role("button", name="变化量", exact=True).click()
            expect(page.locator(".network-panel")).to_have_count(1)
            assert (
                float(page.locator('[data-source="delta"] [data-node]').last.get_attribute("data-value"))
                == data["task"]["predicted_delta"]
            )
            checks.append(
                f"{line}: frozen scores, full trace, matching layout, real observed and delta views"
            )
            print(checks[-1], flush=True)

        open_run("run_9454c770db3842a1")
        expect(page.locator(".function-heading")).to_contain_text("实测诊断（非独立留出验收）")
        expect(page.get_by_role("button", name="预测与实测", exact=True)).to_be_visible()
        checks.append("Original validation run exposes observed view with explicit diagnostic boundary")
        open_run(acd)
        expect(page.get_by_role("button", name="预测与实测", exact=True)).to_have_count(0)
        compare_coordinates()
        first_gene = page.locator('[data-source="predicted"] [data-node^="gene:"]').first
        gene_id = first_gene.get_attribute("data-node").split(":", 1)[1]
        first_gene.focus()
        first_gene.press("Enter")
        expect(page.locator(".node-detail .identifier")).to_have_text(gene_id)
        page.locator('[data-source="control"] [data-node^="reaction:"]').first.click()
        expect(page.locator(".node-detail h3")).to_have_text("反应分数")
        page.locator('[data-reaction="FBA"]').click()
        expect(page.locator('[data-source="predicted"] [data-node="reaction:FBA"]')).to_have_class(
            "function-node selected missing"
        )
        expect(page.locator('[data-score="predicted"]')).to_have_text("未提供")
        expect(page.locator(".gpr-detail code")).to_contain_text("ALDO")
        checks.append(
            "HepG2/ACD: no invented observation, mouse/keyboard selection, null reaction and original GPR"
        )
        page.get_by_label("功能分类", exact=True).select_option("ENERGY METABOLISM")
        expect(page.locator(".task-option")).not_to_have_count(0)
        assert all("ENERGY METABOLISM" in item.inner_text() for item in page.locator(".task-option").all())
        page.get_by_label("搜索功能任务").fill("not-a-real-task-20261009")
        expect(page.locator(".task-options")).to_contain_text("未找到匹配的任务")
        expect(page.locator(".function-node")).to_have_count(0)
        page.get_by_label("搜索功能任务").fill("")
        page.get_by_label("功能分类", exact=True).select_option("")
        expect(page.locator(".task-option")).to_have_count(50)
        page.locator(".task-browser").get_by_role("button", name="下一页", exact=True).click()
        expect(page.locator(".task-browser .pager")).to_contain_text("第 2 / 3 页")
        checks.append("Full task categories, search empty state and task pagination")
        page.get_by_label("搜索功能任务").fill("Lysine degradation")
        page.locator(".task-option").first.click()
        wait_trace("Lysine degradation")
        data = load_trace(acd, "Lysine degradation")
        assert len(data["reactions"]) == 92
        expect(page.locator(".reaction-browser header")).to_contain_text("92 / 92")
        expect(page.locator(".reaction-options button")).to_have_count(50)
        page.locator(".reaction-browser").get_by_role("button", name="下一页", exact=True).click()
        expect(page.locator(".reaction-options button")).to_have_count(42)
        expect(page.locator(".reaction-browser .pager")).to_contain_text("第 2 / 2 页")
        with page.expect_download() as download:
            page.get_by_role("button", name="导出关联 JSON", exact=True).click()
        download.value.save_as(str(output / "exported-trace.json"))
        exported = json.loads((output / "exported-trace.json").read_text(encoding="utf-8"))
        assert exported["run_id"] == acd and len(exported["reactions"]) == 92
        assert exported["database_provenance"] == data["database_provenance"]
        checks.append("92 reactions accessible over two pages and complete provenance-preserving JSON export")
        # Find a scored task with the 46-gene complex from the frozen association record.
        frozen = json.loads(
            (root / "data/derived/runs" / acd / "task_trace.json").read_text(encoding="utf-8")
        )
        complex_task = next(
            row["id"] for row in frozen["tasks"].values() if "NADH2_u10m" in row["reaction_ids"]
        )
        page.get_by_label("搜索功能任务").fill(complex_task)
        page.locator(".task-option").filter(has_text=complex_task).first.click()
        wait_trace(complex_task)
        page.locator('[data-reaction="NADH2_u10m"]').click()
        expect(page.locator('[data-source="predicted"] [data-node^="gene:"]')).to_have_count(46)
        expect(page.locator(".gpr-detail summary")).to_have_text("全部关联基因（46）")
        compare_coordinates()
        checks.append("All 46 genes retained in the complex, matching layout without the old 30-gene limit")
        page.get_by_label("搜索功能任务").fill("glycolysis")
        page.locator(".task-option").first.click()
        expect(page.locator(".function-node").first).to_be_visible()
        for width in [1920, 1440, 900, 390]:
            page.set_viewport_size({"width": width, "height": 1000})
            expect(page.locator(".network-panel").first).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
            page.evaluate("window.scrollTo(0,0)")
            page.screenshot(path=str(output / f"ACD-function-{width}.png"), full_page=True)
        checks.append("No page overflow at 1920, 1440, 900 and 390 pixels; screenshots inspected")
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(args.url + f"/workbench?run={acd}", wait_until="networkidle")
        expect(page.locator(".projection-preview")).not_to_have_attribute("open", "")
        expect(page.get_by_role("link", name="查看功能前后对比", exact=False)).to_be_visible()
        page.locator(".projection-preview > summary").click()
        expect(page.locator(".state-population")).to_have_count(2)
        checks.append("Functional entry on overview and auxiliary projection still expandable")
        open_run(replays["HepG2"], "demo", "&step=2")
        expect(page.locator(".demo-source")).to_contain_text("真实结果回放")
        svg_gene = page.locator('[data-source="predicted"] [data-node^="gene:"]').first
        svg_gene.focus()
        svg_gene.press("Space")
        assert "step=2" in page.url
        # Global demo keyboard handling must not hijack SVG node activation.
        expect(page.get_by_role("button", name="暂停演示", exact=False)).to_have_count(0)
        checks.append(
            "Demo metabolic chapter uses the same functional view and preserves node keyboard activation"
        )

        # Legacy synthetic results retain task numbers with an explicit unavailable network.
        page.goto(args.url + "/workbench?run=run_b69b0a932fa84675&tab=function", wait_until="networkidle")
        expect(page.locator(".function-workspace")).to_contain_text("合成样例用于展示交互")
        expect(page.locator(".function-workspace")).to_contain_text("功能网络不可用")
        expect(page.locator(".function-node")).to_have_count(0)
        expect(page.locator('[data-score="predicted"]')).to_have_count(1)
        checks.append("Legacy synthetic results have explicit labels and no fabricated real network")

        # Inject a trace error to verify local retry without changing the saved files.
        expected_errors.add("/task-trace")

        def broken(route):
            route.fulfill(
                status=500, json={"detail": {"code": "INVALID_TASK_TRACE", "message": "测试：关联记录损坏"}}
            )

        page.route("**/task-trace?*", broken)
        page.goto(args.url + f"/workbench?run={acd}&tab=function", wait_until="networkidle")
        expect(page.locator(".network-message")).to_contain_text("测试：关联记录损坏")
        expect(page.locator(".task-option")).to_have_count(50)
        expect(page.locator('[data-score="predicted"]')).not_to_have_text("未提供")
        page.unroute("**/task-trace?*", broken)
        page.get_by_role("button", name="重试功能关联", exact=True).click()
        expect(page.locator(".function-node").first).to_be_visible()
        expected_errors.clear()
        checks.append("Local trace failure preserves task scores and retry restores the network")

        # Hold the first switched task request, switch again, then release the stale response.
        pending = []

        def delayed(route):
            if not pending:
                pending.append(route)
            else:
                route.continue_()

        original = page.locator(".task-option.active").get_attribute("data-task")
        page.route("**/task-trace?*", delayed)
        buttons = page.locator(".task-option")
        buttons.nth(1).click()
        expect(page.locator(".network-message")).to_contain_text("正在读取完整功能关联")
        new_task = buttons.nth(2).get_attribute("data-task")
        buttons.nth(2).click()
        wait_trace(new_task)
        assert pending and new_task != original
        stale = load_trace(acd, buttons.nth(1).get_attribute("data-task"))
        try:
            pending[0].fulfill(json=stale)
        except Error as error:
            assert "Invalid" in str(error) or "closed" in str(error) or "cancel" in str(error)
        page.unroute("**/task-trace?*", delayed)
        page.wait_for_load_state("networkidle")
        wait_trace(new_task)
        checks.append("Aborted stale task response cannot overwrite the newly selected task")
        assert not errors, errors
        assert not failed, failed
        browser.close()
    (output / "checks.json").write_text(
        json.dumps(
            {"checks": checks, "page_errors": errors, "unexpected_http_errors": failed},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"checks": len(checks), "page_errors": errors, "unexpected_http_errors": failed},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
