"""Browser regression checks. Start the Vite dev server before running this script."""

import argparse
import json
import sys

from playwright.sync_api import expect, sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    args = parser.parse_args()
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_init_script("""if (!localStorage.getItem('celllens.testInitialized')) {
            localStorage.setItem('celllens.mockMode.v1', 'on');
            localStorage.setItem('celllens.testInitialized', 'yes');
        }""")
        page = context.new_page()
        page.goto(args.url + "/workbench", wait_until="networkidle")

        def check(name, action):
            try:
                action()
                result = {"check": name, "passed": True}
            except Exception as exc:
                result = {"check": name, "passed": False, "error": str(exc)}
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)

        def response_lifecycle(kind):
            actual = page.evaluate(
                """async (kind) => {
                const {apiFetchRaw} = await import('/src/api/http.ts');
                const original = window.fetch;
                const external = new AbortController();
                window.fetch = async (_url, options) => new Response(new ReadableStream({
                    start(stream) {
                        const timer = setTimeout(() => {
                            if (kind === 'network') stream.error(new Error('disconnected'));
                            else {stream.enqueue(new TextEncoder().encode('{}')); stream.close();}
                        }, 150);
                        options.signal.addEventListener('abort', () => {
                            clearTimeout(timer);
                            stream.error(new DOMException('aborted', 'AbortError'));
                        }, {once:true});
                    }
                }));
                if (kind === 'abort') setTimeout(() => external.abort(), 20);
                try {
                    await apiFetchRaw('/fixture', {
                        timeoutMs:kind==='timeout'?20:1000, signal:external.signal
                    });
                    return 'success';
                } catch(error) {return error.kind ?? error.name;}
                finally {window.fetch = original;}
            }""",
                kind,
            )
            assert actual == kind, f"expected {kind}, received {actual}"

        for kind in ("timeout", "abort", "network"):
            check("response body " + kind, lambda kind=kind: response_lifecycle(kind))

        def advanced_parameters():
            assert (
                page.evaluate("""async () => {
                const {isIntegerInRange}=await import('/src/utils/number.ts');
                return isIntegerInRange(64,64,4096);
            }""")
                is True
            )
            expect(page.locator("#n-cells-input")).to_be_editable()
            page.locator("#n-cells-input").fill("64")
            page.locator("#seed-input").fill("42", timeout=3000)
            page.locator("#perturbation-input").fill("MYC")
            page.locator("#perturbation-input").press("Enter")
            expect(page.get_by_role("button", name="开始实验", exact=True)).to_be_enabled(timeout=3000)
            page.locator("#n-cells-input").fill("63")
            expect(page.get_by_role("button", name="开始实验", exact=True)).to_be_disabled(timeout=3000)
            page.locator("#n-cells-input").fill("64")

        check("numeric input stays rendered and validates bounds", advanced_parameters)

        def poll_serialization():
            result = page.evaluate("""async () => {
                const {api} = await import('/src/api/client.ts');
                const {useRunStore} = await import('/src/stores/run.ts');
                const store = useRunStore();
                const original = api.getRun;
                let active=0, maximum=0;
                api.getRun = async (id) => {
                    active++; maximum=Math.max(maximum,active);
                    await new Promise(resolve=>setTimeout(resolve,100)); active--;
                    return {run_id:id,status:'queued',stage_progress:0,request:{},warnings:[]};
                };
                try {
                    store.openRun('fixture-poll'); store.wakePolling(); store.wakePolling();
                    await new Promise(resolve=>setTimeout(resolve,150));
                    return maximum;
                } finally {store.leaveRun(); api.getRun=original;}
            }""")
            assert result == 1, f"concurrent polls: {result}"

        check("visibility wake keeps polling serial", poll_serialization)

        def mock_source():
            page.evaluate("""async () => {
                const mock = await import('/src/fixtures/mockApi.ts');
                const {useCandidatesStore} = await import('/src/stores/candidates.ts');
                const request={cell_line:'K562',perturbation:'MYC',mode:'online',n_cells:64,seed:42};
                const run=await mock.createRun(request);
                for(let i=0;i<8;i++) await mock.getRun(run.run_id);
                useCandidatesStore().clear(); useCandidatesStore().add(run.run_id, request);
            }""")
            page.locator(".app-header nav").get_by_role("link", name="实验比较").click()
            page.get_by_text("已加载", exact=True).wait_for()
            row = page.get_by_role("row").filter(has=page.get_by_role("rowheader", name="来源", exact=True))
            text = row.inner_text()
            assert "合成数据" in text and "真实计算" not in text, text

        check("Mock source is explicit in comparison", mock_source)

        def mock_refresh():
            page.reload(wait_until="networkidle")
            page.get_by_text("已加载", exact=True).wait_for(timeout=3000)
            assert "运行不存在" not in page.locator("body").inner_text()

        check("Mock comparison survives reload", mock_refresh)

        def gene_pagination():
            run_id = page.evaluate("""async () => {
                const {useCandidatesStore}=await import('/src/stores/candidates.ts');
                return useCandidatesStore().items[0].run_id;
            }""")
            page.goto(args.url + f"/runs/{run_id}?tab=genes", wait_until="networkidle")
            page.locator("#gene-search").wait_for()
            rows = page.locator("table tbody tr")
            assert rows.count() <= 50, f"rendered {rows.count()} rows in one page"
            first_gene = rows.first.inner_text()
            page.get_by_role("button", name="下一页", exact=True).click()
            assert rows.first.inner_text() != first_gene
            page.locator("#gene-search").fill("MYC")
            assert rows.count() == 1

        check("gene table paginates and search resets page", gene_pagination)

        def source_isolation():
            page.evaluate("localStorage.removeItem('celllens.mockMode.v1')")
            page.goto(args.url + "/compare", wait_until="networkidle")
            assert "尚未选择比较实验" in page.locator("body").inner_text()

        check("Mock candidates isolated from real API", source_isolation)
        browser.close()
    return 0 if all(item["passed"] for item in results) else 1


if __name__ == "__main__":
    sys.exit(main())
