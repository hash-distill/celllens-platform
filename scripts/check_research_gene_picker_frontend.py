"""Read-only checks for shared categorized experiment selectors."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    parser.add_argument("--output", default="reports/research-gene-picker-2026-10-23")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    errors, checks = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1100}, reduced_motion="reduce")
        context.add_init_script("localStorage.setItem('celllens.theme','light')")
        context.route(
            "**/api/**",
            lambda route: route.continue_() if route.request.method in ("GET", "HEAD") else route.abort(),
        )
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url + "/research?type=measured", wait_until="networkidle")
        expect(page.get_by_role("radiogroup", name="细胞背景", exact=True)).to_be_visible()
        category = page.get_by_label("基因功能分类 · Gene function class", exact=True)
        expect(category).to_be_visible()
        category.select_option("PC00144")
        expect(page.get_by_role("option", name="ALDOA", exact=True)).to_be_visible()

        def selector_styles():
            return page.evaluate("""() => Object.fromEntries([
                '.cell-background-picker .choice', '.cell-background-picker .choice-name',
                '.gene-category-select', '.dropdown-item', '.dropdown-item small'
            ].map(selector => {
                const el = document.querySelector(selector), s = getComputedStyle(el);
                return [selector, {font:s.fontSize, padding:s.padding, radius:s.borderRadius}];
            }))""")

        measured_styles = selector_styles()
        page.get_by_role("combobox", name="扰动基因", exact=True).fill("ALDOA")
        expect(page.get_by_role("option", name="ALDOA", exact=True)).to_be_visible()
        page.screenshot(path=str(output / "measured-candidates.png"), full_page=True)
        page.get_by_role("option", name="ALDOA", exact=True).click()
        expect(page.locator(".selected-gene-annotation")).to_contain_text("裂合酶")
        expect(page.get_by_role("button", name="开始实测分析", exact=True)).to_be_enabled()
        page.screenshot(path=str(output / "measured-classified.png"), full_page=True)
        page.get_by_role("button", name="切换到深色模式", exact=True).click()
        page.screenshot(path=str(output / "measured-classified-dark.png"), full_page=True)
        page.get_by_role("button", name="切换到明亮模式", exact=True).click()
        checks.append("measured: shared radio choices, category filter, candidate selection and annotation")
        page.get_by_label("实验类型", exact=True).select_option("prediction")
        expect(page.get_by_role("radiogroup", name="细胞背景", exact=True)).to_be_visible()
        expect(page.get_by_role("combobox", name="扰动基因", exact=True)).to_have_value("ALDOA")
        category.select_option("PC00144")
        expect(page.get_by_role("option", name="ALDOA", exact=True)).to_be_visible()
        assert selector_styles() == measured_styles
        page.get_by_role("option", name="ALDOA", exact=True).click()
        page.screenshot(path=str(output / "prediction-classified.png"), full_page=True)
        checks.append("prediction: same controls and selected gene retained")
        page.get_by_label("实验类型", exact=True).select_option("measured")
        page.get_by_role("radio", name="RPE1", exact=True).check()
        expect(page.get_by_role("combobox", name="扰动基因", exact=True)).to_have_value("")
        expect(category).to_have_value("")
        category.select_option("PC00144")
        search = page.get_by_role("combobox", name="扰动基因", exact=True)
        search.fill("ALDO")
        search.press("ArrowDown")
        search.press("Enter")
        expect(search).to_have_value("ALDOA")
        search.fill("UNLISTED_FAKE_GENE")
        expect(page.locator(".dropdown")).to_contain_text("无匹配的可用扰动")
        search.press("Escape")
        search.blur()
        expect(search).to_have_value("ALDOA")
        checks.append(
            "background change resets category and target; keyboard selection and invalid input fallback"
        )
        response = context.request.get(
            args.url + "/api/v1/catalog/perturbations?cell_line=RPE1&mode=measured"
        )
        data = response.json()
        assert len(data["items"]) > 100
        last = data["items"][-1]
        category.select_option("")
        search.fill(last)
        page.get_by_role("option", name=last, exact=True).click()
        expect(search).to_have_value(last)
        expect(page.get_by_role("button", name="开始实测分析", exact=True)).to_be_enabled()
        checks.append("complete measured gene catalog: candidate beyond the first 100 remains selectable")
        assert not errors, errors
        browser.close()
    result = dict(tested_url=args.url, checks=checks, page_errors=errors, real_experiments_submitted=False)
    (output / "checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
