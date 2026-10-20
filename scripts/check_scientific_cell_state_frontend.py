"""Browser acceptance for merged metabolism and real scientific cell-state figures."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / "reports/scientific-cell-state-2026-10-09/browser"
    output.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    acd = "run_c76a0442621c4e0d"
    contexts = {
        "K562": "run_2d7de9d129904b63",
        "RPE1": "run_2151b0c415484f8e",
        "Jurkat": "run_4a24afcd5b084acf",
        "HepG2": "run_0895eccf20f8405d",
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1100})
        page.on("pageerror", lambda e: errors.append(str(e)))

        def wait_figure():
            image = page.locator(".scientific-figure img")
            expect(image).to_be_visible(timeout=120000)
            expect(image).to_have_js_property("complete", True)
            assert image.evaluate("img => img.naturalWidth > 0")

        def open_cell(run, extra=""):
            page.goto(
                f"{args.url}/workbench?run={run}&tab=cell{extra}", wait_until="networkidle", timeout=120000
            )
            wait_figure()

        page.goto(f"{args.url}/workbench?run={acd}&tab=function", wait_until="networkidle", timeout=60000)
        expect(page.locator(".function-node").first).to_be_visible(timeout=15000)
        tabs = page.get_by_role("tablist", name="分析结果").get_by_role("tab")
        assert tabs.all_text_contents() == ["响应概览", "单细胞状态", "基因响应", "代谢功能", "预测验证"]
        assert "tab=metabolism" in page.url and "view=function" in page.url
        expect(page.get_by_role("button", name="功能前后对比", exact=True)).to_have_attribute(
            "aria-pressed", "true"
        )
        checks.append("five main tabs; legacy function route redirects into metabolism")
        page.get_by_role("button", name="任务与反应分数", exact=True).click()
        expect(page.locator(".metabolism")).to_be_visible(timeout=15000)
        page.get_by_role("button", name="功能前后对比", exact=True).click()
        expect(page.locator(".function-node").first).to_be_visible(timeout=15000)
        checks.append("both metabolism subviews work inside one main tab")
        page.locator(".result-tabs").screenshot(path=str(output / "merged-tabs.png"))
        page.get_by_role("link", name="查看逐细胞功能分布", exact=True).click()
        wait_figure()
        expect(page.get_by_label("指标类型", exact=True)).to_have_value("task")
        assert "feature_id=" in page.url
        checks.append("metabolic task links to its matching per-cell figure")
        page.get_by_role("tab", name="基因响应", exact=True).click()
        page.locator(".table-wrap tbody tr.clickable").first.click()
        expect(page.get_by_role("link", name="查看该基因逐细胞分布")).to_be_visible(timeout=15000)
        page.get_by_role("link", name="查看该基因逐细胞分布").click()
        wait_figure()
        assert "feature_kind=gene" in page.url
        checks.append("selected gene links to its matching per-cell figure")
        open_cell(acd, "&feature_kind=gene&feature_id=ENO1")
        expect(page.get_by_label("选择逐细胞指标")).to_have_value("ENO1")
        expect(page.locator(".state-source-legend")).to_contain_text("n=1024")
        expect(page.locator(".state-source-legend")).to_contain_text("n=64")
        expect(page.locator(".state-evidence-note")).to_have_count(0)
        page.locator(".scientific-cell-state").screenshot(path=str(output / "ACD-gene-desktop.png"))
        checks.append("ACD real gene view: 1024 control, 64 predicted, no invented observed")
        for format in ("SVG", "PDF", "PNG", "JSON"):
            with page.expect_download(timeout=60000) as capture:
                page.get_by_role("button", name="导出 " + format, exact=True).click()
            download = capture.value
            destination = output / download.suggested_filename
            download.save_as(destination)
            content = destination.read_bytes()
            assert content.startswith(
                {"SVG": b"<?xml", "PDF": b"%PDF", "PNG": b"\x89PNG", "JSON": b"{"}[format]
            )
            if format == "JSON":
                assert json.loads(content)["feature"]["id"] == "ENO1"
            checks.append("actual " + format + " download matches selected gene view")
        page.get_by_role("button", name="放大科研图").click()
        expect(page.locator(".scientific-figure")).to_have_class("scientific-figure zoom")
        page.get_by_role("button", name="适应页面").click()
        page.get_by_label("搜索逐细胞指标").fill("ENO2")
        page.get_by_label("选择逐细胞指标").select_option("ENO2")
        wait_figure()
        expect(page.locator(".state-numbers h3")).to_contain_text("ENO2")
        page.get_by_label("指标类型", exact=True).select_option("task")
        wait_figure()
        expect(page.locator(".state-numbers h3")).to_contain_text("scCellFie")
        page.locator(".scientific-cell-state").screenshot(path=str(output / "ACD-task-desktop.png"))
        checks.append("zoom, gene search, feature switching and task switching")
        for name, run in contexts.items():
            open_cell(run)
            expect(page.locator(".state-source-legend")).to_contain_text("扰动后 / 实测")
            page.locator(".scientific-figure").screenshot(path=str(output / f"{name}-figure.png"))
            checks.append(name + " frozen real-result replay has control/predicted/observed figures")
        page.set_viewport_size({"width": 1440, "height": 1000})
        open_cell(acd, "&feature_id=ENO1")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth+1")
        page.locator(".scientific-cell-state").screenshot(path=str(output / "ACD-desktop-1440.png"))
        checks.append("1440px desktop: figure scroll stays within container")
        page.set_viewport_size({"width": 1920, "height": 1100})
        page.goto(
            f"{args.url}/workbench?run=run_b69b0a932fa84675&tab=cell", wait_until="networkidle", timeout=60000
        )
        expect(page.get_by_role("heading", name="本次科研图暂不可用")).to_be_visible(timeout=15000)
        expect(page.locator(".scientific-figure")).to_have_count(0)
        checks.append("synthetic historical demo remains explicitly unavailable for scientific figures")
        # Stale requests must not overwrite a newly selected run.
        open_cell(acd, "&feature_id=ENO1")
        page.get_by_label("选择逐细胞指标").select_option("ENO2")
        open_cell(contexts["Jurkat"], "&feature_kind=task")
        expect(page.locator(".active-experiment")).to_contain_text("Jurkat")
        expect(page.locator(".state-source-legend")).to_contain_text("n=34")
        checks.append("rapid feature/run changes cannot show stale results")
        assert not errors, errors
        browser.close()
    document = {"passed": len(checks), "checks": checks, "page_errors": errors}
    (output / "acceptance.json").write_text(
        json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(document, ensure_ascii=False))


if __name__ == "__main__":
    main()
