"""Check live four-context selection and saved real predictions in the browser."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--runs", type=Path)
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[1] / "reports/frontend/contexts"
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url + "/workbench", wait_until="networkidle")
        for cell_line in ["K562", "RPE1", "Jurkat", "HepG2"]:
            radio = page.locator(f'input[name="cell-line"][value="{cell_line}"]')
            expect(radio).to_have_count(1)
            expect(radio).to_be_enabled()
            page.locator("label.choice").filter(has=radio).click()
            expect(radio).to_be_checked()
            response = page.request.get(
                args.url + f"/api/v1/catalog/perturbations?cell_line={cell_line}&mode=online"
            )
            assert response.ok
            assert "AAMP" in response.json()["items"]
            checks.append(f"{cell_line}: enabled selection and matching perturbation catalog")
        page.screenshot(path=str(output / "four-contexts.png"), full_page=True)
        if args.runs:
            runs = json.loads(args.runs.read_text(encoding="utf-8"))["runs"]
            for run in runs:
                line, run_id = run["cell_line"], run["run_id"]
                page.goto(args.url + "/workbench?run=" + run_id, wait_until="networkidle")
                expect(page.locator(".active-experiment")).to_contain_text(line)
                expect(page.locator(".run-identity")).to_have_text(run_id)
                expect(page.locator(".gene-row").first).to_be_visible()
                expect(page.locator(".task-row").first).to_be_visible()
                expect(page.locator(".state-population")).to_have_count(2)
                expect(page.locator(".trace-provenance")).to_contain_text("scCellFie")
                page.screenshot(path=str(output / f"{line}-real.png"), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                page.wait_for_function("document.documentElement.scrollWidth <= window.innerWidth")
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.screenshot(path=str(output / f"{line}-mobile.png"), full_page=True)
                page.set_viewport_size({"width": 1440, "height": 1000})
                checks.append(f"{line}: real result, genes, tasks, projection, provenance and mobile fit")
        page.goto(args.url + "/", wait_until="networkidle")
        for cell_line in ["K562", "RPE1", "Jurkat", "HepG2"]:
            expect(page.locator(".hero-context")).to_contain_text(cell_line)
        checks.append("homepage availability follows all live ready contexts")
        assert not errors, errors
        browser.close()
    (output / "checks.json").write_text(
        json.dumps({"checks": checks, "page_errors": errors}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"checks": checks, "page_errors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
