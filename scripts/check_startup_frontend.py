"""Read-only desktop first-screen regression: defer below-fold decorative images."""

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default="reports/startup-performance-2026-10-20/browser-after.json")
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        errors, writes = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: writes.append(request.url) if request.method == "POST" else None)
        start = time.perf_counter()
        page.goto(args.url, wait_until="networkidle", timeout=120_000)
        expect(page.locator(".home-shell")).to_be_visible()
        metrics = page.evaluate(r"""() => ({
            paint: performance.getEntriesByType('paint').map(e=>({name:e.name,ms:e.startTime})),
            images: performance.getEntriesByType('resource').filter(e=>/\.(png|webp)($|\?)/.test(e.name))
                .map(e=>({name:e.name.split('/').pop(),bytes:e.transferSize,duration:e.duration})),
            requests: performance.getEntriesByType('resource').length
        })""")
        metrics["settled_seconds"] = round(time.perf_counter() - start, 3)
        metrics["image_bytes"] = sum(row["bytes"] for row in metrics["images"])
        assert not any(row["name"].startswith("image") for row in metrics["images"]), metrics["images"]
        for section in page.locator(".story-panel,.browse-card").all():
            section.scroll_into_view_if_needed()
            page.wait_for_load_state("networkidle")
        backgrounds = page.locator(".visual-image,.browse-card-media").evaluate_all(
            "nodes=>nodes.map(node=>getComputedStyle(node).backgroundImage)"
        )
        assert len(backgrounds) == 8 and all("url(" in value for value in backgrounds), backgrounds
        assert not errors and not writes, (errors, writes)
        metrics.update({"below_fold_images_loaded": True, "page_errors": errors, "post_requests": writes})
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(metrics, ensure_ascii=False))
        browser.close()


if __name__ == "__main__":
    main()
