"""Verify metabolic score projections, task coloring, exports and unchanged frozen results."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from scripts.check_umap_overview import coordinates, digest_outputs, values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    base = parser.parse_args().url.rstrip("/")
    root = Path(__file__).resolve().parents[1]
    output = root / "reports/metabolic-projection-2026-10-12"
    output.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, reduced_motion="reduce")
        page.on("pageerror", lambda error: errors.append(str(error)))
        history = page.request.get(base + "/api/v1/experiments").json()
        records = [r for r in history["items"] if r["source"] == "online" and r["status"] == "completed"][:2]
        assert records, "A completed real run is required"
        before = {r["id"]: digest_outputs(root, r["id"]) for r in records}
        for record in records:
            run = record["id"]
            endpoint = base + f"/api/v1/runs/{run}/cell-state"
            documents = {}
            for method in ("pca", "umap"):
                response = page.request.get(
                    endpoint,
                    params={
                        "space": "metabolic",
                        "embedding": method,
                        "feature_kind": "task",
                    },
                    timeout=120000,
                )
                assert response.ok, response.text()
                document = documents[method] = response.json()
                assert document["embedding_space"] == "metabolic"
                assert document["embedding_preprocessing"]["scaling"] == "control-zscore"
                assert document["embedding_preprocessing"]["feature_count"] >= 2
                tasks = document["available_features"]["tasks"]
                response = page.request.get(
                    endpoint,
                    params={
                        "space": "metabolic",
                        "embedding": method,
                        "feature_kind": "task",
                        "feature_id": tasks[1],
                    },
                    timeout=120000,
                )
                assert response.ok, response.text()
                assert coordinates(response.json()) == coordinates(document)
                response = page.request.get(
                    endpoint,
                    params={
                        "space": "expression",
                        "embedding": method,
                        "feature_kind": "task",
                        "feature_id": document["feature"]["id"],
                    },
                    timeout=120000,
                )
                assert response.ok, response.text()
                expression = response.json()
                assert coordinates(expression) != coordinates(document)
                assert values(expression) == values(document)
                assert expression["distributions"] == document["distributions"]
                output.joinpath(f"{run}-{method}.json").write_text(
                    json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            assert coordinates(documents["pca"]) != coordinates(documents["umap"])
            page.goto(base + f"/demo?run={run}", wait_until="networkidle", timeout=120000)
            assert page.locator(".function-entry").count() == 0
            assert page.get_by_text("查看功能前后对比", exact=True).count() == 0
            page.goto(base + f"/demo?run={run}&tab=metabolism&view=function", wait_until="networkidle")
            expect(page.locator(".function-main .scientific-figure img")).to_be_visible(timeout=120000)
            expect(page.locator(".function-main .scientific-figure figcaption")).to_contain_text("共同 UMAP")
            expect(page.locator(".function-main .scientific-figure figcaption")).to_contain_text("个代谢任务")
            expect(page.get_by_role("button", name="UMAP", exact=True)).to_have_attribute(
                "aria-pressed", "true"
            )
            assert page.locator(".network-comparison").count() == 0
            assert page.locator(".function-main .state-feature-controls").count() == 0
            assert page.locator(".scientific-figure img").evaluate("img => img.naturalWidth > 0")
            page.locator(".function-main").screenshot(path=str(output / f"{run}-umap.png"))
            second = page.locator(".task-option").nth(1)
            second_id = second.get_attribute("data-task")
            second.click()
            expect(page.locator(".state-numbers h3")).to_contain_text(second_id, timeout=120000)
            with page.expect_download(timeout=120000) as capture:
                page.get_by_role("button", name="导出 JSON", exact=True).click()
            exported = output / capture.value.suggested_filename
            capture.value.save_as(exported)
            parsed = json.loads(exported.read_text(encoding="utf-8"))
            assert parsed["embedding_space"] == "metabolic" and parsed["feature"]["id"] == second_id
            assert coordinates(parsed) == coordinates(documents["umap"])
            page.get_by_role("button", name="PCA", exact=True).click()
            expect(page.locator(".scientific-figure figcaption")).to_contain_text(
                "共同对照参考 PCA", timeout=120000
            )
            page.locator(".function-main").screenshot(path=str(output / f"{run}-pca.png"))
            for file_format in ("SVG", "PDF", "PNG"):
                with page.expect_download(timeout=120000) as capture:
                    page.get_by_role("button", name="导出 " + file_format, exact=True).click()
                target = output / capture.value.suggested_filename
                capture.value.save_as(target)
                assert "_metabolic_pca_" in target.name
                if file_format == "SVG":
                    svg = target.read_text(encoding="utf-8")
                    assert "metabolic tasks" in svg and "control variance" in svg and "UMAP 1" not in svg
            page.locator(".association-evidence>summary").click()
            expect(page.locator(".reaction-browser")).to_be_visible(timeout=30000)
            expect(page.locator(".gpr-detail .gene-link").first).to_be_visible()
            assert page.locator(".gpr-detail code").count() == 0
            checks.append(
                {
                    "run": run,
                    "tasks_in_projection": parsed["embedding_preprocessing"]["feature_count"],
                    "cells": parsed["total_cells"],
                    "methods": ["pca", "umap"],
                }
            )
        for width in (768, 390):
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            page.screenshot(path=str(output / f"metabolic-{width}.png"), full_page=True)
        assert not errors, errors
        assert history == page.request.get(base + "/api/v1/experiments").json()
        assert before == {r["id"]: digest_outputs(root, r["id"]) for r in records}
        browser.close()
    output.joinpath("acceptance.json").write_text(
        json.dumps(
            {
                "checks": checks,
                "browser_errors": errors,
                "frozen_outputs_unchanged": True,
                "experiment_history_unchanged": True,
                "viewport_widths": [1600, 768, 390],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(checks, ensure_ascii=False))


if __name__ == "__main__":
    main()
