"""UI acceptance with synthetic API credentials and intercepted provider requests only."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    output = Path("reports/ai-settings-2026-10-22/browser")
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        errors, calls = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def models(route):
            body = route.request.post_data_json
            assert set(body) == {"provider", "base_url", "api_key"}
            calls.append("models")
            route.fulfill(
                json={
                    "models": [
                        {"id": "lab-text-a", "name": "Lab Text A", "context_window": 64000},
                        {"id": "lab-text-b", "name": "Lab Text B"},
                    ],
                    "truncated": False,
                }
            )

        def completion(route):
            body = route.request.post_data_json
            assert body["reasoning_effort"] == "high"
            assert body["context_window"] == 64000 and body["max_tokens"] == 4096
            assert "name" not in body and "id" not in body
            calls.append("test")
            route.fulfill(json={"text": "连接成功", "model": body["model"], "finish_reason": "stop"})

        page.route("**/api/v1/assistant/models", models)
        page.route("**/api/v1/assistant/test", completion)
        page.goto(args.url + "/settings", wait_until="networkidle")
        expect(page.get_by_role("heading", name="大模型连接", exact=True)).to_be_visible()
        expect(page.get_by_text("有未保存的修改", exact=True)).to_have_count(0)
        page.get_by_label("连接名称", exact=True).fill("研究服务 A")
        page.get_by_label("API Key", exact=True).fill("ui-fixture-key-a")
        page.get_by_role("button", name="获取模型列表", exact=True).click()
        expect(page.get_by_role("group", name="服务端模型列表").get_by_role("button")).to_have_count(2)
        page.get_by_label("搜索模型", exact=True).fill("text-a")
        expect(page.get_by_role("group", name="服务端模型列表").get_by_role("button")).to_have_count(1)
        page.get_by_role("group", name="服务端模型列表").get_by_role("button").click()
        page.get_by_role("button", name="填入上下文窗口", exact=True).click()
        page.get_by_label("推理强度", exact=True).select_option("high")
        page.get_by_label("最大输出长度（token）", exact=True).fill("4096")
        page.get_by_role("button", name="保存配置", exact=True).click()
        expect(page.get_by_role("status")).to_contain_text("配置已保存")
        expect(page.get_by_text("有未保存的修改", exact=True)).to_have_count(0)
        profile_a = page.get_by_label("当前解读连接", exact=True).input_value()
        assert page.evaluate("!JSON.stringify(localStorage).includes('ui-fixture-key-a')")
        assert page.evaluate("JSON.stringify(sessionStorage).includes('ui-fixture-key-a')")
        page.get_by_role("button", name="测试连接", exact=True).click()
        expect(page.get_by_role("status")).to_contain_text("服务已返回文本")
        page.screenshot(path=str(output / "settings-light.png"), full_page=True)

        # Export must contain usable non-secret settings, including the context and effort.
        with page.expect_download() as download:
            page.get_by_role("button", name="导出当前配置", exact=True).click()
        exported = Path(download.value.path()).read_text(encoding="utf-8")
        assert "ui-fixture-key" not in exported and '"context_window": 64000' in exported
        (output / "export-without-secrets.json").write_text(exported, encoding="utf-8")

        page.get_by_role("button", name="导入配置", exact=True).click()
        page.get_by_label("配置内容", exact=True).fill(
            "AI_CONNECTION_NAME=研究服务 B\nOPENAI_BASE_URL=https://api.deepseek.com\n"
            "OPENAI_API_KEY=ui-fixture-key-b\nOPENAI_MODEL=manual-text\nAI_CONTEXT_WINDOW=65536"
        )
        calls_before = len(calls)
        page.get_by_role("button", name="解析并预览", exact=True).click()
        expect(page.get_by_role("heading", name="待导入 1 组连接", exact=True)).to_be_visible()
        assert len(calls) == calls_before
        page.get_by_role("button", name="导入为新连接", exact=True).click()
        expect(page.get_by_label("模型提供商", exact=True)).to_have_value("deepseek")
        expect(page.get_by_label("模型名称", exact=True)).to_have_value("manual-text")
        expect(page.get_by_label("当前解读连接", exact=True).locator("option")).to_have_count(2)
        page.get_by_label("当前解读连接", exact=True).select_option(profile_a)
        expect(page.get_by_label("API Key", exact=True)).to_have_value("ui-fixture-key-a")
        expect(page.get_by_label("推理强度", exact=True)).to_have_value("high")
        page.reload(wait_until="networkidle")
        expect(page.get_by_label("API Key", exact=True)).to_have_value("ui-fixture-key-a")
        expect(page.get_by_label("上下文窗口（token）", exact=True)).to_have_value("64000")

        # Failed discovery retains manual choices; late replies cannot cross providers.
        page.unroute("**/api/v1/assistant/models")
        page.route(
            "**/api/v1/assistant/models",
            lambda route: route.fulfill(
                status=502,
                json={
                    "detail": {
                        "code": "MODEL_DISCOVERY_REJECTED",
                        "message": "服务未提供模型列表接口，可以手动填写模型名称",
                    }
                },
            ),
        )
        page.get_by_role("button", name="获取模型列表", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("可以手动填写")
        expect(page.get_by_label("模型名称", exact=True)).to_have_value("lab-text-a")
        page.unroute("**/api/v1/assistant/models")
        late_replies = []
        page.route("**/api/v1/assistant/models", lambda route: late_replies.append(route))
        page.get_by_role("button", name="获取模型列表", exact=True).click()
        expect(page.get_by_role("button", name="获取中…", exact=True)).to_be_visible()
        page.get_by_label("模型提供商", exact=True).select_option("deepseek")
        for route in late_replies:
            route.fulfill(json={"models": [{"id": "stale-model", "name": "Stale"}], "truncated": False})
        expect(page.get_by_label("模型名称", exact=True)).to_have_value("")
        expect(page.get_by_role("group", name="服务端模型列表")).to_have_count(0)
        page.get_by_label("当前解读连接", exact=True).select_option(profile_a)

        # File import adds a connection without overwriting current or sending requests.
        page.get_by_role("button", name="导入配置", exact=True).click()
        page.get_by_label("选择 API 配置文件", exact=True).set_input_files(
            {
                "name": "generic.json",
                "mimeType": "application/json",
                "buffer": json.dumps(
                    {"name": "本地兼容服务", "baseURL": "http://127.0.0.1:11434/v1", "model": "local-text"}
                ).encode(),
            }
        )
        expect(page.get_by_role("heading", name="待导入 1 组连接", exact=True)).to_be_visible()
        page.get_by_role("button", name="导入为新连接", exact=True).click()
        expect(page.get_by_label("模型提供商", exact=True)).to_have_value("custom")
        expect(page.get_by_label("当前解读连接", exact=True).locator("option")).to_have_count(3)
        expect(page.get_by_text("该地址尚未加入部署允许列表。", exact=False)).to_be_visible()
        expect(page.get_by_role("button", name="获取模型列表", exact=True)).to_be_disabled()
        page.get_by_label("当前解读连接", exact=True).select_option(profile_a)

        # Invalid files report a static message, without reflecting a secret URL.
        page.get_by_role("button", name="导入配置", exact=True).click()
        page.get_by_label("配置内容", exact=True).fill(
            '{"base_url":"https://user:private-import@example.org/v1"}'
        )
        page.get_by_role("button", name="解析并预览", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("服务地址不能包含")
        assert "private-import" not in page.get_by_role("alert").inner_text()
        page.get_by_role("button", name="导入配置", exact=True).click()

        page.get_by_label("页面主题", exact=True).select_option("dark")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        page.screenshot(path=str(output / "settings-dark.png"), full_page=True)
        for width in (1920, 1440, 1280, 1024):
            page.set_viewport_size({"width": width, "height": 950})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), width
        page.screenshot(path=str(output / "settings-narrow.png"), full_page=True)
        page.get_by_role("button", name="清除 API Key", exact=True).click()
        expect(page.get_by_label("API Key", exact=True)).to_have_value("")
        assert page.evaluate("!JSON.stringify(sessionStorage).includes('ui-fixture-key-a')")
        assert not errors, errors
        report = {
            "passed": True,
            "provider_requests": calls,
            "real_provider_called": False,
            "checks": [
                "model search and selection",
                "actual parameter payload",
                "JSON export excludes keys",
                "dotenv preview without requests",
                "file import",
                "profile isolation and reload",
                "safe invalid import",
                "light/dark",
                "1920/1440/1280/1024 desktop widths",
                "clear session key",
            ],
            "page_errors": errors,
        }
        (output / "evidence.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        browser.close()
        print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
