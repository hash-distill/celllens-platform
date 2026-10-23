"""Read-only homepage animation/resource regression and repeatable frame sampling.

Run against a production build. Frame timings are observations, not portable pass
thresholds: host GPU, browser mode and screen refresh rate affect them.
"""

import argparse
import json
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

FRAME_SAMPLE = """async ({duration, scroll}) => {
    const intervals = [];
    const distance = document.documentElement.scrollHeight - innerHeight;
    let start, previous;
    await new Promise(resolve => {
        function sample(now) {
            start ??= now;
            if (previous !== undefined) intervals.push(now - previous);
            previous = now;
            if (scroll) scrollTo(0, distance * (1-Math.cos((now-start)/duration*Math.PI*2))/2);
            if (now-start < duration) requestAnimationFrame(sample); else resolve();
        }
        requestAnimationFrame(sample);
    });
    intervals.sort((a,b) => a-b);
    return {frames:intervals.length,
        fps:1000*intervals.length/intervals.reduce((a,b)=>a+b,0),
        p95_ms:intervals[Math.floor(intervals.length*.95)],
        frames_over_50ms:intervals.filter(v=>v>50).length};
}"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default="reports/homepage-performance")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    writes: list[str] = []
    results: list[dict] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        browser_version = browser.version
        for theme in ("light", "dark"):
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                reduced_motion="no-preference", color_scheme=theme,
            )
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: writes.append(request.url)
                    if request.method not in ("GET", "HEAD") else None)
            page.goto(args.url, wait_until="networkidle")
            expect(page.locator(".home-shell")).to_be_visible()
            resources = page.evaluate("""() => performance.getEntriesByType('resource')
                .map(e=>({name:e.name, bytes:e.encodedBodySize, type:e.initiatorType}))""")
            image_bytes = sum(row["bytes"] for row in resources if row["type"] in ("img", "css"))
            assert image_bytes < 160_000, f"First-screen images exceed 160 KB: {image_bytes}"
            assert not any(re.search(r"image[1-4][-\.]", row["name"]) for row in resources), resources
            filters = page.locator(".home-shell *, .page-edge-button").evaluate_all("""nodes =>
                nodes.filter(node=>getComputedStyle(node).backdropFilter!=='none')
                    .map(node=>node.className)""")
            assert not filters, f"Realtime backdrop sampling in homepage: {filters}"
            expect(page.locator(".home-hero")).to_have_class(re.compile(r"hero-animating"))
            idle = page.evaluate(FRAME_SAMPLE, {"duration": 2000, "scroll": False})
            scroll = page.evaluate(FRAME_SAMPLE, {"duration": 3000, "scroll": True})
            page.evaluate("scrollTo(0,document.documentElement.scrollHeight)")
            expect(page.locator(".home-hero")).not_to_have_class(re.compile(r"hero-animating"))
            states = page.locator(".orb, .stage-card-float").evaluate_all("""nodes =>
                nodes.map(node=>getComputedStyle(node).animationPlayState)""")
            assert states and all(state == "paused" for state in states), states
            # Visit every section: deferred decoration must eventually load, once.
            for panel in page.locator(".story-panel, .browse-card").all():
                panel.scroll_into_view_if_needed()
                page.wait_for_load_state("networkidle")
            images = page.locator(".visual-image, .browse-card-media").evaluate_all("""nodes=>
                nodes.map(node=>getComputedStyle(node).backgroundImage)""")
            assert len(images) == 8 and all("url(" in value for value in images), images
            page.evaluate("scrollTo(0,0)")
            expect(page.locator(".home-hero")).to_have_class(re.compile(r"hero-animating"))
            # Exercise the visibility handler deterministically in headless Chromium.
            page.evaluate("""() => {
                Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});
                document.dispatchEvent(new Event('visibilitychange'));
            }""")
            expect(page.locator(".home-hero")).not_to_have_class(re.compile(r"hero-animating"))
            page.evaluate("""() => {
                delete document.hidden; document.dispatchEvent(new Event('visibilitychange'));
            }""")
            expect(page.locator(".home-hero")).to_have_class(re.compile(r"hero-animating"))
            page.screenshot(path=str(output / f"hero-{theme}.png"))
            page.emulate_media(reduced_motion="reduce")
            animations = page.locator(".home-hero").evaluate(
                "node=>node.getAnimations({subtree:true}).length"
            )
            assert animations == 0, animations
            page.emulate_media(reduced_motion="no-preference")
            # Unmount and remount: no orphan animation activity or duplicate page controls.
            page.get_by_role("link", name="了解方法与数据", exact=True).click()
            expect(page.locator(".home-shell")).to_have_count(0)
            expect(page.locator(".page-edge-button")).to_have_count(0)
            page.go_back(wait_until="networkidle")
            expect(page.locator(".home-hero")).to_have_class(re.compile(r"hero-animating"))
            expect(page.locator(".page-edge-button")).to_have_count(1)
            results.append({"theme": theme, "initial_image_bytes": image_bytes,
                            "idle": idle, "scroll": scroll, "lifecycle_checks": "passed"})
            context.close()
        browser.close()
    assert not errors and not writes, (errors, writes)
    report = {"results": results, "page_errors": errors, "write_requests": writes,
              "browser_version": browser_version, "viewport": {"width": 1440, "height": 1000},
              "headed": args.headed, "frame_timings_are_hardware_dependent": True}
    (output / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
