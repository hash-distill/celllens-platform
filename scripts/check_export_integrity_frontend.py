"""Read-only browser regression for complete trace and feature-specific filenames."""

import argparse
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--run", default="run_41504106326f404d")
    parser.add_argument("--phase", default="green")
    parser.add_argument(
        "--figures",
        action="store_true",
        help="Also verify real backend SVG/PDF/PNG feature filenames after backend restart",
    )
    args = parser.parse_args()
    out = Path(__file__).resolve().parents[1] / "reports/export-fixes-2026-10-22/frontend" / args.phase
    out.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.route(
            "**/api/**",
            lambda route: route.continue_() if route.request.method in ("GET", "HEAD") else route.abort(),
        )
        page.goto(f"{args.url}/demo?run={args.run}&tab=metabolism&view=function", wait_until="networkidle")
        search = page.get_by_label("搜索功能任务", exact=True)
        search.fill("Synthesis of kynate from tryptophan")
        button = page.get_by_role("button", name=re.compile("导出.*关联.*JSON"))
        expect(button).to_be_enabled(timeout=60000)
        raw = page.request.get(
            f"{args.url}/api/v1/runs/{args.run}/task-trace",
            params={"task_id": "Synthesis of kynate from tryptophan", "scope": "all"},
        ).json()
        with page.expect_download() as pending:
            button.click()
        target = out / "trace.json"
        pending.value.save_as(target)
        doc = json.loads(target.read_text(encoding="utf8"))
        mismatch = [key for key in raw if doc.get(key) != raw[key]]
        checks.append(
            {
                "check": "F1 raw trace including GPR retained",
                "passed": not mismatch,
                "mismatched_fields": mismatch,
                "raw_reactions": len(raw["reactions"]),
                "exported_reactions": len(doc["reactions"]),
            }
        )
        # Delay one browser-only trace response, switch back, and ensure it cannot leak.
        tasks = page.request.get(
            f"{args.url}/api/v1/runs/{args.run}/metabolic-tasks", params={"scope": "all", "limit": 1000}
        ).json()["items"]
        other = next(
            task
            for task in tasks
            if task["id"] != raw["task"]["id"]
            and all(
                isinstance(task.get(key), (int, float)) for key in ("control", "predicted", "predicted_delta")
            )
            and task["predicted_delta"] != 0
        )
        other_raw = page.request.get(
            f"{args.url}/api/v1/runs/{args.run}/task-trace", params={"task_id": other["id"], "scope": "all"}
        ).json()
        held = []

        def delay_trace(route):
            query = parse_qs(urlparse(route.request.url).query)
            if query.get("scope") == ["all"] and query.get("task_id") == [other["id"]]:
                held.append(route)
            else:
                route.continue_()

        page.route("**/task-trace?*", delay_trace)
        search.fill(other["id"])
        expect(button).to_be_disabled()
        search.fill(raw["task"]["id"])
        expect(button).to_be_enabled(timeout=60000)
        assert held
        try:
            held[0].fulfill(json=other_raw)
        except Exception:
            pass  # Chromium can discard an aborted response before fulfilment.
        with page.expect_download() as pending:
            button.click()
        pending.value.save_as(out / "trace-after-switch.json")
        after = json.loads((out / "trace-after-switch.json").read_text(encoding="utf8"))
        checks.append(
            {
                "check": "F1 task switch clears export until loaded and discards late prior trace",
                "passed": all(after[key] == raw[key] for key in raw),
            }
        )
        page.unroute("**/task-trace?*", delay_trace)
        filenames = []
        figure_filenames = {kind: [] for kind in ("svg", "pdf", "png")}
        page.goto(f"{args.url}/demo?run={args.run}&tab=cell", wait_until="networkidle")
        select = page.get_by_label("选择逐细胞指标", exact=True)
        expect(page.locator(".scientific-figure img")).to_be_visible(timeout=120000)
        options = select.locator("option").evaluate_all("rows => rows.map(row=>row.value)")
        for feature in options[:2]:
            select.select_option(feature)
            expect(page.locator(".scientific-figure img")).to_be_visible(timeout=120000)
            expect(page.locator(".state-numbers h3")).to_contain_text(feature)
            with page.expect_download() as pending:
                page.get_by_role("button", name="导出 JSON", exact=True).click()
            download = pending.value
            filenames.append(download.suggested_filename)
            download.save_as(out / f"{feature}.json")
            if args.figures:
                for kind in figure_filenames:
                    with page.expect_download(timeout=120000) as pending:
                        page.get_by_role("button", name="导出 " + kind.upper(), exact=True).click()
                    download = pending.value
                    figure_filenames[kind].append(download.suggested_filename)
                    download.save_as(out / download.suggested_filename)
        checks.append(
            {
                "check": "F4 different feature filenames remain distinct",
                "passed": len(set(filenames)) == 2,
                "filenames": filenames,
            }
        )
        if args.figures:
            checks.append(
                {
                    "check": "F4 backend SVG/PDF/PNG feature filenames remain distinct",
                    "passed": all(len(set(names)) == 2 for names in figure_filenames.values()),
                    "filenames": figure_filenames,
                }
            )
        page.goto(f"{args.url}/methods/coverage", wait_until="networkidle")
        page.locator(".coverage-method>summary").click()
        with page.expect_download() as pending:
            page.get_by_role("button", name="下载关联基因与任务 JSON", exact=True).click()
        pending.value.save_as(out / "coverage.json")
        coverage = json.loads((out / "coverage.json").read_text(encoding="utf8"))
        ids = {row["id"] for row in coverage["reactions"]}
        omitted = {row["id"] for row in coverage.get("omitted_references", {}).get("reactions", [])}
        missing = {ref for gene in coverage["genes"] for ref in gene["reactions"]} - ids - omitted
        checks.append(
            {
                "check": "coverage reaction references resolve or declare omission",
                "passed": not missing,
                "unresolved": len(missing),
            }
        )
        browser.close()
    result = {"checks": checks, "page_errors": errors}
    (out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(result, ensure_ascii=False))
    assert all(check["passed"] for check in checks) and not errors, result


if __name__ == "__main__":
    main()
