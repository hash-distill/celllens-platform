import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
audit = json.loads((ROOT / 'docs/evidence/reviewer-audit-2026-10-22/audit.json').read_text(encoding='utf-8'))
checks = []
for section, folder, identifier, key in [
    ('comparisons', 'comparisons', 'run_id', 'outputs'),
    ('measured_analyses', 'measured', 'analysis_id', 'files'),
]:
    for record in audit[section]:
        if not record.get('output_hash_checks'):
            continue
        directory = ROOT / 'data/derived' / folder / record[identifier]
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        for name, declared in manifest[key].items():
            expected = declared['sha256'] if isinstance(declared, dict) else declared
            with (directory / name).open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            checks.append({'record': record[identifier], 'file': name, 'matches': actual == expected})
result = {'files_checked': len(checks), 'mismatches': sum(not row['matches'] for row in checks), 'checks': checks}
Path(__file__).with_name('preserved-results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f"Saved scientific outputs: {result['files_checked']} checked; {result['mismatches']} mismatches")
assert result['mismatches'] == 0
