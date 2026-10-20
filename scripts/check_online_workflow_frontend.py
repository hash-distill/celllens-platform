"""Check the running online workbench and stored results.

Run with playwright installed. New online submissions are intercepted; no GPU job is created.
"""

import argparse

from playwright.sync_api import expect, sync_playwright


def check(base: str, executable: str | None = None) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=executable)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors: list[str] = []
        auth_requests: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request", lambda request: auth_requests.append(request.url) if "/auth/" in request.url else None
        )
        page.goto(base + "/records")
        expect(page.get_by_role("heading", name="实验记录", exact=True)).to_be_visible()
        expect(page.locator("#manual-run-id")).to_have_count(0)
        records = page.request.get(base + "/api/v1/runs?limit=1").json()
        if records["items"]:
            run_id = records["items"][0]["run_id"]
            page.locator("#record-search").fill(run_id)
            page.get_by_role("button", name="检索", exact=True).click()
            expect(page.locator(".records-table tbody tr")).to_have_count(1)
            page.get_by_role("link", name="实验分析", exact=True).click()
            expect(page).to_have_url(base + "/demo?run=" + run_id)
        page.goto(base + "/workbench")
        expect(page.get_by_role("heading", name="实验工作台", exact=True)).to_be_visible()
        expect(page.locator('input[name="run-mode"]')).to_have_count(0)
        expect(page.get_by_text("实测对照", exact=True)).to_have_count(0)
        expect(page.get_by_text("结果回放", exact=True)).to_have_count(0)
        page.get_by_role("button", name="展开高级参数").click()
        expect(page.locator("#n-cells-input")).to_be_editable()
        expect(page.locator("#seed-input")).to_be_editable()
        page.locator("#perturbation-input").fill("MYC")
        page.get_by_role("option", name="MYC", exact=True).click()

        def submit() -> None:
            with page.expect_request(
                lambda request: request.url.endswith("/api/v1/runs") and request.method == "POST"
            ) as submitted:
                page.get_by_role("button", name="开始实验", exact=True).click()
            assert submitted.value.post_data_json["mode"] == "online"

        page.route(
            "**/api/v1/runs",
            lambda route: route.fulfill(
                status=503, json={"detail": {"code": "WORKER_UNAVAILABLE", "message": "availability check"}}
            ),
        )
        submit()
        # Reusing old records must create new online predictions instead of replaying them.
        old = page.request.get(base + "/api/v1/runs?mode=precomputed&status=completed&limit=1").json()
        if old["items"]:
            page.goto(base + "/workbench?run=" + old["items"][0]["run_id"])
            page.get_by_role("button", name="复用参数", exact=True).click()
            page.get_by_role("button", name="展开高级参数", exact=True).click()
            expect(page.locator("#n-cells-input")).to_be_editable()
            submit()
        for width in (390, 768, 1280):
            page.set_viewport_size({"width": width, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), width
        assert not errors and not auth_requests, (errors, auth_requests)
        assert not page.context.cookies()
        browser.close()
    print("Online workbench and historical parameter reuse: OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--browser-executable")
    arguments = parser.parse_args()
    check(arguments.url.rstrip("/"), arguments.browser_executable)
