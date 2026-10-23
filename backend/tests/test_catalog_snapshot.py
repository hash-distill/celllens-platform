import json

import pytest
from fastapi.responses import JSONResponse

from backend.app.services.catalog_snapshot import model_catalog_response


def test_snapshot_survives_repeated_reads_and_invalidates_on_inputs(tmp_path):
    registry = tmp_path / 'data/registry'
    registry.mkdir(parents=True)
    panel = registry / 'panel.txt'
    panel.write_text('A')
    calls = []

    def build():
        calls.append(True)
        return JSONResponse({'panel': panel.read_text()})

    first = model_catalog_response(tmp_path, None, [], build)
    assert model_catalog_response(tmp_path, None, [], build).body == first.body
    assert len(calls) == 1
    panel.write_text('B')
    assert json.loads(model_catalog_response(tmp_path, None, [], build).body)['panel'] == 'B'
    assert len(calls) == 2
    model_catalog_response(tmp_path, 'K562', [], build)
    model_catalog_response(tmp_path, None, [{'id': 'changed'}], build)
    assert len(calls) == 4


def test_tampered_snapshot_never_returns_changed_payload(tmp_path):
    def build():
        return JSONResponse({'verified': True})

    model_catalog_response(tmp_path, None, [], build)
    path = next((tmp_path / 'data/derived/catalog-cache').glob('*.json'))
    document = json.loads(path.read_text())
    document['body'] = {'verified': False}
    path.write_text(json.dumps(document))
    result = model_catalog_response(tmp_path, None, [], build)
    assert json.loads(result.body) == {'verified': True}


def test_changed_inputs_do_not_fall_back_to_previous_snapshot(tmp_path):
    model_catalog_response(tmp_path, None, [], lambda: JSONResponse({'verified': True}))

    def unavailable():
        raise ValueError('source verification failed')

    with pytest.raises(ValueError, match='verification failed'):
        model_catalog_response(tmp_path, None, [{'id': 'changed'}], unavailable)


def test_panel_outside_registry_and_resources_invalidate_snapshot(tmp_path):
    panel = tmp_path / 'model-panel.txt'
    panel.write_text('A')
    models = [{'id': 'model', 'enabled': True, 'gene_list_path': panel.name}]
    calls = []

    def build():
        calls.append(True)
        return JSONResponse({'calls': len(calls)})

    model_catalog_response(tmp_path, None, models, build)
    panel.write_text('B')
    model_catalog_response(tmp_path, None, models, build)
    resources = tmp_path / 'backend/app/resources'
    resources.mkdir(parents=True)
    (resources / 'biology_zh.json').write_text('{}')
    model_catalog_response(tmp_path, None, models, build)
    assert len(calls) == 3


def test_snapshot_write_failure_still_returns_verified_live_result(tmp_path, monkeypatch):
    def unavailable(*args):
        raise OSError('read only')

    monkeypatch.setattr('backend.app.services.catalog_snapshot.atomic_write_json', unavailable)
    result = model_catalog_response(tmp_path, None, [], lambda: JSONResponse({'verified': True}))
    assert json.loads(result.body)['verified'] is True
