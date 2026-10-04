"""Capture actual pages; optionally verify the production SPA and lazy scene assets."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://127.0.0.1:5173")
parser.add_argument("--smoke", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
out = root / "docs/design/2026-10-04-celllens/actual"
out.mkdir(parents=True, exist_ok=True)
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(args.url + "/workbench", wait_until="networkidle")
    expect(page.locator(".viewport-live")).to_have_text("3D", timeout=20000)
    page.screenshot(path=str(out / "workbench.png"), full_page=True)
    if args.smoke:
        run_id = None
        directories = sorted(
            (root / "data/derived/runs").glob("run_*"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for directory in directories:
            response = page.request.get(args.url + "/api/v1/runs/" + directory.name)
            if response.ok and response.json().get("status") == "completed":
                run_id = directory.name
                break
        assert run_id, "No completed run found"
        target = args.url + "/demo?run=" + run_id + "&step=2"
        page.goto(target, wait_until="networkidle")
        expect(page.locator(".viewport-live")).to_have_text("3D", timeout=20000)
        expect(page.locator(".demo-task").first).to_be_visible()
        page.reload(wait_until="networkidle")
        expect(page.locator(".demo-title h1")).to_contain_text("功能响应")
        page.locator(".demo-title h1").click()
        page.keyboard.press("Escape")
        expect(page).to_have_url(args.url + "/runs/" + run_id + "?tab=structure")
        expect(page.locator(".viewport-live")).to_have_text("3D", timeout=20000)
        page.get_by_role("tab", name="表达空间", exact=True).click()
        expect(page.get_by_role("img", name="二维随机投影散点图")).to_be_visible()
        page.get_by_role("tab", name="基因响应", exact=True).click()
        expect(page.locator("#gene-search")).to_be_visible()
        page.screenshot(path=str(out / "gene-analysis.png"), full_page=True)
        assert not errors, errors
        result = {
            "url": args.url,
            "run_id": run_id,
            "spa_refresh": True,
            "lazy_scene": True,
            "real_projection_and_genes": True,
            "pageerrors": errors,
        }
        (out / "production-checks.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False))
    else:
        print("WebGL ready; actual workbench captured; pageerrors:", errors)
    browser.close()
