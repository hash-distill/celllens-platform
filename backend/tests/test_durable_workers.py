import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from backend.app.config import Settings
from backend.app.core.errors import JobAlreadyClaimedError
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.core.storage import RunStore
from backend.app.db.models import MeasuredAnalysisModel, WorkerHeartbeatModel
from backend.app.main import create_app
from backend.app.schemas import CreateRunRequest, RunStatus
from backend.app.services.measured_jobs import MeasuredJobs
from backend.app.services.measured_store import MeasuredStore
from backend.app.services.worker_status import heartbeat


def settings(root, **kwargs):
    registry = root / "data/registry"
    registry.mkdir(parents=True, exist_ok=True)
    for name in ("models", "datasets"):
        (registry / f"{name}.json").write_text(json.dumps({name: []}))
    return Settings(
        _env_file=None,
        project_root=root,
        database_url=f"sqlite+pysqlite:///{(root / 'worker.db').as_posix()}",
        create_database_schema=True,
        **kwargs,
    )


def request(identifier="measured_" + "a" * 24):
    return {"id": identifier, "cell_line": "K562", "perturbation": "MYC", "max_cells": 64, "seed": 42}


def expire(store, identifier):
    with store.sessions.begin() as session:
        session.execute(
            update(MeasuredAnalysisModel)
            .where(MeasuredAnalysisModel.id == identifier)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )


def test_cpu_claim_is_atomic_across_separate_connections(tmp_path):
    config = settings(tmp_path)
    stores = [
        MeasuredStore(RunStore(config.database_url, create_schema=True).session_factory) for _ in range(2)
    ]
    stores[0].create(request())
    gate = Barrier(2)

    def claim(index):
        gate.wait()
        return stores[index].claim(f"worker-{index}", 60)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, range(2)))
    assert sum(value is not None for value in results) == 1
    assert len(stores[0].attempts(request()["id"])) == 1


def test_expired_attempt_cannot_heartbeat_update_or_publish(tmp_path):
    app = create_app(settings(tmp_path))
    store = app.state.measured.store
    store.create(request())
    old = store.claim("dead", 60)
    expire(store, old["id"])
    assert store.recover_expired() == 1
    successor = store.claim("new", 60)
    called = []
    assert not store.heartbeat(old["id"], old["token"], 60)
    assert not store.owned_update(old["id"], old["token"], progress=99)
    assert not store.finish(old["id"], old["token"], "completed", publish=lambda: called.append(True))
    assert not called
    assert successor["attempt_no"] == 2
    assert [a["status"] for a in store.attempts(old["id"])] == ["abandoned", "running"]


def test_api_restart_does_not_interrupt_external_measured_owner(tmp_path):
    config = settings(tmp_path)
    app = create_app(config)
    app.state.measured.store.create(request())
    claim = app.state.measured.store.claim("separate-worker", 60)
    with TestClient(create_app(config)) as client:
        assert client.get(f"/api/v1/measured/analyses/{claim['id']}").json()["status"] == "preparing"
    assert app.state.measured.store.heartbeat(claim["id"], claim["token"], 60)


def test_queued_and_remote_running_cancellation(tmp_path):
    app = create_app(settings(tmp_path))
    store = app.state.measured.store
    first = request()
    second = request("measured_" + "b" * 24)
    store.create(first)
    assert store.cancel(first["id"])["status"] == "cancelled"
    assert store.claim("worker", 60) is None
    store.create(second)
    claim = store.claim("separate-worker", 60)
    with TestClient(app) as client:
        response = client.post(f"/api/v1/measured/analyses/{second['id']}/cancel")
        assert response.status_code == 200
        assert response.json()["cancel_requested"]
    assert not store.heartbeat(second["id"], claim["token"], 60)
    assert store.finish(second["id"], claim["token"], "cancelled", message="cancelled")
    assert store.get(second["id"])[0]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_worker_adopts_verified_atomic_publication_after_crash(tmp_path):
    app = create_app(settings(tmp_path))
    store = app.state.measured.store
    job = request()
    store.create(job)
    claim = store.claim("crashed", 60)
    final = tmp_path / "data/derived/measured" / job["id"]
    final.mkdir(parents=True)
    atomic_write_json(final / "summary.json", {"source_kind": "measured"})
    atomic_write_json(
        final / "manifest.json",
        {
            "id": job["id"],
            "source_kind": "measured",
            "request": job,
            "files": {"summary.json": file_sha256(final / "summary.json")},
            "inputs": {"groups": {}},
        },
    )
    digest = file_sha256(final / "manifest.json")
    expire(store, claim["id"])
    assert await app.state.measured.run_once()
    assert store.get(job["id"])[0]["status"] == "completed"
    assert file_sha256(final / "manifest.json") == digest
    assert [a["status"] for a in store.attempts(job["id"])] == ["abandoned", "completed"]


def test_prediction_claim_race_and_stale_heartbeat(tmp_path):
    config = settings(tmp_path)
    stores = [RunStore(config.database_url, create_schema=True) for _ in range(2)]
    stores[0].create("run_race", CreateRunRequest(cell_line="K562", perturbation="MYC"))
    gate = Barrier(2)

    def claim(index):
        gate.wait()
        try:
            return stores[index].start_attempt("run_race", worker_id=str(index), lease_seconds=60)
        except JobAlreadyClaimedError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, range(2)))
    attempt = next(value for value in claims if value)
    assert sum(value is not None for value in claims) == 1
    stores[0].force_attempt_lease(attempt.id, datetime.now(UTC) - timedelta(seconds=1))
    stores[0].prepare_recovery("run_race")
    with pytest.raises(JobAlreadyClaimedError):
        stores[0].heartbeat(attempt.id, 60)


def test_prediction_stale_owner_cannot_publish(tmp_path):
    store = RunStore(settings(tmp_path).database_url, create_schema=True)
    store.create("run_1", CreateRunRequest(cell_line="K562", perturbation="MYC"))
    attempt = store.start_attempt("run_1", worker_id="old", lease_seconds=60)
    store.force_attempt_lease(attempt.id, datetime.now(UTC) - timedelta(seconds=1))
    partial, final = tmp_path / "partial", tmp_path / "final"
    partial.mkdir()
    with pytest.raises(JobAlreadyClaimedError):
        store.transition("run_1", RunStatus.STATE_RUNNING, 15)
    with pytest.raises(JobAlreadyClaimedError):
        store.publish_attempt("run_1", partial, final)
    assert partial.exists() and not final.exists()


def test_private_auth_session_and_cpu_readiness(tmp_path):
    app = create_app(
        settings(
            tmp_path,
            deployment_mode="private",
            workspace_token="test-token",
            session_secure_cookie=False,
            gpu_available=True,
        )
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/measured/analyses").status_code == 401
        assert client.post("/api/v1/auth/session", json={"token": "wrong"}).status_code == 401
        response = client.post("/api/v1/auth/session", json={"token": "test-token"})
        assert response.status_code == 200 and "HttpOnly" in response.headers["set-cookie"]
        assert client.get("/api/v1/measured/analyses").status_code == 200
        ready = client.get("/api/v1/ready")
        assert ready.status_code == 200
        assert ready.json()["capabilities"] == {
            "result_browsing": True,
            "cpu_analysis": False,
            "prediction": False,
        }
        heartbeat(app.state.container.store, "cpu-probe", "cpu", {"cpu_analysis": True, "prediction": False})
        assert client.get("/api/v1/ready").json()["capabilities"]["cpu_analysis"]
        assert (
            client.post(
                "/api/v1/measured/analyses", json={}, headers={"Origin": "https://evil.invalid"}
            ).status_code
            == 403
        )
        client.delete("/api/v1/auth/session")
        assert client.get("/api/v1/measured/analyses").status_code == 401


def test_public_is_allowlist_not_get_based_permission(tmp_path):
    identifier = "run_public"
    app = create_app(settings(tmp_path, deployment_mode="public", public_result_ids=identifier))
    with TestClient(app) as client:
        for path in (
            "/system-status",
            "/research/findings",
            "/research/imports/capabilities",
            f"/runs/{identifier}/cell-state",
            f"/runs/{identifier}/cell-state/figure",
            "/runs/run_private/summary",
        ):
            assert client.get("/api/v1" + path).status_code == 403, path
        assert client.get("/api/v1/runs").json()["total"] == 0
        assert client.get(f"/api/v1/research/results/prediction/{identifier}/export").status_code == 404
        for method in (client.post, client.put, client.patch, client.delete):
            assert method("/api/v1/runs/" + identifier).status_code == 403
        assert client.get("/api/v1/auth/session").json()["read_only"]


def test_local_mode_denies_remote_client(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app, client=("203.0.113.1", 5000)) as client:
        assert client.get("/api/v1/measured/analyses").status_code == 401


def test_private_missing_token_fails_closed(tmp_path):
    app = create_app(settings(tmp_path, deployment_mode="private"))
    with TestClient(app) as client:
        assert client.get("/api/v1/measured/analyses").status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["embedded", "disabled"])
async def test_standalone_worker_rejects_other_execution_modes(tmp_path, mode):
    from backend.app.worker import serve

    app = create_app(settings(tmp_path, worker_mode=mode))
    with pytest.raises(RuntimeError, match="external mode"):
        await serve(app.state.container, "cpu", once=True)


@pytest.mark.asyncio
async def test_cancel_between_last_heartbeat_and_publish_never_publishes(tmp_path, monkeypatch):
    app = create_app(settings(tmp_path))

    async def runner(*args):
        return

    jobs = MeasuredJobs(app.state.container, runner=runner)
    job = request()
    jobs.store.create(job)
    original = jobs.store.finish

    def cancel_before_finish(identifier, token, status, **kwargs):
        if status == "completed":
            jobs.store.cancel(identifier)
        return original(identifier, token, status, **kwargs)

    monkeypatch.setattr(jobs.store, "finish", cancel_before_finish)
    assert await jobs.run_once()
    assert jobs.store.get(job["id"])[0]["status"] == "cancelled"
    assert not (tmp_path / "data/derived/measured" / job["id"]).exists()


def test_finish_attempt_does_not_overwrite_cancellation(tmp_path):
    store = RunStore(settings(tmp_path).database_url, create_schema=True)
    store.create("run_cancel", CreateRunRequest(cell_line="K562", perturbation="MYC"))
    attempt = store.start_attempt("run_cancel", worker_id="worker", lease_seconds=60)
    store.cancel("run_cancel")
    store.finish_attempt(attempt.id, succeeded=True)
    assert store.attempts("run_cancel")[0]["status"] == "cancelled"


def test_cancelled_prediction_does_not_serve_a_summary_renamed_before_commit(tmp_path):
    from backend.app.schemas import RunSummary

    app = create_app(settings(tmp_path))
    store = app.state.container.store
    store.create("run_cancel", CreateRunRequest(cell_line="K562", perturbation="MYC"))
    directory = tmp_path / "data/derived/runs/run_cancel"
    atomic_write_json(
        directory / "summary.json",
        RunSummary(
            run_id="run_cancel",
            status=RunStatus.COMPLETED,
            stage_progress=100,
            cell_line="K562",
            perturbation="MYC",
        ).model_dump(mode="json"),
    )
    store.cancel("run_cancel")
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/run_cancel/summary")
        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        assert response.json()["error_code"] == "RUN_CANCELLED"
        assert response.json()["stage_progress"] == 0


def test_import_identity_is_visible_without_input_paths(tmp_path):
    app = create_app(settings(tmp_path))
    row = app.state.measured.store.create(
        request()
        | {
            "import_id": "import_" + "b" * 24,
            "source": {"kind": "controlled_private_h5ad", "path": "C:/private/source.h5ad"},
        }
    )
    assert row["import_id"] == "import_" + "b" * 24
    assert row["source"]["type"] == "controlled_private_h5ad"
    assert "path" not in row["source"]


def test_private_unicode_bad_token_and_cross_origin_logout_are_rejected(tmp_path):
    app = create_app(
        settings(
            tmp_path, deployment_mode="private", workspace_token="random-secret", session_secure_cookie=False
        )
    )
    with TestClient(app) as client:
        assert client.post("/api/v1/auth/session", json={"token": "错误口令"}).status_code == 401
        client.post("/api/v1/auth/session", json={"token": "random-secret"})
        assert (
            client.delete("/api/v1/auth/session", headers={"Origin": "https://evil.invalid"}).status_code
            == 403
        )
        assert client.get("/api/v1/auth/session").json()["authenticated"]


def test_public_lists_export_and_legacy_summary_do_not_leak_private_content(tmp_path):
    from backend.app.schemas import RunSummary
    from backend.app.services.research_findings import ResearchFindings

    app = create_app(settings(tmp_path, deployment_mode="public", public_result_ids="run_public"))
    store = app.state.container.store
    for identifier in ("run_public", "run_private"):
        store.create(identifier, CreateRunRequest(cell_line="K562", perturbation="MYC"))
        directory = tmp_path / "data/derived/runs" / identifier
        directory.mkdir(parents=True)
        summary = RunSummary(
            run_id=identifier,
            status=RunStatus.COMPLETED,
            stage_progress=100,
            cell_line="K562",
            perturbation="MYC",
            warnings=["missing C:/private/input.h5ad"],
        )
        atomic_write_json(directory / "summary.json", summary.model_dump(mode="json"))
        atomic_write_json(
            directory / "manifest.json",
            {"outputs": {"summary.json": {"sha256": file_sha256(directory / "summary.json")}}},
        )
        store.transition(identifier, RunStatus.COMPLETED, 100)
    # Notes belong to the workspace even when the underlying result is published.
    ResearchFindings(app.state.container).create("prediction", "run_public", {}, "PRIVATE_NOTE_DO_NOT_SHARE")
    with TestClient(app) as client:
        assert [x["id"] for x in client.get("/api/v1/experiments").json()["items"]] == ["run_public"]
        assert [x["run_id"] for x in client.get("/api/v1/runs").json()["items"]] == ["run_public"]
        assert client.get("/api/v1/measured/analyses").json()["total"] == 0
        assert "C:/private" not in client.get("/api/v1/runs/run_public/summary").text
        export = client.get("/api/v1/research/results/prediction/run_public/export")
        assert export.status_code == 200, export.text
        assert export.json()["findings"] == []
        assert "PRIVATE_NOTE_DO_NOT_SHARE" not in export.text
        assert "C:/private" not in export.text
        assert client.get("/api/v1/research/results/prediction/run_private/export").status_code == 403
        catalog = client.get("/api/v1/data-catalog").json()
        assert catalog["source"]["scope"] == "allowlisted_frozen_results"
        assert len(catalog["items"]) == 1


def test_prediction_submission_requires_live_worker_and_keeps_existing_queue(tmp_path):
    from backend.tests.test_api_modes import settings as model_settings
    from backend.tests.test_api_modes import write_registry

    write_registry(tmp_path, valid=True)
    # The API may run on a CPU host: only the observed worker probes establish GPU readiness.
    app = create_app(model_settings(tmp_path, worker_enabled=True, gpu_available=False))
    container = app.state.container
    with TestClient(app) as client:
        payload = {"cell_line": "K562", "perturbation": "MYC", "n_cells": 64}
        assert not client.get("/api/v1/catalog/contexts").json()[0]["online_ready"]
        assert client.post("/api/v1/runs", json=payload).status_code == 503
        assert container.store.list_runs(limit=10, offset=0)[1] == 0
        heartbeat(container.store, "observed-gpu-worker", "gpu", {"prediction": True, "cuda_detected": True})
        assert client.get("/api/v1/catalog/contexts").json()[0]["online_ready"]
        assert client.post("/api/v1/runs", json=payload).status_code == 202
        with container.store.session_factory.begin() as session:
            session.execute(
                update(WorkerHeartbeatModel).values(
                    heartbeat_at=datetime.now(UTC)
                    - timedelta(seconds=container.settings.worker_stale_seconds + 1)
                )
            )
        assert not client.get("/api/v1/catalog/contexts").json()[0]["online_ready"]
        assert client.post("/api/v1/runs", json=payload | {"seed": 43}).status_code == 503
        records, total = container.store.list_runs(limit=10, offset=0)
        assert total == 1 and records[0].status == RunStatus.QUEUED


def test_embedded_readiness_needs_a_running_queue_and_real_probe(tmp_path, monkeypatch):
    from backend.app.services.worker_status import prediction_ready

    app = create_app(settings(tmp_path, worker_mode="embedded", worker_enabled=True, gpu_available=True))
    probe = {"prediction": False}
    monkeypatch.setattr("backend.app.services.worker_status.probe_capabilities", lambda *args: probe)
    assert not prediction_ready(app.state.container)
    with TestClient(app):
        assert app.state.container.queue._task is not None
        assert not prediction_ready(app.state.container)
        probe["prediction"] = True
        assert prediction_ready(app.state.container)
    assert not prediction_ready(app.state.container)


@pytest.mark.parametrize("deployment,mode", [("public", "external"), ("local", "disabled")])
def test_read_only_or_disabled_readiness_ignores_private_worker_heartbeats(tmp_path, deployment, mode):
    app = create_app(
        settings(
            tmp_path, deployment_mode=deployment, worker_mode=mode, worker_enabled=True, gpu_available=True
        )
    )
    heartbeat(app.state.container.store, "private-cpu", "cpu", {"cpu_analysis": True})
    heartbeat(app.state.container.store, "private-gpu", "gpu", {"prediction": True, "cuda_detected": True})
    with TestClient(app) as client:
        response = client.get("/api/v1/ready")
        assert response.status_code == 200
        assert response.json()["capabilities"] == {
            "result_browsing": True,
            "cpu_analysis": False,
            "prediction": False,
        }
        assert response.json()["workers"]["live"] == []
