"""Read-only checks for control provenance, live counts and prediction-sampling guidance."""

import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default="reports/control-sampling-2026-10-22/frontend")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1100}, reduced_motion="reduce")
        context.add_init_script("localStorage.setItem('celllens.theme','light')")
        page = context.new_page()
        page.set_default_navigation_timeout(120000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route(
            "**/api/**",
            lambda route: route.continue_() if route.request.method in ("GET", "HEAD") else route.abort(),
        )
        page.goto(args.url + "/methods/backgrounds?cell_line=K562", wait_until="networkidle")
        section = page.locator("#control-sampling")
        expect(section).to_be_visible()
        for name, count in (("K562", 1024), ("RPE1", 1024), ("Jurkat", 1024), ("HepG2", 1024)):
            page.locator(".background-choice").filter(has_text=name).click()
            expect(section.locator("tbody")).to_contain_text(f"{count:,} 个 {name} 实测细胞")
            checks.append({"background": name, "control_cells": count})
        for text in ("non-targeting", "有放回取样", "不要求等量", "64–4096", "不保证更准确"):
            expect(section).to_contain_text(text)
        page.locator(".background-choice").filter(has_text="K562").click()
        page.screenshot(path=str(output / "data-sources-light.png"), full_page=True)
        assert (
            page.locator("main").evaluate("el=>getComputedStyle(el).backgroundColor") == "rgb(255, 255, 255)"
        )
        page.get_by_role("button", name="切换到深色模式", exact=True).click()
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        page.screenshot(path=str(output / "data-sources-dark.png"), full_page=True)
        page.get_by_role("button", name="切换到明亮模式", exact=True).click()
        checks.append(
            {"scope": "source and sampling explanation, white background and theme switch", "passed": True}
        )
        page.goto(args.url + "/workbench", wait_until="networkidle")
        expect(page.get_by_label("预测采样细胞数", exact=True)).to_be_visible()
        expect(page.locator("#n-cells-hint")).to_contain_text("不改变真实对照数")
        positions = page.locator("#n-cells-input,#seed-input").evaluate_all(
            "nodes=>nodes.map(el=>el.getBoundingClientRect().top)"
        )
        assert len(positions) == 2 and abs(positions[0] - positions[1]) <= 1, positions
        page.get_by_role("link", name="了解对照与采样", exact=True).click()
        page.wait_for_url(re.compile(r"/methods/backgrounds\?cell_line=K562#control-sampling"))
        expect(page.locator("#control-sampling")).to_be_visible()
        # Near the page end, the browser clamps scrolling before the anchor reaches 100px.
        page.wait_for_function(
            "(() => {const r=document.getElementById('control-sampling')?.getBoundingClientRect();"
            " return r && r.top>=70 && r.bottom<=window.innerHeight})()"
        )
        checks.append(
            {"scope": "parameter meaning, aligned inputs and context-specific anchor", "passed": True}
        )
        page.goto(args.url + "/methods/models", wait_until="networkidle")
        page.get_by_role("link", name="查看对照来源与采样说明 →", exact=True).click()
        page.wait_for_url(re.compile(r"/methods/backgrounds#control-sampling"))
        expect(page.locator("#control-sampling")).to_be_visible()
        checks.append({"scope": "model methods explanation link", "passed": True})

        def unknown_count(route):
            response = route.fetch()
            data = response.json()
            for item in data["contexts"]:
                item.update(control_cell_count=None, control_metadata_verified=False)
            route.fulfill(response=response, json=data)

        page.route("**/api/v1/catalog/data-summary", unknown_count)
        page.reload(wait_until="networkidle")
        expect(page.locator(".sampling-table tbody")).to_contain_text("当前数量暂未核验")
        checks.append({"scope": "fixture: unavailable metadata stays unknown", "passed": True})
        assert not errors, errors
        browser.close()
    result = {"checks": checks, "page_errors": errors, "new_experiments_submitted": False}
    root = Path(__file__).resolve().parents[1]
    baseline_path = root / "reports/control-sampling-2026-10-22/baseline.json"
    if baseline_path.is_file():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        after = {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (root / "data/derived/runs").rglob("*")
            if path.is_file()
        }
        assert after == baseline["hashes"], "Frozen experiment files changed"
        with urllib.request.urlopen(args.url + "/api/v1/experiments?limit=100") as response:
            assert json.load(response) == baseline["history"], "Experiment history changed"
        result.update(frozen_files_unchanged=len(after), history_unchanged=True)
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
