"""Browser acceptance: real local summaries, controlled model replies; no GPU submissions."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--run", default="run_41504106326f404d")
    args = parser.parse_args()
    out = Path("reports/assistant-2026-10-22/browser")
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors, sent = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url + "/", wait_until="networkidle")
        expect(page.get_by_role("button", name="AI 解读", exact=True)).to_be_visible()
        page.get_by_role("button", name="AI 解读", exact=True).click()
        dialog = page.get_by_role("dialog", name="AI 科研解读")
        expect(dialog).to_be_visible()
        expect(dialog.get_by_text("选择一个实验，开始解读", exact=False)).to_be_visible()
        page.keyboard.press("Escape")
        expect(page.get_by_role("button", name="AI 解读", exact=True)).to_be_focused()
        page.goto(args.url + "/settings", wait_until="networkidle")
        expect(page.get_by_role("heading", name="系统设置", exact=True)).to_be_visible()
        page.get_by_label("模型名称", exact=True).fill("protocol-fixture")
        page.get_by_label("API Key", exact=True).fill("fixture-session-key")
        page.get_by_role("button", name="保存配置", exact=True).click()
        assert page.evaluate("!JSON.stringify(localStorage).includes('fixture-session-key')")
        page.goto(args.url + "/demo?run=" + args.run + "&tab=cell", wait_until="networkidle")
        expect(page.get_by_role("button", name="解读此图", exact=True)).to_be_visible(timeout=60000)
        page.get_by_role("button", name="解读此图", exact=True).click()
        panel = page.get_by_role("region", name="大模型辅助解读")
        expect(panel.get_by_label("解读任务")).to_have_value("figure")
        expect(panel.locator(".context-preview")).to_have_count(0)
        page.get_by_role("button", name="预览发送内容", exact=True).click()
        expect(panel.locator(".context-preview")).to_be_visible(timeout=60000)
        panel.get_by_text("完整发送摘要", exact=False).click()
        preview = json.loads(panel.locator(".raw-context").inner_text())
        assert preview["selection"]["view"] == "chart"
        assert preview["data"]["figure"]["method"] == "control-reference-pca"
        assert "points" not in preview["data"]["figure"]
        assert "ecdf" not in json.dumps(preview["data"]["figure"])
        panel.get_by_label("补充问题").fill("请说明当前指标的预测变化和局限")

        def completion(route):
            payload = route.request.post_data_json
            sent.append(payload)
            assert payload["context_sha256"] == preview["context_sha256"]
            assert "data" not in payload
            assert payload["question"] == "请说明当前指标的预测变化和局限"
            route.fulfill(
                json={
                    "text": '<img src=x onerror="window.unsafeModel=true">协议模拟：均值变化仅为描述统计。',
                    "model": payload["model"],
                    "base_url": payload["base_url"],
                    "finish_reason": "length",
                    "usage": {"total_tokens": 20},
                    "generated_at": "2026-10-22T03:00:00Z",
                    "source_id": args.run,
                    "context_sha256": payload["context_sha256"],
                    "selection": preview["selection"],
                    "question": payload["question"],
                    "purpose": payload["purpose"],
                }
            )

        page.route("**/assistant/interpret", completion)
        panel.get_by_role("button", name="发送摘要并生成解读", exact=True).click()
        expect(panel.locator(".generated-text")).to_contain_text("协议模拟")
        expect(panel.locator(".generated-text img")).to_have_count(0)
        assert page.evaluate("window.unsafeModel === undefined")
        expect(panel.get_by_text("输出达到长度上限", exact=False)).to_be_visible()
        with page.expect_download() as downloaded:
            panel.get_by_role("button", name="下载解读与来源 JSON", exact=True).click()
        downloaded.value.save_as(out / "protocol-fixture.json")
        exported = json.loads((out / "protocol-fixture.json").read_text(encoding="utf-8"))
        assert exported["interpretation"]["question"] == "请说明当前指标的预测变化和局限"
        assert "fixture-session-key" not in json.dumps(exported)
        page.get_by_role("button", name="收起 AI 解读", exact=True).click()
        expect(dialog).to_be_hidden()
        page.get_by_role("button", name="AI 解读", exact=True).click()
        expect(panel.locator(".generated-text")).to_contain_text("协议模拟")
        page.screenshot(path=str(out / "assistant-light.png"), full_page=True)
        # Changing the selected figure invalidates the previous preview and answer.
        picker = page.get_by_label("选择逐细胞指标")
        options = picker.locator("option").evaluate_all("items => items.map(x => x.value)")
        alternative = next(value for value in options if value != picker.input_value())
        picker.select_option(alternative)
        expect(panel.locator(".context-preview")).to_have_count(0)
        expect(panel.locator(".generated-text")).to_have_count(0)
        expect(page.get_by_role("button", name="解读此图", exact=True)).to_be_visible(timeout=60000)
        expect(dialog.locator(".focus-label")).to_contain_text(alternative)
        page.keyboard.press("Escape")
        page.get_by_role("tab", name="基因响应", exact=True).click()
        page.get_by_role("button", name="AI 解读", exact=True).click()
        expect(panel.get_by_label("解读任务")).to_have_value("genes")
        page.get_by_role("button", name="预览发送内容", exact=True).click()
        expect(panel.locator(".context-preview")).to_be_visible(timeout=20000)
        page.keyboard.press("Escape")
        page.get_by_role("link", name="实验记录", exact=True).first.click()
        page.get_by_role("button", name="AI 解读", exact=True).click()
        expect(dialog.locator(".assistant-empty")).to_be_visible()
        expect(panel).to_have_count(0)
        page.keyboard.press("Escape")
        # Settings remain reachable and clearing a key disables generation.
        page.goto(args.url + "/settings", wait_until="networkidle")
        page.get_by_role("button", name="清除 API Key", exact=True).click()
        assert page.evaluate("sessionStorage.getItem('celllens.api-key') === null")
        page.get_by_label("页面主题").select_option("dark")
        page.goto(args.url + "/demo?run=" + args.run + "&tab=cell", wait_until="networkidle")
        page.get_by_role("button", name="解读此图", exact=True).click(timeout=60000)
        page.get_by_role("button", name="预览发送内容", exact=True).click()
        expect(panel.get_by_role("button", name="发送摘要并生成解读", exact=True)).to_be_disabled(
            timeout=60000
        )
        for width in (1280, 1440, 1920):
            page.set_viewport_size({"width": width, "height": 900})
            bounds = dialog.bounding_box()
            assert bounds and bounds["x"] >= 0 and bounds["y"] >= 0
            assert bounds["x"] + bounds["width"] <= width
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(out / "assistant-dark.png"), full_page=True)
        assert not errors, errors
        (out / "acceptance.json").write_text(
            json.dumps(
                {
                    "run_id": args.run,
                    "context_sha256": preview["context_sha256"],
                    "provider_response": "controlled protocol fixture; no real provider generation",
                    "page_errors": errors,
                    "generation_requests": len(sent),
                    "checks": [
                        "rail and settings",
                        "real figure summary",
                        "custom question",
                        "plain text",
                        "download",
                        "minimize preserves result",
                        "feature invalidates result",
                        "data tab focus",
                        "navigation clears source",
                        "key clearing",
                        "desktop dark/light",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        browser.close()
    print("Assistant figure browser acceptance: OK (provider response is a protocol fixture)")


if __name__ == "__main__":
    main()
