"""Check projection availability for all completed runs and render old/new demo experiments."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    out = Path(__file__).resolve().parents[1] / "reports/frontend/projection"
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.set_default_timeout(15000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        base = args.url
        listing = page.request.get(base + "/api/v1/runs?status=completed&limit=100").json()
        runs = listing["items"]
        for offset in range(100, listing["total"], 100):
            runs.extend(
                page.request.get(base + f"/api/v1/runs?status=completed&limit=100&offset={offset}").json()[
                    "items"
                ]
            )
        checks = []
        for record in runs:
            response = page.request.get(base + f"/api/v1/runs/{record['run_id']}/projection")
            assert response.status == 200, (record["run_id"], response.text())
            projection = response.json()
            counts = {
                source: sum(point["source"] == source for point in projection["points"])
                for source in ["control", "predicted", "observed"]
            }
            assert counts["control"] > 0 and counts["predicted"] > 0
            if record["request"]["mode"] == "precomputed":
                assert projection["data_kind"] == "synthetic_demo"
                assert projection["input_sha256"]
            checks.append({"run_id": record["run_id"], "mode": record["request"]["mode"], "counts": counts})
        historical = next(record["run_id"] for record in runs if record["request"]["mode"] == "precomputed")
        page.goto(base + "/workbench?run=" + historical + "&tab=cell", wait_until="networkidle")
        expect(page.locator(".state-population")).to_have_count(2)
        expect(page.get_by_role("heading", name="合成对照群体", exact=False)).to_be_visible()
        expect(page.get_by_role("heading", name="合成扰动后群体", exact=False)).to_be_visible()
        expect(page.get_by_text("本次结果未提供二维投影", exact=True)).to_have_count(0)
        expect(page.locator(".notice-warn")).to_contain_text("不是 STATE 预测")
        expect(page.locator(".notice-warn")).to_contain_text("原始结果保留")
        page.screenshot(path=str(out / "historical-demo.png"), full_page=True)
        page.get_by_role("button", name="叠加比较", exact=True).click()
        expect(page.locator(".projection-chart")).to_have_count(1)
        page.get_by_role("button", name="并排比较", exact=True).click()
        page.reload(wait_until="networkidle")
        expect(page.locator(".state-population")).to_have_count(2)

        created_response = page.request.post(
            base + "/api/v1/runs",
            data={
                "cell_line": "K562",
                "perturbation": "MYC",
                "mode": "precomputed",
                "n_cells": 512,
                "seed": 42,
            },
        )
        assert created_response.status == 202, created_response.text()
        created = created_response.json()
        page.goto(base + "/workbench?run=" + created["run_id"], wait_until="networkidle")
        expect(page.locator(".state-population")).to_have_count(2)
        expect(page.locator(".state-overview")).to_contain_text("512 个显示点")
        expect(page.get_by_text("本次结果未提供二维投影", exact=True)).to_have_count(0)
        page.screenshot(path=str(out / "new-demo.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 900})
        page.reload(wait_until="networkidle")
        expect(page.locator(".state-population")).to_have_count(2)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(out / "demo-mobile.png"), full_page=True)
        assert not errors, errors
        report = {
            "completed_runs": checks,
            "historical_demo": historical,
            "new_demo": created,
            "overlay_reload_mobile": True,
            "page_errors": errors,
        }
        (out / "checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
