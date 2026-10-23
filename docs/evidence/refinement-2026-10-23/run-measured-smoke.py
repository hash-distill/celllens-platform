import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx


def main():
    output = Path(__file__).with_name('measured-smoke.json')
    report = {
        'started_at': datetime.now(UTC).isoformat(),
        'request': {'cell_line': 'K562', 'perturbation': 'ALDOA', 'max_cells': 16, 'seed': 20261023},
        'external_llm_called': False,
    }

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    with httpx.Client(base_url='http://127.0.0.1:8001/api/v1', timeout=30, trust_env=False) as client:
        source = client.get('/data-catalog/pair', params={'cell_line': 'K562', 'perturbation': 'ALDOA'})
        source.raise_for_status()
        if not source.json().get('local_verified'):
            raise RuntimeError('Smoke test requires already verified local measured data')
        created = client.post('/measured/analyses', json=report['request'])
        created.raise_for_status()
        identifier = created.json()['id']
        report['analysis_id'] = identifier
        save()
        print('Created measured smoke:', identifier, flush=True)
        deadline = time.monotonic() + 300
        previous = None
        while time.monotonic() < deadline:
            response = client.get(f'/measured/analyses/{identifier}')
            response.raise_for_status()
            record = response.json()
            report['status'] = record['status']
            save()
            current = (record['status'], record['progress'])
            if current != previous:
                print('Status:', *current, flush=True)
                previous = current
            if record['status'] == 'completed':
                report['counts'] = record['summary']['counts']
                report['gene_count'] = record['summary']['gene_count']
                report['checks'] = {}
                for kind in ('genes', 'tasks', 'reactions'):
                    response = client.get(f'/measured/analyses/{identifier}/table', params={'kind': kind})
                    response.raise_for_status()
                    report['checks'][kind] = response.json()['total']
                report['completed_at'] = datetime.now(UTC).isoformat()
                save()
                print(json.dumps(report, ensure_ascii=False), flush=True)
                return
            if record['status'] in ('failed', 'cancelled', 'interrupted'):
                report['error'] = record.get('error_message')
                save()
                raise RuntimeError('Measured smoke did not complete; see measured-smoke.json')
            time.sleep(2)
        report['status'] = 'still_running_at_check_deadline'
        save()
        raise RuntimeError('Smoke check timed out; the created analysis was not cancelled')


if __name__ == '__main__':
    main()
