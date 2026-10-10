"""Check formal production behavior against a running CellLens service."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    parser.add_argument("--output", default="reports/formal-system-2026-10-10/browser")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    checks = []
    errors = []
    forbidden = ["内部科研原型", "预计算演示", "演示模式", "联调", "待后端协作", "验证入口未开放"]

    def passed(name: str) -> None:
        checks.append(name)
        print(name, flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        # An old browser opt-in must have no effect on production requests.
        context.add_init_script("localStorage.setItem('celllens.mockMode.v1', 'on')")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        requests = []
        page.on("request", lambda request: requests.append(request.url))
        ready = page.request.get(base + "/api/v1/ready")
        assert ready.ok and ready.json()["ready"] is True
        for cell_line in ["K562", "RPE1", "Jurkat", "HepG2"]:
            for mode in ["precomputed", "validation"]:
                response = page.request.get(
                    base + f"/api/v1/catalog/perturbations?cell_line={cell_line}&mode={mode}"
                )
                assert response.ok and response.json()["items"] == ["ALDOA"]
        passed("four backgrounds expose real ALDOA replay and matched observations")

        before = page.request.get(base + "/api/v1/runs").json()["total"]
        rejected = page.request.post(
            base + "/api/v1/runs", data={"cell_line": "K562", "perturbation": "MYC", "mode": "precomputed"}
        )
        assert rejected.status == 422 and rejected.json()["detail"]["code"] == "SYNTHETIC_RESULT_DISABLED"
        assert page.request.get(base + "/api/v1/runs").json()["total"] == before
        passed("direct synthetic replay request is rejected without creating a record")

        for route in ["/", "/workbench", "/records", "/compare", "/demo", "/about"]:
            page.goto(base + route, wait_until="networkidle")
            body = page.locator("body").inner_text()
            assert all(term not in body for term in forbidden), route
            nav = page.locator(".app-header nav")
            expect(nav.get_by_role("link", name="结果解读", exact=True)).to_be_visible()
            expect(page.locator(".mock-banner")).to_have_count(0)
            if route == "/about":
                expect(page.get_by_role("heading", name="结果含义", exact=True)).to_be_visible()
                expect(page.get_by_text("共同对照 PCA", exact=False).first).to_be_visible()
                expect(page.locator("input[type=checkbox]")).to_have_count(0)
            page.screenshot(path=str(out / (route.strip("/") or "home")) + ".png", full_page=True)
        assert any("/api/v1/catalog/contexts" in url for url in requests)
        assert not any("mockApi" in url for url in requests)
        passed("six production pages use formal copy and ignore stored Mock opt-in")

        page.goto(base + "/workbench", wait_until="networkidle")
        page.get_by_role("button", name="展开高级参数", exact=True).click()
        expect(page.locator("#n-cells-input")).to_have_value("64")
        expect(page.locator("#n-cells-input")).to_have_attribute("min", "64")
        expect(page.locator("#n-cells-input")).to_have_attribute("max", "4096")
        page.locator("input[type=radio][value=precomputed]").check()
        expect(page.locator("#n-cells-input")).to_have_count(0)
        page.locator("#perturbation-input").fill("ALDOA")
        page.locator("#perturbation-input").press("Enter")
        with page.expect_response(
            lambda response: response.url.endswith("/api/v1/runs") and response.request.method == "POST"
        ) as created_response:
            page.get_by_role("button", name="开始实验", exact=True).click()
        response = created_response.value
        assert response.status == 202, response.text()
        run_id = response.json()["run_id"]
        expect(page).to_have_url(base + "/workbench?run=" + run_id)
        expect(page.locator(".active-experiment")).to_contain_text("真实结果回放", timeout=30000)
        record = page.request.get(base + "/api/v1/runs/" + run_id).json()
        assert record["result_kind"] == "frozen_model_result"
        expect(page.get_by_role("link", name="解读本次实验", exact=True)).to_be_visible()
        page.screenshot(path=str(out / "real-result-workbench.png"), full_page=True)
        passed("formal sample controls and a real replay submission preserve genuine provenance")

        page.get_by_role("link", name="解读本次实验", exact=True).click()
        expect(page).to_have_url(base + "/demo?run=" + run_id)
        page.reload(wait_until="networkidle")
        expect(page.locator(".demo-source")).to_contain_text("真实结果回放")
        expect(page.get_by_role("navigation", name="解读章节")).to_be_visible()
        passed("result interpretation survives refresh and remains bound to the same run")

        page.goto(base + "/workbench?run=" + run_id + "&tab=cell", wait_until="networkidle")
        expect(page.locator(".scientific-figure img")).to_be_visible(timeout=120000)
        expect(page.locator(".scientific-figure figcaption")).to_contain_text("共同对照参考 PCA")
        page.screenshot(path=str(out / "scientific-cell-state.png"), full_page=True)
        page.goto(base + "/workbench?run=" + run_id + "&tab=validation", wait_until="networkidle")
        expect(page.get_by_text("匹配观测分析已完成", exact=True)).to_be_visible(timeout=30000)
        expect(page.get_by_text("训练排除关系未核实", exact=False).first).to_be_visible()
        page.screenshot(path=str(out / "matched-observations.png"), full_page=True)
        passed("common PCA and matched-observation views retain actual scientific interpretation")

        page.set_viewport_size({"width": 390, "height": 844})
        for route in ["/workbench", "/about", "/records", "/demo?run=" + run_id]:
            page.goto(base + route, wait_until="networkidle")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), route
        page.screenshot(path=str(out / "mobile-interpretation.png"), full_page=True)
        passed("formal pages remain readable at phone width without document overflow")

        offline = browser.new_context()
        offline.add_init_script("localStorage.setItem('celllens.mockMode.v1', 'on')")
        offline.route("**/api/v1/**", lambda route: route.abort())
        offline_page = offline.new_page()
        offline_page.goto(base + "/about", wait_until="networkidle")
        expect(offline_page.locator(".connection-banner")).to_be_visible()
        expect(offline_page.locator(".mock-banner")).to_have_count(0)
        expect(offline_page.get_by_text("已连接", exact=True)).to_have_count(0)
        offline.close()
        passed("an unavailable backend remains a connection error and never switches to synthetic data")
        assert not errors, errors
        report = {"url": base, "checks": checks, "run_id": run_id, "page_errors": errors, "passed": True}
        (out / "checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        browser.close()
        print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
