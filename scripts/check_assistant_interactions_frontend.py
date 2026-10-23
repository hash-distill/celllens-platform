"""Cancellation, late replies, experiment changes and real UMAP/metabolic context acceptance."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8013")
    args = parser.parse_args()
    out = Path("reports/assistant-2026-10-22/browser")
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors, pending = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url + "/settings", wait_until="networkidle")
        page.get_by_label("模型名称", exact=True).fill("protocol-fixture")
        page.get_by_label("API Key", exact=True).fill("fixture-session-key")
        page.get_by_role("button", name="保存配置", exact=True).click()
        page.get_by_label("页面主题").select_option("light")
        runs = page.request.get(args.url + "/api/v1/runs?status=completed&limit=10").json()["items"]
        run_id = "run_41504106326f404d"
        other = next(row["run_id"] for row in runs if row["run_id"] != run_id)
        page.goto(args.url + "/demo?run=" + run_id + "&tab=cell", wait_until="networkidle")
        page.get_by_role("button", name="解读此图", exact=True).click(timeout=60000)
        panel = page.get_by_role("region", name="大模型辅助解读")
        dialog = page.get_by_role("dialog", name="AI 科研解读")

        def preview():
            panel.get_by_role("button", name="预览发送内容", exact=True).click()
            expect(panel.locator(".context-preview")).to_be_visible(timeout=60000)
            return json.loads(panel.locator(".raw-context").text_content())

        initial = preview()
        # Delay provider protocol fixtures, then abort or change source before they return.
        page.route("**/assistant/interpret", lambda route: pending.append(route))
        with page.expect_request("**/assistant/interpret"):
            panel.get_by_role("button", name="发送摘要并生成解读", exact=True).click()
        expect(panel.get_by_role("button", name="取消等待")).to_be_visible()
        panel.get_by_role("button", name="取消等待").click()
        assert pending

        def release(text):
            route = pending.pop(0)
            route.fulfill(
                json={
                    "text": text,
                    "model": "protocol-fixture",
                    "usage": {},
                    "base_url": "https://api.openai.com/v1",
                    "finish_reason": "stop",
                    "generated_at": "2026-10-22T04:00:00Z",
                }
            )

        release("late canceled response")
        expect(panel.locator(".generated-result")).to_have_count(0)
        with page.expect_request("**/assistant/interpret"):
            panel.get_by_role("button", name="发送摘要并生成解读", exact=True).click()
        expect(panel.get_by_role("button", name="取消等待")).to_be_visible()
        picker = page.get_by_label("选择逐细胞指标")
        values = picker.locator("option").evaluate_all("items => items.map(x => x.value)")
        picker.select_option(next(value for value in values if value != picker.input_value()))
        release("late previous feature response")
        expect(panel.locator(".context-preview")).to_have_count(0)
        expect(panel.locator(".generated-result")).to_have_count(0)
        expect(page.get_by_role("button", name="解读此图", exact=True)).to_be_visible(timeout=60000)
        page.keyboard.press("Escape")
        # Client navigation between experiments must clear old context even while drawer stays open.
        page.get_by_role("tab", name="基因响应", exact=True).click()
        page.get_by_role("button", name="解读当前结果", exact=True).click()
        data_preview = preview()
        assert data_preview["selection"]["view"] == "genes"
        page.get_by_role("button", name="收起 AI 解读", exact=True).click()
        page.get_by_role("button", name="AI 解读", exact=True).click()
        expect(panel.locator(".context-preview")).to_be_visible()
        # Same-document location navigation goes through the Vue router without a page reload.
        page.evaluate(
            "path => { history.pushState({}, '', path); dispatchEvent(new PopStateEvent('popstate')); }",
            "/demo?run=" + other + "&tab=genes",
        )
        expect(panel.locator(".context-preview")).to_have_count(0)
        expect(dialog.locator(".floating-source")).to_contain_text(
            next(row["request"]["perturbation"] for row in runs if row["run_id"] == other), timeout=20000
        )
        next_preview = preview()
        assert next_preview["source_id"] == other
        page.keyboard.press("Escape")
        # Overview UMAP and metabolic UMAP/PCA are real saved-input reconstructions, no model calls.
        page.goto(args.url + "/demo?run=" + run_id, wait_until="networkidle")
        page.get_by_role("button", name="解读此图", exact=True).click(timeout=90000)
        umap = preview()
        assert umap["data"]["figure"]["method"] == "joint-umap"
        assert umap["selection"]["space"] == "expression"
        page.keyboard.press("Escape")
        page.get_by_role("tab", name="代谢功能", exact=True).click()
        page.get_by_role("button", name="解读此图", exact=True).click(timeout=90000)
        metabolic = preview()
        assert metabolic["selection"]["space"] == "metabolic"
        assert metabolic["selection"]["feature_kind"] == "task"
        assert metabolic["data"]["figure"]["method"] == "joint-umap"
        assert len(metabolic["selection"]["feature_id"]) > 0
        page.keyboard.press("Escape")
        page.get_by_role("button", name="PCA", exact=True).click()
        page.get_by_role("button", name="解读此图", exact=True).click(timeout=60000)
        metabolic_pca = preview()
        assert metabolic_pca["data"]["figure"]["method"] == "control-reference-pca"
        assert metabolic_pca["selection"]["space"] == "metabolic"
        # Keep a clean side-by-side screenshot with real statistics and no fabricated model prose.
        page.screenshot(path=str(out / "metabolic-real-summary.png"), full_page=True)
        page.keyboard.press("Escape")
        page.get_by_role("tab", name="实测对比", exact=True).click()
        page.get_by_role("button", name="解读当前结果", exact=True).click()
        comparison = preview()
        assert comparison["selection"]["view"] == "comparison"
        # An old running backend must produce a clear restart message, never silently send wrong context.
        old_context = {key: value for key, value in comparison.items() if key != "selection"}
        page.route("**/assistant/context?**", lambda route: route.fulfill(json=old_context))
        panel.get_by_role("button", name="重新预览发送内容", exact=True).click()
        expect(panel.get_by_role("alert")).to_contain_text("重启")
        expect(panel.locator(".context-preview")).to_have_count(0)
        assert not pending
        assert not errors, errors
        (out / "interactions.json").write_text(
            json.dumps(
                {
                    "source": run_id,
                    "switched_source": other,
                    "page_errors": errors,
                    "checks": [
                        "cancel generation",
                        "late canceled reply ignored",
                        "late old feature ignored",
                        "minimized data preview retained",
                        "experiment switch resets context",
                        "expression UMAP",
                        "metabolic UMAP",
                        "metabolic PCA",
                "comparison context",
                "old backend requires restart instead of sending mismatched context",
                    ],
                    "hashes": [
                        value["context_sha256"]
                        for value in (
                            initial,
                            data_preview,
                            next_preview,
                            umap,
                            metabolic,
                            metabolic_pca,
                            comparison,
                        )
                    ],
                    "model_calls": "delayed protocol fixtures only; no external model calls",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        browser.close()
    print("Assistant interactions and real UMAP/metabolic contexts: OK")


if __name__ == "__main__":
    main()
