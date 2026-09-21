from datetime import UTC, datetime, timedelta

import pytest

from backend.app.core.errors import InvalidTransitionError
from backend.app.core.storage import RunStore
from backend.app.schemas import CreateRunRequest, RunStatus


def make_store(tmp_path):
    return RunStore(f"sqlite+pysqlite:///{(tmp_path / 'test.db').as_posix()}", create_schema=True)


def test_terminal_run_cannot_transition_backwards(tmp_path):
    store = make_store(tmp_path)
    store.create("run_1", CreateRunRequest(cell_line="K562", perturbation="MYC"))
    store.transition("run_1", RunStatus.STATE_RUNNING, 15)
    store.transition("run_1", RunStatus.ADAPTING, 45)
    store.transition("run_1", RunStatus.METABOLIC_RUNNING, 65)
    store.transition("run_1", RunStatus.VALIDATING, 85)
    store.transition("run_1", RunStatus.COMPLETED, 100)
    with pytest.raises(InvalidTransitionError):
        store.transition("run_1", RunStatus.QUEUED, 0)


def test_store_records_events_attempts_artifacts_and_cache(tmp_path):
    store = make_store(tmp_path)
    request = CreateRunRequest(cell_line="K562", perturbation="MYC")
    store.create("run_1", request, cache_key="cache-1")
    attempt = store.start_attempt("run_1", worker_id="worker-1", lease_seconds=60)
    assert attempt.attempt_no == 1
    store.transition("run_1", RunStatus.STATE_RUNNING, 15)
    store.register_artifact("run_1", "summary", "run_1/summary.json", "a" * 64, 123, "application/json")
    store.finish_attempt(attempt.id, succeeded=False, error_code="EXPECTED")
    assert store.events("run_1")[-1].to_status == RunStatus.STATE_RUNNING.value
    assert store.artifacts("run_1")[0].kind == "summary"
    assert store.get_cached_run("cache-1") is None
    assert store.cache_key("run_1") == "cache-1"


def test_recoverable_runs_include_queued_and_expired_running_attempts(tmp_path):
    store = make_store(tmp_path)
    request = CreateRunRequest(cell_line="K562", perturbation="MYC")
    store.create("queued", request)
    store.create("expired", request)
    attempt = store.start_attempt("expired", worker_id="dead-worker", lease_seconds=60)
    store.transition("expired", RunStatus.STATE_RUNNING, 15)
    store.force_attempt_lease(attempt.id, datetime.now(UTC) - timedelta(seconds=1))
    assert set(store.list_recoverable_run_ids()) == {"queued", "expired"}
