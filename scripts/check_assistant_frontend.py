"""Browser acceptance: actual source summaries, mocked external completion, no GPU/model calls."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--browser-executable")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    output = Path("reports/assistant-ui-2026-10-11")
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.browser_executable, headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/settings")
        expect(page.get_by_role("heading", name="系统设置", exact=True)).to_be_visible()
        theme = page.get_by_label("页面主题")
        theme.select_option("dark")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        page.reload()
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        theme.select_option("system")
        page.emulate_media(color_scheme="dark")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        page.emulate_media(color_scheme="light")
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        page.get_by_label("模型名称", exact=True).fill("protocol-fixture-model")
        page.get_by_label("API Key", exact=True).fill("fixture-session-key")
        page.get_by_role("button", name="保存配置", exact=True).click()
        expect(page.get_by_role("status").filter(has_text="配置已保存")).to_be_visible()
        assert page.evaluate("sessionStorage.getItem('celllens.api-key') !== null")
        assert page.evaluate("!JSON.stringify(localStorage).includes('fixture-session-key')")
        page.route(
            "**/api/v1/assistant/test",
            lambda route: route.fulfill(
                json={
                    "text": "连接成功",
                    "model": "protocol-fixture-model",
                    "usage": {},
                    "generated_at": "2026-10-11T01:00:00Z",
                    "finish_reason": "stop",
                }
            ),
        )
        page.get_by_role("button", name="测试连接", exact=True).click()
        expect(page.get_by_role("status").filter(has_text="服务已返回文本")).to_be_visible()
        page.reload()
        expect(page.get_by_label("模型名称", exact=True)).to_have_value("protocol-fixture-model")
        expect(page.get_by_label("API Key", exact=True)).to_have_value("fixture-session-key")
        page.get_by_role("button", name="切换深色", exact=True).click()
        page.screenshot(path=str(output / "settings-dark.png"), full_page=True)
        page.get_by_role("button", name="直达底部", exact=True).click()
        assert page.evaluate("window.scrollY + innerHeight >= document.documentElement.scrollHeight - 2")
        page.get_by_role("button", name="直达顶部", exact=True).click()
        assert page.evaluate("window.scrollY") == 0

        runs = page.request.get(base + "/api/v1/runs?status=completed&limit=1").json()["items"]
        analyses = page.request.get(base + "/api/v1/analyses?status=completed&limit=1").json()["items"]
        targets = [("run", runs[0]["run_id"], "/workbench?run=" + runs[0]["run_id"])] if runs else []
        if analyses:
            targets.append(("analysis", analyses[0]["id"], "/analyses/" + analyses[0]["id"]))
        assert len(targets) == 2, "Both completed source types are required for this acceptance"
        checked = []
        for kind, identifier, path in targets:
            page.goto(base + path)
            panel = page.get_by_role("region", name="大模型辅助解读")
            expect(panel).to_be_visible()
            expect(panel.locator(".generated-result")).to_have_count(0)
            panel.get_by_role("button", name="预览发送内容", exact=True).click()
            expect(panel.locator(".context-preview")).to_be_visible()
            preview = json.loads(panel.locator("pre").inner_text())
            assert preview["source_kind"] == kind and preview["source_id"] == identifier
            assert "projection" not in preview["data"] and "api_key" not in preview
            assert len(preview["context_sha256"]) == 64

            def completion(route, _request, expected=preview):
                body = route.request.post_data_json
                assert body["context_sha256"] == expected["context_sha256"]
                assert body["source_id"] == expected["source_id"]
                assert "data" not in body
                route.fulfill(
                    json={
                        "text": '<img src=x onerror="window.unsafeModel=true">协议校验文本',
                        "model": body["model"],
                        "base_url": body["base_url"],
                        "finish_reason": "length",
                        "usage": {"total_tokens": 20},
                        "generated_at": "2026-10-11T01:00:00Z",
                        "source_id": body["source_id"],
                        "context_sha256": body["context_sha256"],
                        "purpose": body["purpose"],
                    }
                )

            page.route("**/api/v1/assistant/interpret", completion)
            panel.get_by_role("button", name="发送摘要并生成解读", exact=True).click()
            expect(panel.locator(".generated-text")).to_contain_text("协议校验文本")
            expect(panel.locator(".generated-text img")).to_have_count(0)
            expect(panel.get_by_text("输出达到预算上限", exact=False)).to_be_visible()
            assert page.evaluate("window.unsafeModel === undefined")
            with page.expect_download() as downloaded:
                panel.get_by_role("button", name="下载解读与来源 JSON", exact=True).click()
            downloaded.value.save_as(output / (kind + "-protocol-fixture.json"))
            checked.append(
                {"source_kind": kind, "source_id": identifier, "context_sha256": preview["context_sha256"]}
            )
            page.unroute("**/api/v1/assistant/interpret")

        for width in (390, 768, 1280):
            page.set_viewport_size({"width": width, "height": 900})
            for path in ("/", "/settings", "/records", "/datasets", targets[0][2], targets[1][2]):
                page.goto(base + path)
                expect(page.locator(".utility-rail")).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (width, path)
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(base + "/settings")
        page.get_by_label("页面主题").select_option("light")
        page.get_by_role("button", name="清除 API Key", exact=True).click()
        expect(page.get_by_label("API Key", exact=True)).to_have_value("")
        assert page.evaluate("sessionStorage.getItem('celllens.api-key') === null")
        page.screenshot(path=str(output / "settings-light.png"), full_page=True)
        page.goto(base + targets[0][2])
        panel = page.get_by_role("region", name="大模型辅助解读")
        panel.get_by_role("button", name="预览发送内容", exact=True).click()
        expect(panel.get_by_role("button", name="发送摘要并生成解读", exact=True)).to_be_disabled()
        assert not errors, errors
        assert not context.cookies()
        output.joinpath("acceptance.json").write_text(
            json.dumps(
                {
                    "sources": checked,
                    "external_completion": "mocked_protocol_only",
                    "page_errors": errors,
                    "checks": [
                        "themes and system changes",
                        "session-only key",
                        "clear key",
                        "top/bottom",
                        "source preview",
                        "plain text rendering",
                        "JSON download",
                        "responsive layouts",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        browser.close()
    print("Theme, settings, utility rail and read-only assistant browser acceptance: OK")


if __name__ == "__main__":
    main()
