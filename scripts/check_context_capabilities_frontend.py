"""Verify four-context capabilities against live API and production frontend."""

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
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    proof = root / "reports/four-context-capabilities-2026-10-09"
    output = proof / "browser"
    output.mkdir(exist_ok=True)
    replays = json.loads((proof / "replays.json").read_text(encoding="utf-8"))["items"]
    diagnoses = json.loads((proof / "diagnostics.json").read_text(encoding="utf-8"))["items"]
    metrics = {row["cell_line"]: row["expression"] for row in diagnoses}
    checks: list[str] = []
    errors: list[str] = []
    failed_api: list[str] = []
    expected_missing: set[str] = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("response", lambda response: failed_api.append(response.url)
                if response.status >= 400 and "/api/v1/" in response.url
                and not (response.status == 404 and response.url in expected_missing) else None)
        page.goto(args.url + "/workbench", wait_until="networkidle")
        catalog = page.request.get(args.url + "/api/v1/catalog/contexts").json()
        assert len(catalog) == 4
        for context in catalog:
            assert all(context[key] for key in ("online_ready", "precomputed_ready", "validation_ready"))
        for line in ["K562", "RPE1", "Jurkat", "HepG2"]:
            radio = page.locator(f'input[name="cell-line"][value="{line}"]')
            page.locator("label.choice").filter(has=radio).click()
            expect(radio).to_be_checked()
            page.wait_for_load_state("networkidle")
            for mode in ["online", "precomputed", "validation"]:
                print(f"checking selection {line}/{mode}", flush=True)
                mode_radio = page.locator(f'input[name="run-mode"][value="{mode}"]')
                expect(mode_radio).to_be_enabled()
                page.locator("label.choice").filter(has=mode_radio).click()
                page.wait_for_load_state("networkidle")
                query = page.get_by_placeholder("搜索扰动基因…")
                query.click()
                query.fill("ALDOA")
                expect(page.get_by_role("option", name="ALDOA", exact=True)).to_be_visible()
                page.get_by_role("option", name="ALDOA", exact=True).click()
                expect(page.get_by_role("button", name="开始实验", exact=True)).to_be_enabled()
                response = page.request.get(
                    args.url + f"/api/v1/catalog/perturbations?cell_line={line}&mode={mode}"
                )
                items = response.json()["items"]
                assert "ALDOA" in items
                if mode == "validation":
                    assert items == ["ALDOA"]
                    query.fill("AAMP")
                    expect(query).to_have_attribute("aria-expanded", "true")
                    expect(page.get_by_role("option")).to_have_count(0)
                    query.fill("ALDOA")
                    query.click()
                    expect(page.get_by_role("option", name="ALDOA", exact=True)).to_be_visible()
                    page.get_by_role("option", name="ALDOA", exact=True).click()
                    invalid = page.request.post(args.url + "/api/v1/runs", data={
                        "cell_line": line, "perturbation": "AAMP", "mode": mode,
                        "n_cells": 64, "seed": 42,
                    })
                    assert invalid.status == 422
                    assert invalid.json()["detail"]["code"] == "DIAGNOSTIC_UNAVAILABLE"
            checks.append(f"{line}: three modes, real catalog, ALDOA selection and diagnostic gate")
        for width in [2048, 1440, 900, 390]:
            page.set_viewport_size({"width": width, "height": 1000})
            boxes = page.locator(".cell-choice-group label").evaluate_all(
                "xs => xs.map(x => { const r=x.getBoundingClientRect(); "
                "return {x:r.x,y:r.y,w:r.width,h:r.height} })"
            )
            assert len(boxes) == 4
            assert max(b["w"] for b in boxes) - min(b["w"] for b in boxes) < 1
            assert max(b["h"] for b in boxes) - min(b["h"] for b in boxes) < 1
            assert abs(boxes[0]["y"] - boxes[1]["y"]) < 1
            assert abs(boxes[2]["y"] - boxes[3]["y"]) < 1
            assert boxes[2]["y"] > boxes[0]["y"]
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(output / f"settings-{width}.png"), full_page=True)
        checks.append("equal 2 by 2 background cards at 2048, 1440, 900 and 390 pixels")
        page.set_viewport_size({"width": 1440, "height": 1000})
        for replay in replays:
            line, run_id = replay["cell_line"], replay["run_id"]
            page.goto(args.url + f"/workbench?run={run_id}", wait_until="networkidle")
            expect(page.locator(".active-experiment")).to_contain_text(line + " / ALDOA")
            expect(page.locator(".active-experiment")).to_contain_text("真实结果回放（本次未重新计算）")
            expect(page.locator(".gene-row").first).to_be_visible()
            expect(page.locator(".task-row").first).to_be_visible()
            expand_projection(page)
            expect(page.locator(".state-population")).to_have_count(3)
            expect(page.locator(".workspace-results")).not_to_contain_text("合成参考")
            page.screenshot(path=str(output / f"{line}-response.png"), full_page=True)
            page.locator(".run-evidence > summary").click()
            expect(page.locator(".run-evidence")).to_contain_text(replay["source_run_id"])
            source_link = f'.run-evidence a[href="/workbench?run={replay["source_run_id"]}"]'
            expect(page.locator(source_link)).to_be_visible()
            page.get_by_role("tab", name="预测验证", exact=True).click()
            card = page.get_by_label("STATE 表达预测验证")
            ratio = str(round(metrics[line]["mse_relative_to_no_change"], 4))
            expect(card).to_contain_text(ratio)
            expect(card).to_contain_text("尚未完成独立留出验收")
            expect(page.locator(".validation")).not_to_contain_text("合成参考值")
            report = page.request.get(args.url + f"/api/v1/runs/{run_id}/report")
            assert report.ok and "真实结果回放（本次未重新计算）" in report.text()
            page.screenshot(path=str(output / f"{line}-diagnostic.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            expect(card).to_be_visible()
            page.wait_for_function("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(output / f"{line}-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})
            for step in [0, 1, 2, 3]:
                page.goto(args.url + f"/demo?run={run_id}&step={step}", wait_until="networkidle")
                expect(page.locator(".demo-source")).to_contain_text("真实结果回放")
                if step == 0:
                    expect(page.locator(".demo-experiment")).to_contain_text(line + " / ALDOA")
                    expect(page.locator(".demo-experiment")).to_contain_text("读取已保存结果")
                elif step == 1:
                    expect(page.locator(".gene-row").first).to_be_visible()
                elif step == 2:
                    expect(page.locator(".function-node").first).to_be_visible()
                else:
                    expect(page.get_by_label("STATE 表达预测验证")).to_contain_text(ratio)
                expect(page.locator(".demo-stage")).not_to_contain_text("合成参考值")
            checks.append(f"{line}: three populations, source, metrics, report, demo and mobile")
        page.goto(args.url + "/records", wait_until="networkidle")
        expect(page.locator("body")).to_contain_text("真实结果回放（本次未重新计算）")
        legacy = page.request.get(args.url + "/api/v1/runs?mode=precomputed&limit=100").json()["items"]
        synthetic = next(row for row in legacy if row["request"]["perturbation"] == "MYC")
        expected_missing.add(args.url + "/api/v1/runs/" + synthetic["run_id"] + "/validation")
        page.goto(
            args.url + "/workbench?run=" + synthetic["run_id"] + "&tab=validation", wait_until="networkidle"
        )
        expect(page.locator(".validation")).to_contain_text("合成参考值")
        checks.append("server history labels true replay; old K562/MYC remains synthetic")
        assert not errors, errors
        assert not failed_api, failed_api
        browser.close()
    result = {"checks": checks, "page_errors": errors, "failed_page_api": failed_api,
              "expected_optional_404": sorted(expected_missing)}
    (output / "checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
