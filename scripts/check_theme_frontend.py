"""Check the integrated design against a running production API; no jobs are submitted."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    output = Path("reports/frontend-integration-2026-10-20/browser")
    output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    writes: list[str] = []
    layouts: list[dict] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            reduced_motion="reduce",
            color_scheme="light",
        )
        page = context.new_page()
        page.set_default_timeout(30_000)
        page.set_default_navigation_timeout(120_000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda req: writes.append(req.url) if req.method == "POST" else None)
        history = page.request.get(base + "/api/v1/experiments?limit=100").json()
        run_id = next(
            (row["run"]["run_id"] for row in history["items"] if row["status"] == "completed"),
            None,
        )
        page.goto(base + "/", wait_until="networkidle")
        expect(page.locator(".home-shell")).to_be_visible()
        expect(page.locator(".mock-banner")).to_have_count(0)
        for section in page.locator(".story-panel,.browse-card").all():
            section.scroll_into_view_if_needed()
            page.wait_for_load_state("networkidle")
        page.evaluate("window.scrollTo(0,0)")
        assets = page.locator(".home-fixed-backdrop,.visual-image,.browse-card-media").evaluate_all(
            r"""nodes => [...new Set(nodes.flatMap(node =>
                [...getComputedStyle(node).backgroundImage.matchAll(/url\([\"']?([^\"')]+)[\"']?\)/g)]
                    .map(match => match[1])))]"""
        )
        assert len(assets) == 5, assets
        for asset in assets:
            response = page.request.get(asset)
            assert response.ok and response.headers["content-type"].startswith("image/"), asset
            assert response.body().startswith(b"\x89PNG\r\n\x1a\n"), asset
        contexts = page.request.get(base + "/api/v1/catalog/contexts").json()
        ready_count = sum(bool(row["online_ready"]) for row in contexts)
        expect(page.locator(".hero-metrics dd").first).to_have_text(str(ready_count))
        expect(page.get_by_text("在线 / 回放 / 对照三种模式", exact=True)).to_have_count(0)
        expect(page.locator("a.coverage-entry")).to_have_attribute("href", "/coverage")

        page.get_by_role("button", name="切换到深色模式", exact=True).click()
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        page.reload(wait_until="networkidle")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        page.goto(base + "/settings", wait_until="networkidle")
        selector = page.get_by_label("页面主题", exact=True)
        expect(selector).to_have_value("dark")
        selector.select_option("system")
        page.emulate_media(color_scheme="dark")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        page.emulate_media(color_scheme="light")
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        page.get_by_role("button", name="切换深色", exact=True).click()
        expect(selector).to_have_value("dark")

        paths = ["/", "/workbench", "/records", "/settings", "/coverage", "/status", "/compare"]
        if run_id:
            paths.extend("/demo?run=" + run_id + suffix for suffix in ("", "&tab=genes", "&tab=metabolism"))
        for mode in ("light", "dark"):
            page.goto(base + "/settings", wait_until="networkidle")
            page.get_by_label("页面主题", exact=True).select_option(mode)
            for width in (1280, 1440, 1920):
                page.set_viewport_size({"width": width, "height": 1000})
                for index, path in enumerate(paths):
                    page.goto(base + path, wait_until="networkidle")
                    expect(page.locator("html")).to_have_attribute("data-theme", mode)
                    expect(page.locator("html")).to_have_css("opacity", "1")
                    expect(page.locator("html")).to_have_css("filter", "none")
                    expect(page.locator(".header-settings")).to_be_visible()
                    expect(page.get_by_role("button", name="AI 解读", exact=True)).to_be_visible()
                    contrast_targets = page.locator(".btn-primary:visible,.pill-ev-insufficient:visible")
                    contrasts = contrast_targets.evaluate_all("""nodes => {
                        function luminance(color) {
                            const rgb = color.match(/[\\d.]+/g).slice(0,3).map(Number).map(v => {
                                v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
                            });
                            return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
                        }
                        return nodes.filter(node => !node.disabled).map(node => {
                            const style = getComputedStyle(node);
                            const a = luminance(style.color), b = luminance(style.backgroundColor);
                            return (Math.max(a,b) + 0.05) / (Math.min(a,b) + 0.05);
                        });
                    }""")
                    assert all(ratio >= 4.5 for ratio in contrasts), (mode, path, contrasts)
                    width_state = page.evaluate(
                        "({viewport:innerWidth, document:document.documentElement.scrollWidth})"
                    )
                    assert width_state["document"] <= width_state["viewport"] + 1, (mode, path, width_state)
                    if path == "/":
                        launcher = page.get_by_role("button", name="AI 解读", exact=True).bounding_box()
                        edge = page.locator(".page-edge-button").bounding_box()
                        assert launcher and edge
                        assert edge["y"] + edge["height"] <= launcher["y"], (launcher, edge)
                        for panel in page.locator(".story-panel").all():
                            panel.scroll_into_view_if_needed()
                            expect(panel).to_have_css("opacity", "1")
                        page.evaluate("window.scrollTo(0,0)")
                    page.screenshot(path=str(output / f"{mode}-{width}-{index}.png"))
                    layouts.append({"theme": mode, "width": width, "path": path, **width_state})

        if run_id:
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.goto(base + "/demo?run=" + run_id, wait_until="networkidle")
            for name in ("基因响应", "代谢功能", "响应概览"):
                page.get_by_role("tab", name=name, exact=True).click()
                expect(page.get_by_role("tab", name=name, exact=True)).to_have_attribute(
                    "aria-selected", "true"
                )
                page.wait_for_load_state("networkidle")
            page.get_by_role("button", name="AI 解读", exact=True).click()
            expect(page.get_by_role("dialog", name="AI 实验解读", exact=True)).to_be_visible()
            expect(page.locator(".floating-source")).to_contain_text(run_id)
        assert not errors, errors
        assert not writes, writes
        after = page.request.get(base + "/api/v1/experiments?limit=1").json()
        assert after["total"] == history["total"]
        result = {
            "run_id": run_id,
            "history_total": history["total"],
            "layout_cases": len(layouts),
            "theme_persistence_and_system_sync": True,
            "source_assets": 5,
            "page_errors": errors,
            "post_requests": writes,
            "layouts": layouts,
        }
        (output / "acceptance.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary = {key: value for key, value in result.items() if key != "layouts"}
        print(json.dumps(summary, ensure_ascii=False))
        browser.close()


if __name__ == "__main__":
    main()
