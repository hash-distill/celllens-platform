"""Browser fixtures for download controls, validation and stale-request cancellation.

HTTP responses in this script are controlled fixtures, not real backend ZIP/CSV evidence.
All service requests are GET/HEAD; no experiments are created or changed.
"""

import argparse
import io
import json
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5183")
    parser.add_argument("--run", default="run_41504106326f404d")
    parser.add_argument("--phase", default="fixture-green")
    args = parser.parse_args()
    out = Path(__file__).resolve().parents[1] / "reports/export-fixes-2026-10-22/frontend" / args.phase
    out.mkdir(parents=True, exist_ok=True)
    checks, errors, requests, downloads = [], [], [], []
    mode = {"genes": "partial", "export": "ok", "hold": False}
    held = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("download", lambda download: downloads.append(download.suggested_filename))

        def route_api(route):
            if route.request.method not in ("GET", "HEAD"):
                raise AssertionError("unexpected mutation request: " + route.request.method)
            parsed = urlparse(route.request.url)
            query = parse_qs(parsed.query)
            if parsed.path.endswith("/genes"):
                doc = route.fetch().json()
                doc["items"] = doc["items"][:1]
                doc["truncated"] = True
                doc["limit"] = 1
                if mode["genes"] == "zero":
                    doc["items"][0].update(control=1, predicted=1, predicted_delta=0)
                route.fulfill(json=doc)
            elif parsed.path.endswith("/export/table"):
                requests.append(query)
                if mode["export"] == "html":
                    route.fulfill(status=200, content_type="text/html", body="<html>error</html>")
                elif mode["export"] == "error":
                    route.fulfill(status=409, json={"detail": {"message": "fixture export unavailable"}})
                else:
                    table = query["table"][0]
                    assert query["population"] == ["original"]
                    key = "gene" if table == "genes" else "id"
                    csv = (
                        f"\ufeff{key},control,predicted,predicted_delta,run_id,population,units\r\n"
                        f"A,1,2,1,{args.run},original,mean(log1p(CP10K))\r\n"
                        f"ZERO,1,1,0,{args.run},original,mean(log1p(CP10K))\r\n"
                    )
                    route.fulfill(
                        content_type="text/csv; charset=utf-8",
                        headers={
                            "Content-Disposition": f'attachment; filename="fixture-complete-{table}.csv"'
                        },
                        body=csv,
                    )
            elif parsed.path.endswith("/export"):
                requests.append(query)
                if mode["hold"]:
                    held.append(route)
                    return
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, "w") as archive:
                    archive.writestr("FIXTURE.txt", query["package"][0])
                route.fulfill(
                    content_type="application/zip",
                    headers={
                        "Content-Disposition": f'attachment; filename="fixture-{query["package"][0]}.zip"'
                    },
                    body=stream.getvalue(),
                )
            else:
                route.continue_()

        page.route("**/api/**", route_api)
        page.goto(f"{args.url}/demo?run={args.run}&tab=genes", wait_until="networkidle")
        button = page.get_by_role("button", name="导出完整基因 CSV", exact=True)
        expect(button).to_be_enabled()
        with page.expect_download() as pending:
            button.click()
        target = out / pending.value.suggested_filename
        pending.value.save_as(target)
        csv = target.read_text(encoding="utf-8-sig")
        assert "ZERO,1,1,0" in csv and "population,units" in csv
        checks.append(
            "fixture: server complete CSV preserves zero change rows despite one loaded display row"
        )
        for kind in ("analysis", "single-cell", "network", "ranking"):
            page.get_by_label("导出结果包类型").select_option(kind)
            with page.expect_download() as pending:
                page.get_by_role("button", name="下载结果包", exact=True).click()
            target = out / pending.value.suggested_filename
            pending.value.save_as(target)
            with zipfile.ZipFile(target) as archive:
                assert archive.read("FIXTURE.txt").decode() == kind
        checks.append("fixture: four ZIP choices use package query and Content-Disposition filename")
        for export_mode, text in [("html", "下载文件类型"), ("error", "fixture export unavailable")]:
            count = len(downloads)
            mode["export"] = export_mode
            button.click()
            expect(page.get_by_role("alert")).to_contain_text(text)
            assert len(downloads) == count
        checks.append("fixture: HTML masquerading as CSV and HTTP detail errors do not download")
        mode["export"] = "ok"
        mode["genes"] = "zero"
        page.reload(wait_until="networkidle")
        expect(page.get_by_text("暂无可展示的基因响应", exact=True)).to_be_visible()
        expect(button).to_be_enabled()
        with page.expect_download() as pending:
            button.click()
        pending.value.save_as(out / "zero-display-full.csv")
        checks.append("fixture: complete export remains accessible when display has no nonzero rows")
        mode["hold"] = True
        page.get_by_role("button", name="下载结果包", exact=True).click()
        expect(page.get_by_role("button", name="下载中…", exact=True)).to_be_disabled()
        assert held
        count = len(downloads)
        page.get_by_role("tab", name="实测对比", exact=True).click()
        expect(page.get_by_role("button", name="下载结果包", exact=True)).to_be_disabled()
        try:
            held.pop().fulfill(content_type="application/zip", body=b"PK\x05\x06" + b"\0" * 18)
        except Exception:
            pass  # Aborted request can already have been discarded by Chromium.
        page.wait_for_timeout(250)
        assert len(downloads) == count
        checks.append("fixture: changing to comparison aborts pending original-population package download")
        page.screenshot(path=str(out / "download-controls.png"), full_page=True)
        assert not errors, errors
        browser.close()
    result = {"fixture_only": True, "checks": checks, "requests": requests, "page_errors": errors}
    (out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
