import json
import sys
import time
from types import SimpleNamespace

from backend.app.api.coverage import get_coverage
from backend.app.config import Settings
from backend.app.core.registry import AssetRegistry

settings = Settings()
container = SimpleNamespace(
    settings=settings,
    registry=AssetRegistry(settings.project_root, settings.registry_root),
)
request = SimpleNamespace(query_params={}, app=SimpleNamespace(state=SimpleNamespace(container=container)))
started = time.perf_counter()
response = get_coverage(request, cell_line=None, run_id=None)
payload = json.loads(bytes(response.body))
print(json.dumps({
    'seconds': round(time.perf_counter() - started, 4),
    'bytes': len(response.body),
    'loaded_scoring_package': 'sccellfie' in sys.modules,
    'panel_genes': payload['panel_gene_count'],
    'tasks': len(payload['tasks']),
    'fully_covered_tasks': sum(row['coverage_status'] == 'full' for row in payload['tasks']),
    'run_created': False,
}))
