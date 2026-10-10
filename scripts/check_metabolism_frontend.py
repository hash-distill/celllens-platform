"""Exercise real task filters, chart selection and missing optional results in a browser."""

import argparse
import json
from pathlib import Path
from typing import cast

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--demo-run-id", default="run_386e07d2897f4e0f")
    parser.add_argument("--real-run-id", default="run_4d0b3038ea8642af")
    args = parser.parse_args()
    out = Path(__file__).resolve().parents[1] / "reports/frontend/metabolism-fix"
    out.mkdir(parents=True, exist_ok=True)
    checks, errors, failures = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(15000)
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.on(
            "response",
            lambda r: (
                failures.append({"url": r.url, "status": r.status})
                if r.status >= 400 and "/api/v1/runs/" in r.url
                else None
            ),
        )
        page.goto(f"{args.url}/workbench?run={args.demo_run_id}&tab=metabolism", wait_until="networkidle")
        filters = page.get_by_role("radiogroup", name="任务覆盖等级筛选")
        expect(filters.get_by_role("radio")).to_have_count(4)
        expect(filters.get_by_role("radio", name="全部", exact=False)).to_be_checked()
        expect(page.locator(".metabolism input[type=checkbox]")).to_have_count(0)
        checks.append("mutually exclusive task filters default to all")
        for level in ["探索性", "证据不足"]:
            filters.get_by_role("radio", name=level, exact=False).check()
            expect(filters.get_by_role("radio", checked=True)).to_have_count(1)
            expect(page.locator(".task-empty")).to_contain_text(level)
            expect(page.locator(".task-empty")).to_contain_text("Top 摘要")
            expect(page.get_by_role("img", name="代谢任务差异条形图")).to_have_count(0)
        checks.append("zero-count filters immediately show an explicit scoped empty state")
        filters.get_by_role("radio", name="覆盖支持", exact=False).check()
        expect(page.get_by_role("img", name="代谢任务差异条形图")).to_be_visible()
        page.locator("#task-search").fill("no-such-task")
        expect(page.locator(".task-empty")).to_contain_text("no-such-task")
        page.locator("#task-search").fill("")
        page.get_by_role("button", name="查看任务：TCA cycle", exact=True).click()
        expect(page.locator(".task-detail")).to_contain_text("TCA cycle")
        expect(page.locator(".task-detail")).to_contain_text("尚未提供")
        expect(page.locator(".task-trace")).to_contain_text("本次运行尚无关联追溯记录")
        expect(page.locator(".metabolism")).not_to_contain_text("HTTP 404")
        checks.append("legacy task details remain readable without requesting absent trace or reaction files")
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=str(out / "demo-after.png"), full_page=True)

        # A physical click in the bar must select its task (not just produce a tooltip).
        chart = page.get_by_role("img", name="代谢任务差异条形图")
        canvas = chart.locator("canvas")
        canvas.screenshot(path=str(out / "demo-chart.png"))
        # Find the warm bar's interior in the rendered canvas; avoids guessed chart coordinates.
        from PIL import Image

        with Image.open(out / "demo-chart.png").convert("RGB") as im:
            candidates = []
            # Selected tasks dim the other bars. Include those blended warm colors,
            # and exclude the sticky header and labels outside the positive half.
            for y in range(80, im.height):
                for x in range(im.width // 2 + 40, im.width):
                    red, green, blue = cast(tuple[int, int, int], im.getpixel((x, y)))
                    if red > 180 and red - green > 15 and green - blue > 5:
                        candidates.append((x, y))
        assert candidates, "Expected actual positive bars in the demo chart"
        x, y = candidates[len(candidates) // 2]
        canvas.click(position={"x": x, "y": y})
        expect(page.locator(".task-detail h4")).not_to_have_text("TCA cycle")
        checks.append("physical chart bar click selects a task detail")

        page.goto(f"{args.url}/workbench?run={args.real_run_id}&tab=metabolism", wait_until="networkidle")
        data = page.request.get(f"{args.url}/api/v1/runs/{args.real_run_id}/metabolic-tasks?scope=all").json()
        filters = page.get_by_role("radiogroup", name="任务覆盖等级筛选")
        if data.get("completeness_available"):
            expect(filters).to_have_count(0)
            expect(page.locator(".official-cards")).to_contain_text("131 / 931")
        else:
            for level, key in [
                ("覆盖支持", "supported"),
                ("探索性", "exploratory"),
                ("证据不足", "insufficient"),
            ]:
                filters.get_by_role("radio", name=level, exact=False).check()
                expected = sum(t["evidence_level"] == key for t in data["items"])
                expect(page.locator(".task-filter-status")).to_contain_text(f"{expected} 项")
        task = next(
            t for t in data["items"] if t["trace_available"] and t["evidence_level"] == "insufficient"
        )
        page.locator("#task-search").fill(task["label"])
        page.get_by_role("button", name="查看任务：" + task["label"], exact=True).click()
        expect(page.locator(".trace-network")).to_be_visible()
        expect(page.locator(".trace-task .mono")).to_have_text(task["id"])
        checks.append(
            "real official completeness or legacy categories and matching frozen trace are selectable"
        )
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=str(out / "real-after.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        expect(filters.get_by_role("radio")).to_have_count(0 if data.get("completeness_available") else 4)
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 2")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
        checks.append(
            "390px metabolism layout preserves the applicable completeness view without page overflow"
        )
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(f"{args.url}/workbench?run={args.demo_run_id}", wait_until="networkidle")
        expect(page.locator(".task-trace")).to_contain_text("本次运行尚无关联追溯记录")
        checks.append("overview also avoids requests for known missing optional artifacts")
        assert not errors, errors
        assert not failures, failures
        (out / "checks.json").write_text(
            json.dumps(
                {"checks": checks, "pageerrors": errors, "failed_run_requests": failures},
                ensure_ascii=False,
                indent=2,
            ),
            "utf-8",
        )
        print(json.dumps({"passed": len(checks), "checks": checks}, ensure_ascii=False))
        browser.close()


if __name__ == "__main__":
    main()
