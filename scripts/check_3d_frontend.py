"""Real API and WebGL workbench checks. Start backend and Vite first."""

import argparse
import hashlib
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "frontend" / "3d"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    results, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.set_default_timeout(6000)
        page.on("pageerror", lambda error: errors.append(str(error)))

        def check(name, action):
            try:
                action()
                result = {"check": name, "passed": True}
            except Exception as exc:
                result = {"check": name, "passed": False, "error": str(exc)}
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)

        def state():
            return page.evaluate("""async () => {
                const {useSceneStore}=await import('/src/stores/scene.ts');
                const s=useSceneStore();
                return {status:s.renderStatus,selected:s.selected,visible:{...s.visible},
                    cut:s.cutaway,rotating:s.rotating,preset:s.cameraPreset};
            }""")

        def ready():
            expect(page.locator(".viewport-live")).to_have_text("3D", timeout=20000)

        def pixels():
            page.wait_for_timeout(250)
            return hashlib.sha256(page.locator(".cell-viewport canvas").screenshot()).hexdigest()

        page.goto(args.url + "/workbench", wait_until="networkidle")
        ready()

        def interaction():
            assert page.locator(".cell-viewport canvas").count() == 1
            assert state()["status"] == "ready"
            start = pixels()
            box = page.locator(".cell-viewport canvas").bounding_box()
            page.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + box["height"] * 0.5)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] * 0.6 + 80, box["y"] + box["height"] * 0.5 + 35, steps=12)
            page.mouse.up()
            page.wait_for_timeout(600)
            assert pixels() != start, "orbit did not change rendered geometry"
            start = pixels()
            page.mouse.wheel(0, -180)
            page.wait_for_timeout(600)
            assert pixels() != start, "zoom did not change rendered geometry"
            page.get_by_title("重置视角与剖切", exact=True).click()
            page.wait_for_timeout(900)
            page.locator(".organelle-label").filter(has_text="细胞核").click()
            assert state()["selected"] == "nucleus"
            expect(page.locator(".object-name")).to_have_text("细胞核")
            page.get_by_role("button", name="隐藏内质网", exact=True).click()
            assert state()["visible"]["er"] is False
            page.get_by_role("button", name="隐藏高尔基体", exact=True).click()
            page.get_by_role("button", name="隐藏线粒体", exact=True).click()
            page.locator(".object-select").filter(has_text="细胞膜").click()
            # Click exposed nuclear geometry rather than its DOM label.
            page.locator(".cell-viewport canvas").click(
                position={"x": box["width"] * 0.49, "y": box["height"] * 0.54}
            )
            assert state()["selected"] == "nucleus", "raycast failed to select exposed nucleus"
            page.get_by_role("button", name="显示内质网", exact=True).click()
            page.get_by_role("button", name="显示高尔基体", exact=True).click()
            page.get_by_role("button", name="显示线粒体", exact=True).click()
            start = pixels()
            page.get_by_title("膜壳剖切", exact=True).click()
            assert state()["cut"] is False
            assert pixels() != start
            page.get_by_title("重置视角与剖切", exact=True).click()
            page.wait_for_timeout(900)
            assert state()["cut"] is True
            page.locator(".organelle-label").filter(has_text="线粒体").click()

        check("real WebGL orbit, zoom, selection, layers, cut and reset", interaction)

        def export_image():
            with page.expect_download() as download:
                page.get_by_role("button", name="下载当前三维画面", exact=True).click()
            path = OUT / "rendered-cell.png"
            download.value.save_as(path)
            assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
            assert path.stat().st_size > 20000
            page.wait_for_timeout(4200)
            page.screenshot(path=str(OUT / "workbench.png"), full_page=True)

        check("export current rendered PNG", export_image)

        run_id = args.run_id
        if not run_id:
            for directory in sorted(
                (ROOT / "data/derived/runs").glob("run_*"), key=lambda f: f.stat().st_mtime, reverse=True
            ):
                response = page.request.get(args.url + "/api/v1/runs/" + directory.name)
                if (
                    response.ok
                    and response.json().get("status") == "completed"
                    and response.json()["request"]["mode"] == "online"
                ):
                    run_id = directory.name
                    break
        assert run_id, "no completed real online run found; pass --run-id"
        base = args.url + "/runs/" + run_id

        def real_result():
            page.goto(base + "?tab=structure", wait_until="networkidle")
            ready()
            expect(page.locator(".completed-line")).to_contain_text("计算完成")
            assert "Mock" not in page.locator("body").inner_text()
            page.get_by_role("tab", name="基因响应", exact=True).click()
            expect(page.locator("#gene-search")).to_be_visible()
            expect(page.locator(".gene-detail")).to_be_visible()
            page.locator("#gene-search").fill("MYC")
            expect(page.locator("table tbody tr")).to_have_count(1)
            page.locator("table tbody tr").first.click()
            expect(page.get_by_role("region", name="选中基因详情")).to_contain_text("MYC")
            with page.expect_download() as download:
                page.get_by_role("button", name="导出全部已加载 CSV", exact=True).click()
            path = OUT / "genes.csv"
            download.value.save_as(path)
            assert len(path.read_text(encoding="utf-8-sig").splitlines()) > 50
            page.locator("#gene-search").fill("")
            page.screenshot(path=str(OUT / "gene-analysis.png"), full_page=True)
            page.get_by_role("button", name="导出报告", exact=True).click()
            # Verify report itself via API independently of browser download event timing.
            report = page.request.get(args.url + "/api/v1/runs/" + run_id + "/report")
            assert report.ok and "<html" in report.text().lower()
            page.get_by_role("button", name="加入候选", exact=True).click()
            page.get_by_role("link", name="实验比较", exact=True).click()
            expect(page.get_by_text("已加载", exact=True)).to_be_visible()
            expect(
                page.get_by_role("row").filter(has=page.get_by_role("rowheader", name="来源", exact=True))
            ).to_contain_text("真实")

        check("real run, gene details/search, full CSV, HTML report and comparison", real_result)

        def demo():
            page.goto(args.url + "/demo?run=" + run_id, wait_until="networkidle")
            ready()
            page.screenshot(path=str(OUT / "presentation.png"), full_page=True)
            page.get_by_role("button", name="下一章 →", exact=True).click()
            expect(page.locator(".demo-title h1")).to_contain_text("怎样改变表达")
            expect(page.locator(".demo-result")).to_contain_text("基因响应")
            page.get_by_role("button", name="下一章 →", exact=True).click()
            expect(page.locator(".demo-task")).to_have_count(6)
            page.get_by_role("button", name="下一章 →", exact=True).click()
            expect(page.locator(".demo-result")).to_contain_text("未提供匹配观测")
            page.reload(wait_until="networkidle")
            expect(page.locator(".demo-title h1")).to_contain_text("都有出处")
            assert ("run=" + run_id) in page.url and "step=3" in page.url
            page.get_by_role("button", name="上一章", exact=False).click()
            page.get_by_role("button", name="自动播放", exact=True).click()
            expect(page.get_by_role("button", name="暂停演示", exact=True)).to_be_visible()
            page.get_by_role("button", name="暂停演示", exact=True).click()
            current_url = page.url
            page.wait_for_timeout(1200)
            assert page.url == current_url
            page.locator(".demo-title h1").click()
            page.keyboard.press("ArrowLeft")
            expect(page.locator(".demo-title h1")).to_contain_text("怎样改变表达")
            page.keyboard.press("Escape")
            expect(page).to_have_url(base + "?tab=structure")
            page.goto(args.url + "/demo?step=1", wait_until="networkidle")
            expect(page.locator(".demo-result")).to_contain_text("为结果，选择一次实验")
            assert page.locator(".demo-result canvas").count() == 0

        check("four chapters, URL restoration, pause, keyboard, return and honest empty result", demo)

        def responsive():
            for width, height in [(1440, 900), (1366, 768), (768, 1024), (390, 844)]:
                page.set_viewport_size({"width": width, "height": height})
                page.goto(args.url + "/workbench", wait_until="networkidle")
                ready()
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth+1"), (
                    f"overflow at {width}"
                )
                page.screenshot(path=str(OUT / f"workbench-{width}.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})

        check("1440, 1366, 768 and 390 widths without horizontal overflow", responsive)

        def fallback():
            fallback_context = browser.new_context(viewport={"width": 1280, "height": 900})
            fallback_context.add_init_script("""const original=HTMLCanvasElement.prototype.getContext;
                HTMLCanvasElement.prototype.getContext=function(kind,...rest){
                    if (kind==='webgl'||kind==='webgl2'||kind==='experimental-webgl') return null;
                    return original.call(this,kind,...rest);
                };""")
            fallback_page = fallback_context.new_page()
            fallback_page.goto(args.url + "/workbench", wait_until="networkidle")
            expect(fallback_page.locator(".viewport-live")).to_have_text("2D 示意")
            fallback_page.locator(".fallback-options button").filter(has_text="细胞核").click()
            expect(fallback_page.locator(".object-name")).to_have_text("细胞核")
            fallback_page.screenshot(path=str(OUT / "webgl-fallback.png"), full_page=True)
            fallback_context.close()

        check("WebGL unavailable shows interactive honest 2D fallback", fallback)

        def reduced():
            reduced_context = browser.new_context(reduced_motion="reduce")
            reduced_page = reduced_context.new_page()
            reduced_page.goto(args.url + "/workbench", wait_until="networkidle")
            expect(reduced_page.locator(".viewport-live")).to_have_text("3D")
            expect(reduced_page.get_by_title("已遵循系统减少动态效果设置", exact=True)).to_be_disabled()
            reduced_context.close()

        check("system reduced motion disables rotation", reduced)
        check(
            "no unhandled browser errors",
            lambda: (_ for _ in ()).throw(AssertionError(errors)) if errors else None,
        )
        browser.close()
    (OUT / "checks.json").write_text(
        json.dumps({"run_id": run_id, "checks": results, "pageerrors": errors}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
