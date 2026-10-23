import argparse
import io
import json
import zipfile
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8001')
    parser.add_argument('--require-latest', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--run-id', default='run_41504106326f404d')
    parser.add_argument('--measured-id', default='measured_a40955b0de73475a9d628e05')
    args = parser.parse_args()
    checks = []
    run_id = args.run_id
    measured_id = args.measured_id

    def check(name, passed, **details):
        checks.append({'name': name, 'passed': bool(passed), **details})

    with httpx.Client(base_url=args.url, timeout=120, trust_env=False) as client:
        def get(path, **params):
            response = client.get('/api/v1/' + path, params=params)
            response.raise_for_status()
            return response.json()

        for path in ('health', 'ready', 'system-status', 'catalog/contexts',
                     'catalog/data-summary', 'data-catalog', 'resources',
                     'experiments', 'assistant/capabilities', 'measured/analyses'):
            payload = get(path)
            check(path, payload.get('ready') is True if path == 'ready' else bool(payload))
            if path == 'assistant/capabilities':
                check('model default lengths active', payload.get('model_default_lengths') is True)

        response = client.post('/api/v1/assistant/test', json={
            'provider': 'custom', 'base_url': 'https://invalid.example', 'model': 'endpoint-rejection-check',
            'api_key': '', 'max_tokens': None, 'context_window': None,
        })
        detail = response.json().get('detail', {})
        check('nullable lengths accepted before endpoint rejection',
              response.status_code == 422 and isinstance(detail, dict) and detail.get('code') == 'ENDPOINT_REJECTED')

        measured = get(f'measured/analyses/{measured_id}')
        check('measured completed', measured['status'] == 'completed')
        for kind in ('genes', 'tasks', 'reactions'):
            payload = get(f'measured/analyses/{measured_id}/table', kind=kind)
            check('measured table ' + kind, bool(payload))
        for embedding in ('pca', 'umap'):
            payload = get(f'measured/analyses/{measured_id}/projection', embedding=embedding)
            check('measured projection ' + embedding, bool(payload))
        response = client.get(f'/api/v1/measured/analyses/{measured_id}/download', params={'kind': 'bundle'})
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            check('measured bundle CRC', archive.testzip() is None, entries=len(archive.namelist()))

        for resource in ('summary', 'genes', 'metabolic-tasks', 'completeness', 'provenance', 'projection'):
            payload = get(f'runs/{run_id}/{resource}')
            check('prediction ' + resource, bool(payload))
        comparison = get(f'runs/{run_id}/comparison')
        check('matched comparison available', comparison['status'] == 'available')
        measured_context = get('assistant/context', source_kind='measured', source_id=measured_id)
        check('measured context has no prediction', 'predicted' not in json.dumps(measured_context['data']))
        context = get('assistant/context', source_kind='run', source_id=run_id, view='comparison')
        latest = (
            'comparison_manifest.json' in context['artifact_sha256']
            and context['selection']['view'] == 'comparison'
        )
        check('latest matched AI context active', latest, restart_required=not latest)

    report = {'url': args.url, 'run_id': run_id, 'measured_id': measured_id,
              'read_only': True, 'external_llm_called': False, 'checks': checks}
    output = args.output or Path(__file__).with_name('live-system-recheck.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for row in checks:
        print(('PASS' if row['passed'] else 'FAIL') + ': ' + row['name'])
    failures = [row for row in checks if not row['passed']]
    if args.require_latest or any(row['name'] != 'latest matched AI context active' for row in failures):
        raise SystemExit(bool(failures))


if __name__ == '__main__':
    main()
