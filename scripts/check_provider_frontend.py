"""Provider settings/navigation acceptance; all model responses are mocked locally."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    output = Path("reports/providers-2026-10-11")
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        page = context.new_page()
        errors, calls = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        presets = page.request.get(base + "/api/v1/assistant/capabilities").json()["providers"]

        def complete(route):
            body = route.request.post_data_json
            calls.append(body)
            route.fulfill(
                json={
                    "text": "Synthetic provider protocol fixture: " + body["provider"],
                    "provider": body["provider"],
                    "model": body["model"],
                    "base_url": body["base_url"],
                    "finish_reason": "stop",
                    "usage": {},
                    "generated_at": "2026-10-11T01:00:00Z",
                    "source_id": body.get("source_id"),
                    "context_sha256": body.get("context_sha256"),
                }
            )

        page.route("**/api/v1/assistant/test", complete)
        page.route("**/api/v1/assistant/interpret", complete)
        page.goto(base + "/settings", wait_until="networkidle")
        selector = page.get_by_label("模型提供商", exact=True)
        expect(selector.locator("option")).to_have_text([preset["label"] for preset in presets])
        expect(page.get_by_role("navigation", name="设置分类").locator("a")).to_have_text(
            ["外观", "大模型连接"]
        )
        expect(page.get_by_role("heading", name="分析服务", exact=True)).to_have_count(0)
        expect(page.get_by_label("最大输出长度（token）", exact=True)).not_to_be_visible()
        page.get_by_text("高级选项 · 输出长度与接口参数", exact=True).click()
        expect(page.get_by_label("最大输出长度（token）", exact=True)).to_have_value("2048")
        expect(page.locator(".advanced-options")).to_contain_text("不等于字数")
        nav = page.get_by_role("navigation", name="主导航")
        expect(nav.locator("a")).to_have_text(
            ["首页", "实验工作台", "实验记录", "结果解读", "实验比较", "使用说明"]
        )
        # Switching providers fills server-provided defaults and clears the old draft model/key.
        for preset in presets[1:]:
            page.get_by_label("模型名称", exact=True).fill("old-fixture-model")
            page.get_by_label("API Key", exact=True).fill("old-fixture-key")
            selector.select_option(preset["id"])
            expect(page.get_by_label("服务基础地址", exact=True)).to_have_value(preset["base_url"])
            expect(page.get_by_label("模型名称", exact=True)).to_have_value("")
            expect(page.get_by_label("API Key", exact=True)).to_have_value("")
            expect(page.get_by_role("button", name="测试连接", exact=True)).to_be_disabled()
        records = page.request.get(base + "/api/v1/experiments?source=online&status=completed").json()[
            "items"
        ]
        run_id = records[0]["id"]
        for provider in ("gemini", "anthropic"):
            page.goto(base + "/settings", wait_until="networkidle")
            page.get_by_label("模型提供商", exact=True).select_option(provider)
            expect(page.get_by_label("输出长度参数", exact=True)).to_have_count(0)
            page.get_by_label("模型名称", exact=True).fill(provider + "-protocol-fixture")
            page.get_by_label("API Key", exact=True).fill(provider + "-fixture-key")
            page.get_by_role("button", name="测试连接", exact=True).click()
            expect(page.get_by_role("status").filter(has_text="服务已返回文本")).to_be_visible()
            assert calls[-1]["provider"] == provider and calls[-1]["token_parameter"] == "max_tokens"
            page.get_by_role("button", name="保存配置", exact=True).click()
            expect(page.get_by_role("status").filter(has_text="配置已保存")).to_be_visible()
            assert provider + "-fixture-key" not in page.evaluate("JSON.stringify(localStorage)")
            page.reload(wait_until="networkidle")
            expect(page.get_by_label("模型提供商", exact=True)).to_have_value(provider)
            expect(page.get_by_label("模型名称", exact=True)).to_have_value(provider + "-protocol-fixture")
            expect(page.get_by_label("API Key", exact=True)).to_have_value(provider + "-fixture-key")
            page.screenshot(path=str(output / (provider + "-settings.png")), full_page=True)
            page.goto(base + "/demo?run=" + run_id, wait_until="networkidle")
            expect(page.get_by_role("link", name="查看基因与任务范围 ↗").first).to_be_visible()
            before = len(calls)
            page.get_by_role("button", name="AI 解读", exact=True).click()
            page.get_by_role("button", name="预览发送内容", exact=True).click()
            expect(page.locator(".context-preview")).to_be_visible()
            assert len(calls) == before
            page.get_by_role("button", name="发送摘要并生成解读", exact=True).click()
            expect(page.locator(".generated-text")).to_contain_text(provider)
            assert calls[-1]["provider"] == provider and calls[-1]["source_id"] == run_id
            assert calls[-1]["api_key"] == provider + "-fixture-key"
            page.get_by_role("link", name="实验比较", exact=True).first.click()
            expect(page).to_have_url(base + "/compare")
            expect(page.locator(".header-nav a.active")).to_contain_text("实验比较")
        page.goto(base + "/settings", wait_until="networkidle")
        page.get_by_role("button", name="切换深色", exact=True).click()
        page.screenshot(path=str(output / "claude-settings-dark.png"), full_page=True)
        for width in (390, 768):
            page.set_viewport_size({"width": width, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            page.screenshot(path=str(output / f"claude-settings-{width}.png"), full_page=True)
        # Legacy preferences lacking provider still recover their model, budget and session key.
        legacy = browser.new_context()
        legacy.add_init_script("""
            localStorage.setItem('celllens.model', JSON.stringify({base_url:'https://api.deepseek.com',model:'legacy-fixture',max_tokens:1024,token_parameter:'max_tokens'}));
            sessionStorage.setItem('celllens.api-key','legacy-fixture-key');
        """)
        old = legacy.new_page()
        old.goto(base + "/settings", wait_until="networkidle")
        expect(old.get_by_label("模型提供商", exact=True)).to_have_value("deepseek")
        expect(old.get_by_label("模型名称", exact=True)).to_have_value("legacy-fixture")
        expect(old.get_by_label("API Key", exact=True)).to_have_value("legacy-fixture-key")
        assert not errors, errors
        # Record only metadata; no fixture credentials are retained in reports.
        output.joinpath("acceptance.json").write_text(
            json.dumps(
                {
                    "providers": [preset["id"] for preset in presets],
                    "requests": [
                        {
                            "provider": body["provider"],
                            "model": body["model"],
                            "source_id": body.get("source_id"),
                        }
                        for body in calls
                    ],
                    "external_model_calls": "mocked_protocol_only",
                    "legacy_migration": True,
                    "navigation_swapped": True,
                    "analysis_service_removed": True,
                    "output_length_explained_in_advanced_options": True,
                    "page_errors": errors,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        browser.close()
    print(
        "Provider defaults, saved selection, Gemini/Claude interpretation, "
        "legacy migration and navigation: OK"
    )


if __name__ == "__main__":
    main()
