"""Check real observed-data availability and frozen gene associations against the live service."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from scripts.check_prediction_evidence_frontend import scored_genes
from scripts.check_umap_overview import digest_outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    base = parser.parse_args().url.rstrip("/")
    root = Path(__file__).resolve().parents[1]
    output = root / "reports/missing-result-fields-2026-10-12"
    output.mkdir(parents=True, exist_ok=True)
    errors, checks, traces = [], [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))

        def capture_trace(response):
            if "/task-trace?" in response.url and "scope=all" in response.url and response.ok:
                doc = response.json()
                traces[(doc["run_id"], doc["task"]["id"])] = doc

        page.on("response", capture_trace)
        history = page.request.get(base + "/api/v1/experiments").json()
        records = [r for r in history["items"] if r["source"] == "online" and r["status"] == "completed"][:2]
        assert records
        before = {r["id"]: digest_outputs(root, r["id"]) for r in records}
        for record in records:
            run = record["id"]
            raw = page.request.get(base + f"/api/v1/runs/{run}/genes").json()["items"]
            assert all(row.get("observed") is None and row.get("observed_delta") is None for row in raw)
            page.goto(base + f"/demo?run={run}&tab=genes", wait_until="networkidle")
            expect(page.get_by_role("columnheader", name="基因", exact=True)).to_be_visible()
            assert page.get_by_role("columnheader", name="观测", exact=True).count() == 0
            assert page.get_by_role("columnheader", name="观测变化", exact=True).count() == 0
            expect(page.locator('[data-evidence="no-observed"]')).to_contain_text("没有扰动后实测数据")
            cells = page.locator("table tbody tr").first.locator("td").all_text_contents()
            expected = next(row for row in raw if row["gene"] == cells[0])
            assert len(cells) == 4
            for index, key in enumerate(("control", "predicted", "predicted_delta"), 1):
                assert abs(float(cells[index]) - float(expected[key])) < 0.00011
            assert page.locator(".expression-value").count() == 2
            page.screenshot(path=str(output / f"{run}-genes.png"), full_page=True)
            page.goto(base + f"/demo?run={run}&tab=metabolism&view=data", wait_until="networkidle")
            expect(page.locator(".task-associated-genes")).to_have_count(20, timeout=60000)
            assert page.get_by_text("关联基因尚未提供", exact=True).count() == 0
            assert page.get_by_role("columnheader", name="观测变化", exact=True).count() == 0
            task_rows = page.locator(".metabolism table").first.locator("tbody tr")
            for row in task_rows.all():
                task_id = row.locator(".faint.mono").inner_text()
                expected_trace = traces[(run, task_id)]
                genes = scored_genes(expected_trace)
                assert not expected_trace["determinant_genes"] and genes
                actual_genes = row.locator(".task-associated-genes>span").text_content()
                assert actual_genes == ", ".join(genes), (task_id, actual_genes, genes)
            task_rows.first.locator(".task-associated-genes>summary").click()
            page.screenshot(path=str(output / f"{run}-metabolism.png"), full_page=True)
            page.get_by_role("button", name="查看任务：Gluconeogenesis from Glycerol", exact=True).click()
            expect(page.locator(".trace-gene")).to_have_count(1, timeout=30000)
            expect(page.locator(".trace-gene")).to_contain_text("TPI1")
            assert "本次无有效表达值" not in page.locator(".task-trace").inner_text()
            assert "本次无有效反应分数" not in page.locator(".task-trace").inner_text()
            page.get_by_role("button", name="下一页", exact=True).first.click()
            expect(page.locator(".task-associated-genes")).to_have_count(20, timeout=60000)
            checks.append(
                run + ": complete saved numeric fields, no blank observed columns, real frozen associations"
            )

        # Browser-only fixtures verify that real observed values remain visible,
        # and unreadable traces produce an error rather than fake gene names.
        run = records[0]["id"]

        def with_observed(route):
            doc = route.fetch().json()
            doc["items"][0].update(observed="1.234", observed_delta="0.123")
            route.fulfill(json=doc)

        page.route("**/genes?*", with_observed)
        page.goto(base + f"/demo?run={run}&tab=genes", wait_until="networkidle")
        expect(page.get_by_role("columnheader", name="观测", exact=True)).to_be_visible()
        expect(page.get_by_role("columnheader", name="观测变化", exact=True)).to_be_visible()
        page.get_by_placeholder("搜索基因符号（仅覆盖已加载记录）").fill("HES4")
        expect(page.locator("table tbody tr")).to_have_count(1)
        expect(page.locator("table tbody tr td").nth(4)).to_have_text("1.234")
        page.unroute("**/genes?*", with_observed)

        def broken_trace(route):
            route.fulfill(
                status=500,
                json={"detail": {"code": "INVALID_TASK_TRACE", "message": "fixture corrupted trace"}},
            )

        page.route("**/task-trace?*", broken_trace)
        page.goto(base + f"/demo?run={run}&tab=metabolism&view=data", wait_until="networkidle")
        expect(page.get_by_role("button", name="关联读取失败 · 重试", exact=True)).to_have_count(20)
        assert page.locator(".task-associated-genes").count() == 0
        page.unroute("**/task-trace?*", broken_trace)
        checks.append(
            "Browser-only fixtures: observed values preserved; corrupt traces never replaced by attribution"
        )
        assert not errors, errors
        assert history == page.request.get(base + "/api/v1/experiments").json()
        assert before == {r["id"]: digest_outputs(root, r["id"]) for r in records}
        browser.close()
    output.joinpath("acceptance.json").write_text(
        json.dumps(
            {
                "checks": checks,
                "browser_errors": errors,
                "frozen_outputs_unchanged": True,
                "experiment_history_unchanged": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(checks, ensure_ascii=False))


if __name__ == "__main__":
    main()
