"""Check real UMAP overview, independent PCA detail, exports and frozen-result preservation."""

import argparse
import hashlib
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def digest_outputs(root, run_id):
    directory = root / "data/derived/runs" / run_id
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.iterdir()
        if path.is_file()
    }


def values(document):
    return [(point["cell_id"], point["source"], point["value"]) for point in document["points"]]


def coordinates(document):
    return [(point["cell_id"], point["x"], point["y"]) for point in document["points"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    root = Path(__file__).resolve().parents[1]
    output = root / "reports/umap-overview-2026-10-11"
    output.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        page.on("pageerror", lambda error: errors.append(str(error)))
        history = page.request.get(base + "/api/v1/experiments").json()
        records = [
            item for item in history["items"] if item["source"] == "online" and item["status"] == "completed"
        ][:2]
        assert records, "A completed real experiment is required"
        before = {item["id"]: digest_outputs(root, item["id"]) for item in records}
        for record in records:
            run = record["id"]
            endpoint = base + f"/api/v1/runs/{run}/cell-state"
            pca_response = page.request.get(endpoint, timeout=120000)
            assert pca_response.ok, pca_response.text()
            pca = pca_response.json()
            response = page.request.get(endpoint + "?embedding=umap", timeout=120000)
            assert response.ok, response.text()
            umap = response.json()
            assert umap["method"] == "joint-umap" and umap["fit_source"] == "joint"
            assert not umap["explained_variance_ratio"]
            assert umap["embedding_parameters"]["preprocessing"]["n_components"] > 2
            assert umap["embedding_parameters"]["random_state"] == 42
            assert umap["distributions"] == pca["distributions"] and values(umap) == values(pca)
            assert umap["provenance"] == pca["provenance"]
            assert coordinates(umap) != coordinates(pca)
            output.joinpath(run + "-umap.json").write_text(
                json.dumps(umap, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            page.goto(base + f"/demo?run={run}", wait_until="networkidle", timeout=120000)
            expect(page.locator(".projection-preview")).to_have_attribute("open", "")
            expect(page.locator(".scientific-figure img")).to_be_visible(timeout=120000)
            expect(page.locator(".scientific-figure img")).to_have_js_property("complete", True)
            expect(page.locator(".scientific-figure figcaption")).to_contain_text("共同 UMAP")
            assert page.locator(".scientific-figure img").evaluate("image => image.naturalWidth > 0")
            page.locator(".scientific-cell-state").screenshot(path=str(output / (run + "-overview.png")))
            task = umap["available_features"]["tasks"][0]
            response = page.request.get(
                endpoint,
                params={"embedding": "umap", "feature_kind": "task", "feature_id": task},
                timeout=120000,
            )
            assert response.ok, response.text()
            assert coordinates(response.json()) == coordinates(umap)
            page.get_by_label("指标类型", exact=True).select_option("task")
            expect(page.locator(".state-numbers h3")).to_contain_text("scCellFie", timeout=120000)
            expect(page.locator(".scientific-figure figcaption")).to_contain_text("共同 UMAP")
            for file_format in ("JSON", "SVG"):
                with page.expect_download(timeout=120000) as capture:
                    page.get_by_role("button", name="导出 " + file_format, exact=True).click()
                target = output / capture.value.suggested_filename
                capture.value.save_as(target)
                assert "_umap_" in target.name
                if file_format == "JSON":
                    assert json.loads(target.read_text(encoding="utf-8"))["method"] == "joint-umap"
                else:
                    svg = target.read_text(encoding="utf-8")
                    assert "UMAP 1" in svg and "Joint UMAP" in svg and "control variance" not in svg
            page.get_by_role("tab", name="表达状态分布", exact=True).click()
            expect(page.locator(".scientific-figure figcaption")).to_contain_text(
                "共同对照参考 PCA", timeout=120000
            )
            checks.append(
                run + ": real shared UMAP, feature-stable coordinates, matching exports and PCA detail"
            )
        page.goto(base + f"/demo?run={records[0]['id']}", wait_until="networkidle", timeout=120000)
        expect(page.locator(".scientific-figure img")).to_be_visible(timeout=120000)
        for width in (390, 768):
            page.set_viewport_size({"width": width, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            page.locator(".scientific-cell-state").screenshot(path=str(output / f"umap-{width}.png"))
        page.get_by_role("button", name="切换深色", exact=True).click()
        page.locator(".scientific-cell-state").screenshot(path=str(output / "umap-dark.png"))
        assert {item["id"]: digest_outputs(root, item["id"]) for item in records} == before
        assert page.request.get(base + "/api/v1/experiments").json() == history
        assert not errors, errors
        checks.append("Mobile and dark layouts; unchanged experiment records and all saved output hashes")
        output.joinpath("acceptance.json").write_text(
            json.dumps(
                {
                    "checks": checks,
                    "page_errors": errors,
                    "history_unchanged": True,
                    "artifacts_unchanged": True,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        browser.close()
    print("Real UMAP overview, PCA detail, exports and result preservation: OK")


if __name__ == "__main__":
    main()
