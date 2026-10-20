"""Verify prediction display filtering on real runs and isolated browser fixtures."""

import argparse
import copy
import csv
import io
import json
import math
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from scripts.check_umap_overview import digest_outputs


def changed(row):
    try:
        return (
            all(
                row.get(key) is not None and math.isfinite(float(row[key]))
                for key in ("control", "predicted", "predicted_delta")
            )
            and float(row["predicted_delta"]) != 0
        )
    except (ValueError, TypeError):
        return False


def scored_genes(trace):
    if not changed(trace["task"]):
        return []
    return sorted({g["id"] for r in trace["reactions"] if changed(r) for g in r["genes"] if changed(g)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--check-projection", action="store_true")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    root = Path(__file__).resolve().parents[1]
    output = root / "reports/evidence-display-2026-10-12" / base.rsplit(":", 1)[-1]
    output.mkdir(parents=True, exist_ok=True)
    checks, errors, traces = [], [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1000}, reduced_motion="reduce")
        page.on("pageerror", lambda error: errors.append(str(error)))

        def capture(response):
            if "/task-trace?" in response.url and "scope=all" in response.url and response.ok:
                doc = response.json()
                traces[(doc["run_id"], doc["task"]["id"])] = doc

        page.on("response", capture)
        history = page.request.get(base + "/api/v1/experiments").json()
        records = [r for r in history["items"] if r["source"] == "online" and r["status"] == "completed"][:2]
        assert len(records) == 2
        before = {r["id"]: digest_outputs(root, r["id"]) for r in records}
        for record in records:
            run = record["id"]
            api = base + f"/api/v1/runs/{run}"
            genes = page.request.get(api + "/genes?limit=5000").json()["items"]
            tasks = page.request.get(api + "/metabolic-tasks?scope=all&limit=1000").json()["items"]
            reactions = page.request.get(api + "/reactions?limit=1000").json()["items"]
            page.goto(base + f"/demo?run={run}&tab=genes", wait_until="networkidle")
            expect(page.locator('[data-prediction-policy="complete-nonzero"]')).to_have_count(0)
            expect(page.locator(".pager").first).to_contain_text(f"共 {sum(map(changed, genes))} 条")
            assert page.get_by_role("columnheader", name="观测", exact=True).count() == 0
            with page.expect_download() as download:
                page.get_by_role("button", name="导出全部已加载 CSV", exact=True).click()
            csv_file = output / download.value.suggested_filename
            download.value.save_as(csv_file)
            rows = list(csv.DictReader(io.StringIO(csv_file.read_text(encoding="utf-8-sig"))))
            assert len(rows) == sum(map(changed, genes)) and all(map(changed, rows))
            assert "observed" not in rows[0]
            page.goto(base + f"/demo?run={run}&tab=metabolism&view=data", wait_until="networkidle")
            expect(page.locator(".metabolism .pager").nth(0)).to_contain_text(
                f"共 {sum(map(changed, tasks))} 条"
            )
            expect(page.locator(".metabolism .pager").nth(1)).to_contain_text(
                f"共 {sum(map(changed, reactions))} 条"
            )
            expect(page.get_by_text("正在读取冻结关联…", exact=True)).to_have_count(0, timeout=60000)
            for row in page.locator(".metabolism table").first.locator("tbody tr").all():
                task_id = row.locator(".faint.mono").inner_text()
                expected = scored_genes(traces[(run, task_id)])
                if expected:
                    assert row.locator(".task-associated-genes>span").text_content() == ", ".join(expected)
                else:
                    assert row.locator(".task-associated-genes").count() == 0
            page.get_by_role("button", name="查看任务：Gluconeogenesis from Glycerol", exact=True).click()
            expect(page.locator(".trace-gene")).to_have_count(1, timeout=30000)
            expect(page.locator(".trace-gene")).to_contain_text("TPI1")
            assert page.locator(".reaction-node").count() == 1
            assert all(
                name not in page.locator(".task-trace").inner_text()
                for name in ("ALDOA", "ALDOB", "ALDOC", "FBA", "未提供", "无有效表达值")
            )
            page.locator(".task-trace").screenshot(path=str(output / f"{run}-scored-trace.png"))
            if args.check_projection:
                page.goto(
                    base + f"/demo?run={run}&tab=metabolism&view=function", wait_until="domcontentloaded"
                )
                expect(page.locator(".scientific-figure img")).to_be_visible(timeout=120000)
                expect(page.locator(".scientific-figure figcaption")).to_contain_text("共同 UMAP")
                with page.expect_download() as download:
                    page.get_by_role("button", name="导出关联 JSON", exact=True).click()
                file = output / download.value.suggested_filename
                download.value.save_as(file)
                trace = json.loads(file.read_text(encoding="utf-8"))
                assert changed(trace["task"])
                assert all(
                    changed(r) and r["genes"] and all(map(changed, r["genes"])) and r["gene_rule"] is None
                    for r in trace["reactions"]
                )
                assert trace["determinant_genes"] == []
                page.locator(".association-evidence>summary").click()
                expect(page.locator(".gpr-detail .gene-link").first).to_be_visible()
                page.get_by_role("button", name="PCA", exact=True).click()
                expect(page.locator(".scientific-figure figcaption")).to_contain_text(
                    "共同对照参考 PCA", timeout=120000
                )
            checks.append(
                {
                    "run": run,
                    "genes": sum(map(changed, genes)),
                    "tasks": sum(map(changed, tasks)),
                    "reactions": sum(map(changed, reactions)),
                }
            )

        # Only intercepted browser responses are modified; no results or server state are written.
        run = records[0]["id"]
        page.goto(base + f"/demo?run={run}&tab=cell", wait_until="domcontentloaded")
        expect(page.locator(".scientific-figure img")).to_be_visible(timeout=120000)
        expect(page.locator('[aria-label="选择逐细胞指标"] option')).to_have_count(2000)
        page.get_by_label("指标类型", exact=True).select_option("task")
        expect(page.locator('[aria-label="选择逐细胞指标"] option')).to_have_count(141, timeout=60000)
        expect(page.locator(".scientific-figure img")).to_be_visible(timeout=120000)
        checks.append({"direct_cell_tab": "eligible gene/task options load without opening other tabs"})

        def incomplete_genes(route):
            doc = route.fetch().json()
            for index, values in enumerate(({"control": None}, {"predicted": "NaN"}, {"predicted_delta": 0})):
                doc["items"][index].update(values, gene=f"EXCLUDED_GENE_{index}")
            route.fulfill(json=doc)

        page.route("**/genes?*", incomplete_genes)
        page.goto(base + f"/demo?run={run}&tab=genes", wait_until="networkidle")
        page.get_by_placeholder("搜索基因符号（仅覆盖已加载记录）").fill("EXCLUDED_GENE")
        expect(page.locator(".table-tools")).to_contain_text("0 / 1997 条")
        with page.expect_download() as download:
            page.get_by_role("button", name="导出全部已加载 CSV", exact=True).click()
        target = output / "fixture-filtered-genes.csv"
        download.value.save_as(target)
        assert "EXCLUDED_GENE" not in target.read_text(encoding="utf-8-sig")
        page.unroute("**/genes?*", incomplete_genes)

        def incomplete_tasks(route):
            doc = route.fetch().json()
            doc["items"] = copy.deepcopy(doc["items"])
            for index, values in enumerate(
                ({"control": None}, {"predicted": "Infinity"}, {"predicted_delta": 0})
            ):
                doc["items"][index].update(
                    values, id=f"EXCLUDED_TASK_{index}", label=f"EXCLUDED_TASK_{index}"
                )
            route.fulfill(json=doc)

        page.route("**/metabolic-tasks?*", incomplete_tasks)
        page.goto(base + f"/demo?run={run}&tab=metabolism&view=data", wait_until="networkidle")
        expect(page.locator(".metabolism .pager").first).to_contain_text("共 138 条")
        page.get_by_placeholder("搜索任务名或任务 ID").fill("EXCLUDED_TASK")
        expect(page.locator(".task-filter-status")).to_contain_text("匹配 0 项")
        page.unroute("**/metabolic-tasks?*", incomplete_tasks)
        checks.append({"browser_fixtures": "missing/nonfinite/zero rows excluded from lists and CSV"})
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
