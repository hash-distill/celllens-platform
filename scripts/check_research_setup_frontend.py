"""Verify unified experiment setup; submission responses are browser fixtures."""

import argparse
import json
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    parser.add_argument("--output", default="reports/research-setup-2026-10-23")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    errors, posts, checks = [], [], []
    now = "2026-10-23T00:00:00Z"
    measured = dict(
        id="fixture_measured_setup",
        cell_line="K562",
        perturbation="ALDOA",
        max_cells=128,
        seed=17,
        status="failed",
        progress=0,
        message="浏览器提交测试夹具",
        created_at=now,
        updated_at=now,
        source_kind="measured",
        summary=None,
        error_message="测试夹具：未执行分析",
    )
    predicted = dict(
        run_id="fixture_prediction_setup",
        status="failed",
        stage_progress=0,
        request=dict(cell_line="K562", perturbation="ALDOA", mode="online", n_cells=128, seed=23),
        created_at=now,
        updated_at=now,
        warnings=[],
        error_code="BROWSER_FIXTURE",
        error_message="测试夹具：未执行预测",
    )

    def guard(route):
        request = route.request
        path = request.url.split("?")[0]
        if request.method == "POST":
            posts.append({"path": path, "body": request.post_data_json})
            if path.endswith("/measured/analyses"):
                route.fulfill(status=202, json=measured)
            elif path.endswith("/runs"):
                route.fulfill(
                    status=202, json=dict(run_id=predicted["run_id"], status="failed", cache_hit=False)
                )
            else:
                route.abort()
        elif path.endswith("/measured/analyses/fixture_measured_setup"):
            route.fulfill(json=measured)
        elif path.endswith("/runs/fixture_prediction_setup"):
            route.fulfill(json=predicted)
        elif request.method in ("GET", "HEAD"):
            route.continue_()
        else:
            route.abort()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1100}, reduced_motion="reduce")
        context.add_init_script("localStorage.setItem('celllens.theme','light')")
        context.route("**/api/**", guard)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_default_timeout(15000)
        page.set_default_navigation_timeout(120000)
        page.goto(args.url + "/research", wait_until="networkidle")
        expect(page.get_by_role("heading", name="研究分析", exact=True)).to_be_visible()
        kind = page.get_by_label("实验类型", exact=True)
        expect(kind).to_have_value("measured")
        expect(page.locator(".section-navigation")).to_have_count(0)
        expect(page.get_by_role("button", name="开始实测分析", exact=True)).to_be_disabled()
        page.locator("#perturbation-input").fill("ALDOA")
        page.get_by_role("option", name="ALDOA", exact=True).click()
        expect(page.get_by_role("button", name="开始实测分析", exact=True)).to_be_enabled()
        page.locator("#measured-cap").fill("128")
        page.locator("#measured-seed").fill("17")
        page.screenshot(path=str(output / "measured-light.png"), full_page=True)
        checks.append("single setup page, explicit type, measured source gating")

        kind.select_option("prediction")
        expect(page).to_have_url(re.compile(r"/research\?.*type=prediction"))
        expect(page.locator("#perturbation-input")).to_have_value("ALDOA")
        expect(page.locator("#measured-cap")).to_have_count(0)
        page.locator("#n-cells-input").fill("128")
        page.locator("#seed-input").fill("23")
        expect(page.get_by_role("button", name="运行模型预测", exact=True)).to_be_enabled()
        kind.select_option("measured")
        expect(page.locator("#perturbation-input")).to_have_value("ALDOA")
        expect(page.locator("#measured-cap")).to_have_value("128")
        expect(page.locator("#measured-seed")).to_have_value("17")
        kind.select_option("prediction")
        expect(page.locator("#n-cells-input")).to_have_value("128")
        expect(page.locator("#seed-input")).to_have_value("23")
        expect(page.locator(".source-coverage")).to_contain_text("该组合在固定源中有实测数据")
        page.screenshot(path=str(output / "prediction-light.png"), full_page=True)
        page.get_by_role("button", name="切换到深色模式", exact=True).click()
        page.screenshot(path=str(output / "prediction-dark.png"), full_page=True)
        page.get_by_role("button", name="切换到明亮模式", exact=True).click()
        checks.append("type switching retains shared selection and separate sampling drafts")
        page.reload(wait_until="networkidle")
        expect(kind).to_have_value("prediction")
        expect(page.locator("#perturbation-input")).to_have_value("ALDOA")
        page.locator("#n-cells-input").fill("128")
        page.locator("#seed-input").fill("23")
        page.get_by_role("button", name="运行模型预测", exact=True).click()
        page.wait_for_url("**/runs/fixture_prediction_setup")
        expect(page.locator(".active-experiment h1")).to_contain_text("K562 / ALDOA 扰动实验")
        assert posts[-1]["body"] == predicted["request"], posts
        checks.append("fixture: prediction submits online payload and opens prediction detail")
        page.get_by_role("button", name="复用参数", exact=True).click()
        expect(kind).to_have_value("prediction")
        expect(page.locator("#perturbation-input")).to_have_value("ALDOA")
        expect(page.locator("#n-cells-input")).to_have_value("128")
        checks.append("prediction result reuse returns to unified setup")

        kind.select_option("measured")
        page.locator("#measured-cap").fill("128")
        page.locator("#measured-seed").fill("17")
        page.get_by_role("button", name="开始实测分析", exact=True).click()
        page.wait_for_url("**/measured/fixture_measured_setup")
        expect(page.get_by_role("heading", name="实测结果解读", exact=True)).to_be_visible()
        assert posts[-1]["body"] == {
            k: measured[k] for k in ("cell_line", "perturbation", "max_cells", "seed")
        }, posts
        checks.append("fixture: measured submits observed-data payload and opens measured detail")

        for path, expected in [
            ("/measured?cell_line=RPE1&perturbation=ALDOA", "measured"),
            ("/workbench?cell_line=Jurkat&perturbation=ALDOA", "prediction"),
        ]:
            page.goto(args.url + path, wait_until="networkidle")
            expect(kind).to_have_value(expected)
            assert "/research" in page.url
        page.goto(args.url + "/workbench?run=fixture_prediction_setup&tab=genes", wait_until="networkidle")
        expect(page).to_have_url(re.compile(r"/runs/fixture_prediction_setup\?tab=genes"))
        page.goto(args.url + "/research?type=invalid", wait_until="networkidle")
        expect(kind).to_have_value("measured")
        page.get_by_role("navigation", name="主导航").get_by_role("link", name="研究分析", exact=True).click()
        expect(page.get_by_role("heading", name="研究分析", exact=True)).to_be_visible()
        checks.append("legacy deep links, prediction record links, unknown type and navigation")

        page.goto(args.url + "/data-catalog?cell_line=K562&perturbation=ALDOA", wait_until="networkidle")
        page.get_by_role("link", name="直接分析实测", exact=True).first.click()
        expect(kind).to_have_value("measured")
        expect(page.get_by_role("radio", name="K562", exact=True)).to_be_checked()
        expect(page.locator("#perturbation-input")).to_have_value("ALDOA")
        page.goto(args.url + "/data-catalog?cell_line=K562&perturbation=ALDOA", wait_until="networkidle")
        page.get_by_role("link", name="预测并评估", exact=True).first.click()
        expect(kind).to_have_value("prediction")
        expect(page.locator("#perturbation-input")).to_have_value("ALDOA")
        checks.append("data catalog links choose the experiment type and prefill the shared selection")

        # Coverage fixtures exercise unavailable inputs without altering server data.
        page.route(
            "**/api/v1/data-catalog/pair?**",
            lambda route: route.fulfill(
                json=dict(
                    source_status="not_in_source",
                    source_cell_count=0,
                    local_verified=False,
                    local_measured_cells=0,
                    model_supported=True,
                )
            ),
        )
        kind.select_option("measured")
        expect(page.locator(".coverage-state")).to_contain_text("当前固定源未收录")
        expect(page.get_by_role("button", name="开始实测分析", exact=True)).to_be_disabled()
        page.unroute("**/api/v1/data-catalog/pair?**")

        def model_unavailable(route):
            response = route.fetch()
            data = response.json()
            for item in data:
                item.update(online_ready=False, readiness_reasons=["测试夹具：预测服务未就绪"])
            route.fulfill(response=response, json=data)

        page.route("**/api/v1/catalog/contexts", model_unavailable)
        page.goto(
            args.url + "/research?type=prediction&cell_line=K562&perturbation=ALDOA", wait_until="networkidle"
        )
        expect(page.get_by_role("button", name="运行模型预测", exact=True)).to_be_disabled()
        kind.select_option("measured")
        expect(page.get_by_role("button", name="开始实测分析", exact=True)).to_be_enabled()
        page.locator("#measured-cap").fill("0")
        expect(page.get_by_role("button", name="开始实测分析", exact=True)).to_be_disabled()
        page.locator("#measured-cap").fill("128")
        page.locator("#measured-seed").fill("1.5")
        expect(page.get_by_role("button", name="开始实测分析", exact=True)).to_be_disabled()
        page.locator("#measured-seed").fill("17")
        expect(page.get_by_role("button", name="开始实测分析", exact=True)).to_be_enabled()
        page.get_by_role("radio", name="RPE1", exact=True).check()
        expect(page.locator("#perturbation-input")).to_have_value("")
        checks.append(
            "fixtures: missing source blocks measured; model unavailability leaves measured usable; "
            "sampling and context validation"
        )

        page.unroute("**/api/v1/catalog/contexts")
        page.goto(args.url + "/research?cell_line=K562&perturbation=ALDOA", wait_until="networkidle")
        page.set_viewport_size({"width": 1280, "height": 900})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=str(output / "measured-1280.png"), full_page=True)
        checks.append("1280px desktop layout has no horizontal overflow")
        for api, detail, selector in [
            ("/api/v1/measured/analyses", "/measured/", ".result-overview"),
            ("/api/v1/runs", "/runs/", ".run-result-overview"),
        ]:
            response = context.request.get(args.url + api + "?limit=100")
            assert response.ok
            data = response.json()
            record = next(row for row in data["items"] if row["status"] == "completed")
            page.goto(args.url + detail + record.get("id", record.get("run_id")), wait_until="networkidle")
            expect(page.locator(selector)).to_be_visible()
            page.screenshot(
                path=str(
                    output
                    / ("existing-measured.png" if detail == "/measured/" else "existing-prediction.png")
                ),
                full_page=True,
            )
            assert context.request.get(args.url + api + "?limit=100").json()["total"] == data["total"]
        checks.append(
            "real existing completed measured and prediction results still render; record counts unchanged"
        )
        assert len(posts) == 2, posts
        assert not errors, errors
        browser.close()
    result = dict(
        tested_url=args.url,
        checks=checks,
        page_errors=errors,
        submission_fixtures=posts,
        real_experiments_submitted=False,
    )
    (output / "checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
