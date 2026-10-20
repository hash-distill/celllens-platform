"""Check published expression reanalyses and real diagnostic pages."""

import json

import httpx
from playwright.sync_api import expect, sync_playwright

from backend.app.core.run_manifest import file_sha256
from scripts.reanalyse_expression_v2 import PROOF, ROOT, assert_originals


def main() -> None:
    base = "http://127.0.0.1:8001"
    reanalyses = json.loads((PROOF / "reanalysis.json").read_text())["items"]
    diagnostics = json.loads((PROOF / "expression-diagnostics.json").read_text())["items"]
    assert_originals(json.loads((PROOF / "baseline.json").read_text()))
    endpoints = [
        "summary",
        "projection",
        "genes",
        "metabolic-tasks?scope=all",
        "reactions",
        "completeness",
        "provenance",
    ]
    checked = []
    with httpx.Client(base_url=base, timeout=30) as client:
        assert client.get("/api/v1/health").json()["database"] == "ok"
        for item in reanalyses + diagnostics:
            run_id = item["new_run_id"]
            prefix = f"/api/v1/runs/{run_id}"
            assert client.get(prefix).json()["status"] == "completed"
            for endpoint in endpoints:
                response = client.get(prefix + "/" + endpoint)
                assert response.status_code == 200, (run_id, endpoint, response.text)
                assert response.json()
            assert client.get(prefix + "/summary").json()["warnings"] == []
            provenance = client.get(prefix + "/provenance").json()
            assert provenance["prediction_reused"]
            assert provenance["reanalysis_of"] == item["source_run_id"]
            directory = ROOT / "data/derived/runs" / run_id
            original_prediction = ROOT / "data/derived/runs" / item["source_run_id"] / "predicted.h5ad"
            assert file_sha256(directory / "predicted.h5ad") == file_sha256(original_prediction)
            manifest = json.loads((directory / "manifest.json").read_text())
            for name, info in manifest["outputs"].items():
                assert file_sha256(directory / name) == info["sha256"]
            checked.append(run_id)
        for item in diagnostics:
            payload = client.get(f"/api/v1/runs/{item['new_run_id']}/validation").json()
            assert payload["expression"] == item["expression"]
            assert payload["held_out_validation"] is False
    out = ROOT / "output/playwright/expression-v2"
    out.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        for item in diagnostics:
            context = item["request"]["cell_line"]
            page.goto(f"{base}/workbench?run={item['new_run_id']}&tab=validation", wait_until="networkidle")
            card = page.get_by_role("region", name="STATE 表达预测验证")
            expect(card).to_contain_text("预测 MSE / 基线 MSE")
            expect(card).to_contain_text("DE Overlap@N")
            displayed_ratio = str(round(item["expression"]["mse_relative_to_no_change"], 4))
            expect(card.get_by_text(displayed_ratio, exact=True)).to_be_visible()
            expect(card).to_contain_text("尚未完成独立留出验收")
            page.screenshot(path=str(out / f"{context}-desktop.png"), full_page=True)
        old_id = reanalyses[0]["source_run_id"]
        page.goto(f"{base}/workbench?run={old_id}", wait_until="networkidle")
        expect(page.get_by_text("历史分析结果尚未按 expression-cp10k-v2 重算", exact=False)).to_be_visible()
        browser.close()
    assert not errors, errors
    report = {
        "published_runs_checked": checked,
        "output_hashes_verified": True,
        "originals_unchanged": True,
        "diagnostic_pages": 2,
        "desktop_only": True,
        "pageerrors": errors,
    }
    (PROOF / "acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
