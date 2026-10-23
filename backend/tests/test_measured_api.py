import asyncio
import io
import json
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.tests.test_api_runs import _settings
from backend.tests.test_measured_analysis import measured_inputs


def test_frozen_result_rejects_changed_analysis_knowledge_file(tmp_path):
    from backend.app.core.run_manifest import atomic_write_json, file_sha256
    from backend.app.services.measured_results import result_directory, verified_result

    identifier = "measured_" + "a" * 24
    directory = result_directory(tmp_path, identifier)
    directory.mkdir(parents=True)
    asset = tmp_path / "database.json"
    asset.write_text('{"version":1}')
    atomic_write_json(directory / "summary.json", {"source_kind": "measured"})
    atomic_write_json(
        directory / "manifest.json",
        {
            "id": identifier,
            "source_kind": "measured",
            "files": {"summary.json": file_sha256(directory / "summary.json")},
            "inputs": {"groups": {}, "analysis_assets": {"database.json": file_sha256(asset)}},
        },
    )
    digest = file_sha256(directory / "manifest.json")
    verified_result(tmp_path, identifier, digest)
    asset.write_text('{"version":2}')
    with pytest.raises(ValueError, match="知识库"):
        verified_result(tmp_path, identifier, digest)


def test_measured_table_accepts_complete_long_task_identifier(tmp_path, monkeypatch):
    import pandas as pd

    from backend.app.core.run_manifest import atomic_write_json, file_sha256

    task = (
        "Biosynthesis of core2 "
        "(beta-D-Galactosyl-1,3-(N-acetyl-beta-D-glucosaminyl-1,6)-N-acetyl-D-galactosaminyl-R)"
    )
    assert len(task) > 100
    app, _ = make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/measured/analyses", json={"cell_line": "K562", "perturbation": "ALDOA"}
        )
        identifier = response.json()["id"]
        wait_completed(client, identifier)
        directory = tmp_path / "data/derived/measured" / identifier
        pd.DataFrame([{"task": task, "control": 1.0, "observed": 2.0, "observed_delta": 1.0}]).to_csv(
            directory / "tasks.csv", index=False
        )
        path = directory / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["files"]["tasks.csv"] = file_sha256(directory / "tasks.csv")
        atomic_write_json(path, manifest)
        app.state.measured.store.update(identifier, manifest_sha256=file_sha256(path))
        response = client.get(
            f"/api/v1/measured/analyses/{identifier}/table", params={"kind": "tasks", "query": task}
        )
        assert response.status_code == 200, response.text
        assert response.json()["items"] == [
            {"task": task, "control": 1.0, "observed": 2.0, "observed_delta": 1.0}
        ]
        assert (
            client.get(
                f"/api/v1/measured/analyses/{identifier}/table", params={"kind": "tasks", "query": "x" * 501}
            ).status_code
            == 422
        )


def test_unregistered_optional_result_is_never_served(tmp_path, monkeypatch):
    app, _ = make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        reply = client.post("/api/v1/measured/analyses", json={"cell_line": "K562", "perturbation": "ALDOA"})
        identifier = reply.json()["id"]
        wait_completed(client, identifier)
        directory = tmp_path / "data/derived/measured" / identifier
        (directory / "projection-umap.json").write_text('{"points":[{"source":"predicted"}]}')
        assert (
            client.get(f"/api/v1/measured/analyses/{identifier}/projection?embedding=umap").status_code == 409
        )
        assert (
            client.get(f"/api/v1/measured/analyses/{identifier}/download?kind=projection").status_code == 409
        )


def make_app(root, monkeypatch):
    from backend.app.main import create_app
    from backend.app.services.measured_jobs import MeasuredJobs
    from backend.app.services.measured_worker import execute_measured_job

    registry = root / "data/registry"
    registry.mkdir(parents=True)
    for key in ("models", "datasets"):
        (registry / f"{key}.json").write_text(json.dumps({key: []}))
    groups, _ = measured_inputs(root)
    app = create_app(_settings(root, worker_enabled=False, gpu_available=False))
    monkeypatch.setattr(
        "backend.app.services.measured_jobs.pair_detail",
        lambda *args: {
            "source_status": "measured",
            "source_cell_count": 2,
        },
    )

    async def runner(request, staging, final, report):
        execute_measured_job(
            root, request, staging, final, report, inputs=groups, metabolism=False, compute_umap=False
        )

    app.state.measured = MeasuredJobs(app.state.container, runner=runner)
    return app, groups


def wait_completed(client, analysis_id):
    for _ in range(100):
        record = client.get(f"/api/v1/measured/analyses/{analysis_id}").json()
        if record["status"] not in {"queued", "preparing", "analysing"}:
            assert record["status"] == "completed", record
            return record
        time.sleep(0.02)
    pytest.fail("Measured fixture did not finish")


def test_real_measurement_analysis_api_works_with_gpu_and_prediction_worker_disabled(tmp_path, monkeypatch):
    app, groups = make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        reply = client.post("/api/v1/measured/analyses", json={"cell_line": "K562", "perturbation": "ALDOA"})
        assert reply.status_code == 202, reply.text
        record = wait_completed(client, reply.json()["id"])
        assert record["source_kind"] == "measured"
        assert record["summary"]["gene_count"] == 4
        assert record["summary"]["counts"] == {"control": 3, "observed": 2}
        identifier = record["id"]
        assert client.get("/api/v1/measured/analyses").json()["total"] == 1
        table = client.get(f"/api/v1/measured/analyses/{identifier}/table?kind=genes&limit=2").json()
        assert table["total"] == 4 and len(table["items"]) == 2
        assert all("predicted" not in row for row in table["items"])
        projection = client.get(f"/api/v1/measured/analyses/{identifier}/projection").json()
        assert {p["source"] for p in projection["points"]} == {"control", "observed"}
        csv = client.get(f"/api/v1/measured/analyses/{identifier}/download?kind=genes")
        assert csv.status_code == 200 and csv.headers["cache-control"] == "no-store"
        assert "observed_delta" in csv.text and "source_kind" in csv.text
        bundle = client.get(f"/api/v1/measured/analyses/{identifier}/download?kind=bundle")
        archive = zipfile.ZipFile(io.BytesIO(bundle.content))
        assert {"summary.json", "genes.csv", "manifest.json"}.issubset(archive.namelist())
        assert not any("predicted" in name for name in archive.namelist())
        # An existing frozen analysis cannot silently follow changed input bytes.
        with Path(groups["groups"]["observed"]["path"]).open("ab") as stream:
            stream.write(b"changed")
        assert client.get(f"/api/v1/measured/analyses/{identifier}").status_code == 409


def test_measured_analysis_rejects_unknown_source_extra_fields_and_cross_site(tmp_path, monkeypatch):
    app, _ = make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        payload = {"cell_line": "K562", "perturbation": "ALDOA"}
        assert (
            client.post("/api/v1/measured/analyses", json=payload | {"path": "../secret"}).status_code == 422
        )
        assert (
            client.post(
                "/api/v1/measured/analyses", json=payload, headers={"origin": "https://unrelated.example"}
            ).status_code
            == 403
        )
        monkeypatch.setattr(
            "backend.app.services.measured_jobs.pair_detail",
            lambda *args: {
                "source_status": "not_in_source",
                "source_cell_count": 0,
            },
        )
        assert client.post("/api/v1/measured/analyses", json=payload).status_code == 422
        assert client.get("/api/v1/measured/analyses").json()["total"] == 0


@pytest.mark.asyncio
async def test_measured_job_cancellation_preserves_history_and_releases_install_lock(tmp_path, monkeypatch):
    from backend.app.services.measured_jobs import MeasuredJobs

    app, _ = make_app(tmp_path, monkeypatch)
    entered = asyncio.Event()

    async def runner(request, staging, final, report):
        entered.set()
        await asyncio.Event().wait()

    manager = MeasuredJobs(app.state.container, runner=runner)
    row = await manager.start({"cell_line": "K562", "perturbation": "ALDOA", "max_cells": 256, "seed": 42})
    await entered.wait()
    await manager.cancel(row["id"])
    assert manager.get(row["id"])["status"] == "cancelled"
    next_row = await manager.start(
        {"cell_line": "K562", "perturbation": "ALDOA", "max_cells": 256, "seed": 42}
    )
    assert next_row["id"] != row["id"]
    await manager.close()
    assert manager.list()["total"] == 2
