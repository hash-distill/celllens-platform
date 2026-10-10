"""Capture actual pages; optionally verify the production SPA and scientific result views."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://127.0.0.1:5173")
parser.add_argument("--smoke", action="store_true")
parser.add_argument("--run-id", help="Completed run with projection and expression artifacts")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
out = root / "reports" / "frontend" / "production"
out.mkdir(parents=True, exist_ok=True)
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(args.url + "/workbench", wait_until="networkidle")
    expect(page.get_by_role("heading", name="实验工作台", exact=True)).to_be_visible()
    page.screenshot(path=str(out / "workbench.png"), full_page=True)
    if args.smoke:
        run_id = args.run_id
        directories = sorted(
            (root / "data/derived/runs").glob("run_*"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for directory in directories:
            if run_id:
                break
            response = page.request.get(args.url + "/api/v1/runs/" + directory.name)
            if (
                response.ok
                and response.json().get("status") == "completed"
                and (directory / "projection.json").is_file()
                and (directory / "gene_deltas.csv").is_file()
            ):
                run_id = directory.name
                break
        assert run_id, "No completed run found"
        target = args.url + "/demo?run=" + run_id + "&step=2"
        page.goto(target, wait_until="networkidle")
        expect(page.locator(".task-row").first).to_be_visible()
        page.reload(wait_until="networkidle")
        expect(page.locator(".demo-title h1")).to_contain_text("功能响应")
        page.locator(".demo-title h1").click()
        page.keyboard.press("Escape")
        expect(page).to_have_url(args.url + "/workbench?run=" + run_id)
        page.goto(args.url + "/runs/" + run_id + "?tab=structure", wait_until="networkidle")
        expect(page.locator(".cell-viewport")).to_have_count(0)
        page.get_by_role("tab", name="单细胞状态", exact=True).click()
        expect(page.get_by_role("img", name="二维随机投影散点图").first).to_be_visible()
        page.get_by_role("tab", name="基因响应", exact=True).click()
        expect(page.locator("#gene-search")).to_be_visible()
        page.screenshot(path=str(out / "gene-analysis.png"), full_page=True)
        assert not errors, errors
        result = {
            "url": args.url,
            "run_id": run_id,
            "spa_refresh": True,
            "structure_removed": True,
            "real_projection_and_genes": True,
            "pageerrors": errors,
        }
        (out / "production-checks.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False))
    else:
        print("Response workbench captured; pageerrors:", errors)
    browser.close()
