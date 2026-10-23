"""Read real readiness; exercise download controls with clearly isolated protocol fixtures."""

import argparse
import copy
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    parser.add_argument("--output", type=Path, default=Path("reports/resources-2026-10-22"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = {"real": {}, "protocol_fixture": {}, "visual": []}
    with sync_playwright() as driver:
        browser = driver.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors, writes = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda req: writes.append(req.url) if req.method == "POST" else None)
        response = context.request.get(args.url + "/api/v1/resources", timeout=60000)
        assert response.ok and response.headers["cache-control"] == "no-store"
        real = response.json()
        assert len(real["items"]) == 4
        result["real"] = {row["cell_line"]: row["ready"] for row in real["items"]}
        for theme in ("light", "dark"):
            context.add_init_script(f"localStorage.setItem('celllens.theme','{theme}')")
            for width in (1280, 1440, 1920):
                page.set_viewport_size({"width": width, "height": 1000})
                page.goto(args.url + "/status", wait_until="networkidle")
                expect(page.locator(".resource-card")).to_have_count(4, timeout=60000)
                expect(page.get_by_role("button", name="刷新资源状态")).to_be_enabled(timeout=60000)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert page.locator("html").get_attribute("data-theme") == theme
                page.locator("#inference-resources").screenshot(
                    path=args.output / f"resources-{theme}-{width}.png"
                )
                result["visual"].append({"theme": theme, "width": width, "overflow": False})
        assert not writes, "Opening the resource page must not start downloads"

        # Do not fetch large weights during browser acceptance. These requests are
        # fulfilled in this browser only, while ordinary page/API traffic stays real.
        state = copy.deepcopy(real)
        state.update(active_cell=None, can_cancel=True)
        pack = next(row for row in state["items"] if row["cell_line"] == "RPE1")
        pack.update(ready=False, weights_ready=False, control_ready=False, remaining_bytes=pack["size_bytes"])
        for item in pack["files"]:
            item["status"] = "missing"
        pack["job"] = {"status": "idle"}
        calls, catalog_requests = [], []
        page.on(
            "request",
            lambda req: catalog_requests.append(req.url) if "/catalog/contexts" in req.url else None,
        )

        def resources(route):
            endpoint = route.request.url.split("/resources", 1)[1]
            if route.request.method == "GET":
                route.fulfill(json=state, headers={"Cache-Control": "no-store"})
                return
            calls.append({"path": endpoint, "body": route.request.post_data_json})
            assert endpoint in ("/RPE1/download", "/RPE1/cancel")
            if endpoint.endswith("/download"):
                assert route.request.post_data_json == {"accepted_license": True}
                state["active_cell"] = "RPE1"
                pack["job"] = {
                    "status": "downloading",
                    "message": "Protocol fixture",
                    "total_bytes": 100,
                    "downloaded_bytes": 42,
                    "current_file": "checkpoints/final.ckpt",
                }
                route.fulfill(status=202, json=pack["job"])
            else:
                state["active_cell"] = None
                pack["job"] = {"status": "cancelled", "message": "已取消，可重试续传已下载的权重"}
                route.fulfill(json={"status": "cancelled"})

        page.route("**/api/v1/resources**", resources)
        page.goto(args.url + "/status", wait_until="networkidle")
        card = page.locator('[data-cell="RPE1"]')
        expect(card.get_by_role("button", name="下载并准备", exact=True)).to_be_disabled()
        card.get_by_role("checkbox").check()
        card.get_by_role("button", name="下载并准备", exact=True).click()
        expect(card.get_by_role("progressbar")).to_have_attribute("value", "42")
        expect(page.locator('[data-cell="K562"]').get_by_role("button", name="核验已有资源")).to_be_disabled()
        card.get_by_role("button", name="取消准备").click()
        expect(card.get_by_role("button", name="重试准备")).to_be_enabled()
        card.get_by_role("button", name="重试准备").click()
        expect(card.get_by_role("progressbar")).to_be_visible()
        state["active_cell"] = None
        pack.update(ready=True, weights_ready=True, control_ready=True, remaining_bytes=0)
        for item in pack["files"]:
            item["status"] = "verified"
        pack["job"] = {"status": "completed", "message": "Protocol fixture completed"}
        expect(card.get_by_role("button", name="核验已有资源")).to_be_enabled(timeout=10000)
        expect(card.get_by_role("link", name="前往工作台 →")).to_be_visible(timeout=15000)
        card.get_by_role("link", name="前往工作台 →").click()
        expect(page).to_have_url(args.url + "/workbench")
        expect(page.get_by_role("radio", name="RPE1", exact=True)).to_be_checked()
        # Re-entering after completion must refresh the shared catalog again.
        before = len(catalog_requests)
        page.get_by_role("link", name="查看服务状态", exact=False).click()
        expect(page.locator('[data-cell="RPE1"]').get_by_role("link", name="前往工作台 →")).to_be_visible()
        assert len(catalog_requests) > before
        assert len(calls) == 3 and all(row["path"].startswith("/RPE1/") for row in calls)
        result["protocol_fixture"] = {
            "selected_background_only": True,
            "license_gate": True,
            "cancel_retry": True,
            "progress": True,
            "hot_catalog": True,
            "requests": calls,
        }
        assert not errors, errors
        result["page_errors"] = errors
        (args.output / "browser-check.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False))
        browser.close()


if __name__ == "__main__":
    main()
