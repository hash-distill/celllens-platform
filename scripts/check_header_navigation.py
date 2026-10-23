"""Read-only header navigation and stale route-asset recovery regression."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default="reports/ui-refinement-2026-10-21/header")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    base = args.url.rstrip("/")
    checks = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        errors, writes, assistant_requests = [], [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request",
            lambda request: writes.append(request.url) if request.method not in ("GET", "HEAD") else None,
        )
        page.on(
            "request",
            lambda request: (
                assistant_requests.append(request.url)
                if any(
                    path in request.url
                    for path in ("/assistant/context", "/assistant/interpret", "/assistant/test")
                )
                else None
            ),
        )
        before = page.request.get(base + "/api/v1/experiments").json()["total"]
        page.goto(base, wait_until="networkidle")
        for width in (1280, 1440, 1920, 2560):
            page.set_viewport_size({"width": width, "height": 1000})
            status = page.locator(".service-indicator")
            font = status.evaluate("node=>getComputedStyle(node).fontSize")
            nav_font = page.locator(".header-nav a").first.evaluate("node=>getComputedStyle(node).fontSize")
            assert font == nav_font, (width, font, nav_font)
            bounds = page.evaluate("""() => {
                const rect = selector => {
                    const node = document.querySelector(selector);
                    const {left, right, width, height} = node.getBoundingClientRect();
                    return {left, right, width, height};
                };
                return {header:rect('.header-inner'), brand:rect('.brand'),
                    navigation:rect('.header-nav'), actions:rect('.header-actions'),
                    lastLink:rect('.header-nav > a:last-child'), viewport:innerWidth,
                    document:document.documentElement.scrollWidth};
            }""")
            assert bounds["header"]["left"] == 0 and bounds["header"]["width"] == width, bounds
            assert abs(bounds["brand"]["left"] - 32) <= 1, bounds
            assert abs(width - bounds["actions"]["right"] - 32) <= 1, bounds
            assert bounds["lastLink"]["right"] + 16 <= bounds["actions"]["left"], bounds
            assert bounds["document"] <= width + 1, bounds
            expect(page.locator(".utility-rail a[href^='/settings']")).to_have_count(1)
            expect(page.get_by_role("button", name="AI 解读", exact=True)).to_be_visible()
            headline = page.locator(".hero-copy h1").evaluate(
                "node=>({font:parseFloat(getComputedStyle(node).fontSize),"
                "height:node.getBoundingClientRect().height,"
                "line:parseFloat(getComputedStyle(node).lineHeight)})"
            )
            assert headline["font"] <= 60 and headline["height"] <= headline["line"] * 2 + 2, headline
            status.click()
            page.wait_for_url(base + "/status")
            expect(page.get_by_role("heading", name="服务状态", exact=True)).to_be_visible()
            expect(page.get_by_role("region", name="服务连接概览")).to_be_visible(timeout=30000)
            page.goto(base, wait_until="networkidle")
            page.locator(".app-header").screenshot(path=str(output / f"header-{width}.png"))
            checks.append({"width": width, "status_navigation": True, "headline": headline, "bounds": bounds})

        page.locator(".theme-toggle").click()
        selected_theme = page.locator("html").get_attribute("data-theme")
        page.reload(wait_until="networkidle")
        expect(page.locator("html")).to_have_attribute("data-theme", selected_theme)
        page.locator(".app-header").screenshot(path=str(output / "header-toggled-theme.png"))
        page.locator(".theme-toggle").click()
        page.goto(base + "/settings#model-connection", wait_until="networkidle")
        expect(page.locator(".settings-page")).to_be_visible()
        expect(page.locator(".assistant-panel")).to_have_count(0)
        checks.append({"theme_switch_persists": True, "model_settings_reachable": True})
        assert not errors and not writes and not assistant_requests, (errors, writes, assistant_requests)
        page.screenshot(path=str(output / "home.png"))

        # A production rebuild can remove a chunk referenced by an already-open page.
        # Fail only its first request, then require a fresh document at the intended route.
        stale = browser.new_page(viewport={"width": 1440, "height": 1000})
        failures = []

        def fail_once(route):
            if not failures:
                failures.append(route.request.url)
                route.abort("failed")
            else:
                route.continue_()

        stale.route("**/assets/ServiceStatusView-*.js", fail_once)
        stale.goto(base, wait_until="networkidle")
        stale.locator(".service-indicator").click()
        stale.wait_for_url(base + "/status", timeout=15000)
        expect(stale.get_by_role("heading", name="服务状态", exact=True)).to_be_visible()
        assert len(failures) == 1
        checks.append({"stale_route_asset_recovered": True})

        repeated = browser.new_page()
        repeated_failures, documents = [], []

        def fail_repeatedly(route):
            repeated_failures.append(route.request.url)
            route.abort("failed")

        repeated.on(
            "request",
            lambda request: documents.append(request.url) if request.resource_type == "document" else None,
        )
        repeated.route("**/assets/ServiceStatusView-*.js", fail_repeatedly)
        repeated.goto(base, wait_until="networkidle")
        repeated.locator(".service-indicator").click()
        repeated.wait_for_url(base + "/status", timeout=15000)
        repeated.wait_for_load_state("networkidle")
        assert len(repeated_failures) == 2 and len(documents) == 2, (repeated_failures, documents)
        checks.append({"repeated_asset_failure_reload_limit": 1})
        assert page.request.get(base + "/api/v1/experiments").json()["total"] == before
        report = {
            "checks": checks,
            "page_errors": errors,
            "write_requests": writes,
            "assistant_requests": assistant_requests,
        }
        (output / "checks.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False))
        browser.close()


if __name__ == "__main__":
    main()
