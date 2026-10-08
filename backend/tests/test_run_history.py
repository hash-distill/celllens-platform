import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.schemas import CreateRunRequest, RunStatus
from backend.tests.test_api_runs import _settings, _write_registry


@pytest.fixture
def history_client(tmp_path):
    _write_registry(tmp_path)
    app = create_app(_settings(tmp_path, worker_enabled=False))
    store = app.state.container.store
    for run_id, gene, mode, status in [
        ("run_old", "MYC", "online", "completed"),
        ("run_failed", "AAMP", "precomputed", "failed"),
        ("run_running", "MYC", "online", "state_running"),
        ("run_new", "TP53", "precomputed", "queued"),
    ]:
        store.create(run_id, CreateRunRequest(cell_line="K562", perturbation=gene, mode=mode))
        if status != "queued":
            store.transition(run_id, RunStatus(status), 100 if status == "completed" else 15)
    with TestClient(app) as client:
        yield client
    store.engine.dispose()


def test_history_is_paged_from_server_and_sorted_newest_first(history_client):
    first = history_client.get("/api/v1/runs?limit=2").json()
    second = history_client.get("/api/v1/runs?limit=2&offset=2").json()
    assert first["total"] == second["total"] == 4
    assert [row["run_id"] for row in first["items"]] == ["run_new", "run_running"]
    assert [row["run_id"] for row in second["items"]] == ["run_failed", "run_old"]
    assert first["items"][0]["request"]["perturbation"] == "TP53"
    assert first["items"][0]["created_at"]
    assert history_client.get("/api/v1/runs?offset=100").json()["items"] == []


def test_history_search_and_filters_have_consistent_totals(history_client):
    response = history_client.get("/api/v1/runs?q=myc&status=active&mode=online").json()
    assert response["total"] == 1
    assert response["items"][0]["run_id"] == "run_running"
    assert history_client.get("/api/v1/runs?status=active").json()["total"] == 2
    assert history_client.get("/api/v1/runs?status=failed").json()["items"][0]["run_id"] == "run_failed"
    assert history_client.get("/api/v1/runs?q=K562").json()["total"] == 4
    assert history_client.get("/api/v1/runs?q=run_old").json()["total"] == 1
    assert history_client.get("/api/v1/runs?q=%25").json()["total"] == 0


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "status=invalid", "mode=invalid"])
def test_history_rejects_invalid_queries(history_client, query):
    assert history_client.get("/api/v1/runs?" + query).status_code == 422
