"""Real-service browser acceptance for measured comparisons; no response substitutions."""

import argparse
import csv
import io
import json
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/measured-comparison-2026-10-15/browser"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--browser-executable",
        default="C:/Users/zhs14/AppData/Local/ms-playwright/chromium-1223/chrome-win64/chrome.exe",
    )
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(path):
        with opener.open(args.url + path, timeout=60) as response:
            return json.load(response)

    history = get("/api/v1/experiments?limit=100")
    cases = [row for row in history["items"] if row["source"] == "online" and row["status"] == "completed"]
    reports = []
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=args.browser_executable)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1500, "height": 1050})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        for case in cases:
            run = case["id"]
            doc = get(f"/api/v1/runs/{run}/comparison")
            page.goto(f"{args.url}/demo?run={run}&tab=comparison", wait_until="networkidle")
            expect(page.get_by_role("tab", name="实测对比", exact=True)).to_have_attribute(
                "aria-selected", "true"
            )
            panel = page.locator(".measured-comparison")
            if doc["status"] == "available":
                preview = get(f"/api/v1/assistant/context?source_kind=run&source_id={run}")
                assert preview["data"]["measured_comparison"]["expression"] == doc["expression"]
                assert "measured_comparison.json" in preview["artifact_sha256"]
                expect(panel.get_by_text("预测变化 MSE", exact=True)).to_be_visible()
                assert page.locator(".metric-card").count() == 4
                cards = page.locator(".metric-card>strong").all_text_contents()
                expected_values = [
                    doc["expression"].get(key)
                    for key in [
                        "signed_delta_pearson",
                        "signed_delta_spearman",
                        "mse",
                        "mse_relative_to_no_change",
                    ]
                ]
                for shown, expected in zip(cards, expected_values, strict=True):
                    if expected is not None:
                        assert abs(float(shown) - expected) < 0.000051
                mse_ratio = doc["expression"]["mse_relative_to_no_change"]
                if mse_ratio is not None:
                    expected = "本案例误差低于不变化基线" if mse_ratio < 1 else "本案例未优于不变化基线"
                    expect(panel.get_by_text(expected, exact=True)).to_be_visible()
                assert page.locator(".chart-panel canvas").count() >= 1
                assert len(doc["genes"]) == doc["expression"]["gene_count"]
                with page.expect_download() as download:
                    panel.get_by_role("button", name="下载完整基因对比 CSV", exact=True).click()
                csv_path = OUT / download.value.suggested_filename
                download.value.save_as(csv_path)
                exported = list(csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8-sig"))))
                assert len(exported) == len(doc["genes"])
                source_rows = {row["id"]: row for row in doc["genes"]}
                for row in exported:
                    for field in ["control", "predicted", "observed", "predicted_delta", "observed_delta"]:
                        assert abs(float(row[field]) - source_rows[row["id"]][field]) < 1e-12
                panel.get_by_role("button", name="代谢任务比较", exact=True).click()
                expect(panel.get_by_text("表达派生任务的一致性", exact=True)).to_be_visible()
                if doc["tasks"]:
                    with page.expect_download() as download:
                        panel.get_by_role("button", name="下载完整任务对比 CSV", exact=True).click()
                    task_path = OUT / download.value.suggested_filename
                    download.value.save_as(task_path)
                    task_text = task_path.read_text(encoding="utf-8-sig")
                    task_rows = list(csv.DictReader(io.StringIO(task_text)))
                    assert len(task_rows) == len(doc["tasks"])
                panel.get_by_role("button", name="基因表达比较", exact=True).click()
                target = doc["genes"][0]["id"]
                panel.get_by_role("textbox", name="搜索比较基因", exact=True).fill(target)
                expect(page.locator(".paired-table-wrap tbody tr").first).to_be_visible()
                panel.get_by_role("textbox", name="搜索比较基因", exact=True).fill("")
                panel.locator("summary").click()
                with page.expect_download() as download:
                    panel.get_by_role("button", name="下载指标、成对数据与来源 JSON", exact=True).click()
                json_path = OUT / download.value.suggested_filename
                download.value.save_as(json_path)
                assert json.loads(json_path.read_text(encoding="utf8"))["binding"] == doc["binding"]
                panel.locator("summary").click()
            else:
                expect(panel.locator("[data-comparison-unavailable]")).to_be_visible()
                assert page.locator(".metric-card").count() == 0
                expect(panel.get_by_text(doc["reason"], exact=True)).to_be_visible()
                zero_note = panel.get_by_text(
                    "该固定数据版本中的匹配测量数为 0，不能据此推断模型准确率。", exact=True
                )
                if doc.get("available_measured_cells") == 0:
                    expect(zero_note).to_be_visible()
                else:
                    # A comparison may be absent or preparing without a measured-count claim.
                    expect(zero_note).to_have_count(0)
            for width in [1500, 768, 390]:
                page.set_viewport_size({"width": width, "height": 1050})
                page.wait_for_timeout(250)
                assert not page.evaluate("document.documentElement.scrollWidth > innerWidth"), (run, width)
                page.screenshot(path=str(OUT / f"{run}-{width}.png"), full_page=width == 390)
            reports.append(
                {
                    "run_id": run,
                    "status": doc["status"],
                    "cell_line": doc["cell_line"],
                    "perturbation": doc["perturbation"],
                    "all_widths_passed": True,
                    "download_rows": len(doc.get("genes", [])),
                }
            )
        page.goto(args.url + "/workbench", wait_until="networkidle")
        shortcuts = page.locator(".measured-shortcuts button")
        expect(shortcuts.first).to_be_visible()
        target = shortcuts.first.inner_text().split(" · ")[0]
        shortcuts.first.click()
        expect(page.locator("#perturbation-input")).to_have_value(target)
        page.screenshot(path=str(OUT / "measured-shortcuts.png"), full_page=True)
        assert not errors, errors
        browser.close()
    (OUT / "acceptance.json").write_text(
        json.dumps({"items": reports, "page_errors": errors}, ensure_ascii=False, indent=2), encoding="utf8"
    )
    print(json.dumps({"cases": len(reports), "page_errors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
