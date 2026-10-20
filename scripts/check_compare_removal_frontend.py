"""Browser acceptance for removable, persisted experiment comparison selections."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[1] / 'reports/compare-removal-2026-10-10'
    output.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    ids = ['run_c76a0442621c4e0d', 'run_2d7de9d129904b63', 'run_2151b0c415484f8e']
    replacement = 'run_4a24afcd5b084acf'
    key = 'celllens.candidates.v1.api'
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        records = []
        for run in ids + [replacement]:
            response = context.request.get(f'{args.url}/api/v1/runs/{run}')
            assert response.ok, f'{run}: {response.status}'
            records.append(response.json())
        seed = [
            {'run_id': r['run_id'], 'request': r['request'], 'added_at': '2026-10-10T00:00:00Z'}
            for r in records[:3]
        ]
        context.add_init_script('''(() => {
          if (!localStorage.getItem('compare-acceptance-initialized')) {
            localStorage.setItem('compare-acceptance-initialized', 'yes');
            localStorage.setItem('celllens.mockMode.v1', 'off');
            localStorage.setItem('celllens.candidates.v1.api', JSON.stringify(SEED));
            localStorage.setItem('celllens.candidates.v1', JSON.stringify(SEED));
            localStorage.setItem('celllens.candidates.v1.mock', '[]');
          }
        })();'''.replace('SEED', json.dumps(seed)))
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))

        def stored():
            return page.evaluate('(key) => JSON.parse(localStorage.getItem(key))', key)

        def count(value):
            expect(page.locator('[data-remove-run]')).to_have_count(value)
            badge = page.locator('a[href="/compare"] .nav-count')
            if value:
                expect(badge).to_have_text(str(value))
            else:
                expect(badge).to_have_count(0)

        page.goto(args.url + '/compare', wait_until='networkidle')
        expect(page.get_by_role('heading', name='实验比较', exact=True)).to_be_visible()
        count(3)
        expect(page.get_by_text('已加载', exact=True)).to_have_count(3)
        checks.append('three saved candidates load with visible removal controls')
        page.screenshot(path=str(output / 'comparison-three.png'), full_page=True)
        page.locator(f'[data-remove-run="{ids[0]}"]').click()
        count(2)
        assert [item['run_id'] for item in stored()] == ids[1:]
        assert context.request.get(f'{args.url}/api/v1/runs/{ids[0]}').ok
        checks.append('removal updates columns, header count and storage; experiment still exists')
        page.reload(wait_until='networkidle')
        count(2)
        checks.append('refresh retains removal despite a legacy three-candidate storage entry')
        page.screenshot(path=str(output / 'comparison-two.png'), full_page=True)

        page.goto(f'{args.url}/records?q={ids[0]}', wait_until='networkidle')
        row = page.locator(f'[data-run-id="{ids[0]}"]')
        expect(row).to_be_visible()
        expect(row.get_by_role('button', name='加入比较', exact=True)).to_be_enabled()
        row.get_by_role('button', name='加入比较', exact=True).click()
        expect(row.get_by_role('button', name='已选比较', exact=True)).to_be_disabled()
        page.get_by_role('link', name='实验比较').click()
        count(3)
        expect(page.get_by_text('已加载', exact=True)).to_have_count(3)
        checks.append('removed experiment can be selected again from real records')

        page.get_by_role('button', name='清空比较', exact=True).click()
        count(0)
        expect(page.get_by_text('尚未选择比较实验', exact=True)).to_be_visible()
        assert stored() == []
        page.reload(wait_until='networkidle')
        count(0)
        assert page.evaluate("localStorage.getItem('celllens.candidates.v1.mock')") == '[]'
        checks.append('clear persists empty selection after refresh and does not change mock selections')
        page.screenshot(path=str(output / 'comparison-empty.png'), full_page=True)
        page.get_by_role('button', name='去实验记录选择', exact=True).click()
        expect(page.get_by_role('heading', name='实验记录', exact=True)).to_be_visible()
        page.goto(f'{args.url}/records?q={replacement}', wait_until='networkidle')
        page.locator(f'[data-run-id="{replacement}"]').get_by_role(
            'button', name='加入比较', exact=True
        ).click()
        page.get_by_role('link', name='实验比较').click()
        count(1)
        expect(page.get_by_text('已加载', exact=True)).to_have_count(1)
        assert stored()[0]['run_id'] == replacement
        checks.append('empty selection navigates to records and accepts a different experiment')
        page.set_viewport_size({'width': 1920, 'height': 1000})
        expect(page.get_by_role('button', name='清空比较', exact=True)).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        page.screenshot(path=str(output / 'comparison-desktop.png'), full_page=True)
        checks.append('1920 px desktop viewport keeps comparison actions accessible without page overflow')

        # Delay the real API calls in a separate context, then remove during loading.
        delayed = browser.new_context(viewport={'width': 1440, 'height': 900})
        delayed.add_init_script('''(() => {
          localStorage.setItem('celllens.mockMode.v1', 'off');
          localStorage.setItem('celllens.candidates.v1.api', JSON.stringify(SEED));
          const realFetch = window.fetch.bind(window);
          window.fetch = async (...args) => {
            if (String(args[0]).includes('/api/v1/runs/'))
              await new Promise(resolve => setTimeout(resolve, 1200));
            return realFetch(...args);
          };
        })();'''.replace('SEED', json.dumps(seed)))
        race = delayed.new_page()
        race.on('pageerror', lambda error: errors.append(str(error)))
        race.goto(args.url + '/compare', wait_until='domcontentloaded')
        expect(race.locator('[data-remove-run]')).to_have_count(3)
        expect(race.get_by_text('加载中…', exact=True)).to_have_count(3)
        race.locator(f'[data-remove-run="{ids[0]}"]').click()
        race.get_by_role('button', name='清空比较', exact=True).click()
        race.wait_for_timeout(1600)
        expect(race.locator('[data-remove-run]')).to_have_count(0)
        assert race.evaluate('(key) => JSON.parse(localStorage.getItem(key))', key) == []
        checks.append('removal and clear during delayed loading do not restore old data or crash')
        assert not errors, errors
        checks.append('no browser JavaScript errors')
        browser.close()
    result = {'passed': True, 'checks': checks, 'page_errors': errors}
    (output / 'acceptance.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
