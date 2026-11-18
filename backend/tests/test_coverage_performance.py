import builtins
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from backend.app.services import catalog_snapshot, coverage_catalog
from backend.tests.test_coverage_catalog import coverage_app as coverage_app


def test_snapshot_memory_hit_rechecks_inputs_and_snapshot_bytes(tmp_path):
    registry = tmp_path / "data/registry"
    registry.mkdir(parents=True)
    panel = registry / "panel.txt"
    panel.write_text("A")
    calls = []

    def build():
        calls.append(True)
        return JSONResponse({"panel": panel.read_text()})

    first = catalog_snapshot.model_catalog_response(tmp_path, None, [], build)
    # The first persisted read validates and memoizes the serialized response.
    assert catalog_snapshot.model_catalog_response(tmp_path, None, [], build).body == first.body
    assert catalog_snapshot.model_catalog_response(tmp_path, None, [], build).body == first.body
    assert len(calls) == 1
    path = next((tmp_path / "data/derived/catalog-cache").glob("*.json"))
    snapshot = json.loads(path.read_bytes())
    snapshot["body"]["panel"] = "TAMPERED"
    path.write_text(json.dumps(snapshot))
    assert json.loads(catalog_snapshot.model_catalog_response(tmp_path, None, [], build).body) == {
        "panel": "A"
    }
    assert len(calls) == 2
    panel.write_text("B")
    assert json.loads(catalog_snapshot.model_catalog_response(tmp_path, None, [], build).body) == {
        "panel": "B"
    }
    assert len(calls) == 3


def test_persisted_snapshot_hit_requires_no_scientific_import_or_build(tmp_path, monkeypatch):
    first = catalog_snapshot.model_catalog_response(
        tmp_path, None, [], lambda: JSONResponse({"verified": True})
    )
    catalog_snapshot._encoded_snapshots.clear()
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in {"sccellfie", "anndata"}:
            raise AssertionError("Scientific package imported on snapshot hit")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    def unavailable():
        raise AssertionError("Snapshot hit attempted a scientific rebuild")

    result = catalog_snapshot.model_catalog_response(tmp_path, None, [], unavailable)
    assert result.body == first.body
    assert result.headers["cache-control"] == "no-store"


def test_concurrent_snapshot_misses_build_once(tmp_path):
    barrier = Barrier(4)
    calls = []

    def build():
        calls.append(True)
        return JSONResponse({"verified": True})

    def read():
        barrier.wait(timeout=5)
        return catalog_snapshot.model_catalog_response(tmp_path, None, [], build).body

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: read(), range(4)))
    assert len(set(results)) == 1
    assert len(calls) == 1


def test_input_change_during_snapshot_build_is_rejected(tmp_path):
    registry = tmp_path / "data/registry"
    registry.mkdir(parents=True)
    panel = registry / "panel.txt"
    panel.write_text("A")
    entered = Event()
    changed = Event()

    def build():
        entered.set()
        assert changed.wait(timeout=5)
        return JSONResponse({"panel": "A"})

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(catalog_snapshot.model_catalog_response, tmp_path, None, [], build)
        assert entered.wait(timeout=5)
        panel.write_text("B")
        changed.set()
        with pytest.raises(ValueError, match="changed while building"):
            future.result(timeout=5)
    assert not list((tmp_path / "data/derived/catalog-cache").glob("*.json"))


def test_broad_backend_code_changes_still_invalidate_snapshot(tmp_path):
    code = tmp_path / "backend/app/assistant.py"
    code.parent.mkdir(parents=True)
    code.write_text("# previous")
    calls = []

    def build():
        calls.append(True)
        return JSONResponse({"calls": len(calls)})

    catalog_snapshot.model_catalog_response(tmp_path, None, [], build)
    catalog_snapshot.model_catalog_response(tmp_path, None, [], build)
    code.write_text("# updated")
    assert json.loads(catalog_snapshot.model_catalog_response(tmp_path, None, [], build).body)["calls"] == 2


def test_model_catalogue_loads_database_only_once(request, monkeypatch):
    app, _, database = request.getfixturevalue("coverage_app")
    loads = []

    def loader(*_):
        loads.append(True)
        return database, "fixture-v1"

    monkeypatch.setattr("backend.app.api.coverage._load_frozen_database", loader)
    monkeypatch.setattr("backend.app.services.scientific_analysis._load_frozen_database", loader)
    with TestClient(app) as client:
        assert client.get("/api/v1/coverage").status_code == 200
    assert len(loads) == 1


def test_verified_completeness_deduplicates_concurrency_but_not_changed_evidence(tmp_path, monkeypatch):
    calls = []
    database = {"_celllens_provenance": {"manifest_sha256": "a" * 64}}

    def compute(genes, _database, version):
        calls.append((genes, version))
        return {"panel": genes, "version": version}

    monkeypatch.setattr(coverage_catalog, "compute_official_completeness", compute)
    barrier = Barrier(4)

    def read():
        barrier.wait(timeout=5)
        return coverage_catalog.completeness_from_verified_database(["A"], database, "v1", str(tmp_path))

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: read(), range(4)))
    assert all(result == results[0] for result in results)
    assert len(calls) == 1
    database["_celllens_provenance"]["manifest_sha256"] = "b" * 64
    coverage_catalog.completeness_from_verified_database(["A"], database, "v1", str(tmp_path))
    coverage_catalog.completeness_from_verified_database(["B"], database, "v1", str(tmp_path))
    coverage_catalog.completeness_from_verified_database(["B"], database, "v2", str(tmp_path))
    assert len(calls) == 4
