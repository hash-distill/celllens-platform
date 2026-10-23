import asyncio
import hashlib
import json
import sys
from types import SimpleNamespace

import httpx
import pytest

from backend.app.core.registry import AssetRegistry
from backend.app.services.resource_downloads import ResourceManager, download_asset


def asset(cell="k562", value=b"verified model bytes", name="config.yaml"):
    return {
        "name": name,
        "target": f"models/state-replogle-{cell}/{name}",
        "url": f"https://huggingface.co/arcinstitute/ST-HVG-Replogle/resolve/{'a' * 40}/{cell}/{name}",
        "size_bytes": len(value),
        "sha256": hashlib.sha256(value).hexdigest(),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("resume,ignored", [(False, False), (True, False), (True, True)])
async def test_download_checks_ranges_and_hash_before_publication(tmp_path, resume, ignored):
    value = b"verified model bytes"
    spec = asset(value=value)
    target = tmp_path / spec["target"]
    target.parent.mkdir(parents=True)
    partial = target.with_name(target.name + ".part")
    if resume:
        partial.write_bytes(value[:5])
    requests, progress = [], []

    def upstream(request):
        requests.append(request)
        if resume:
            assert request.headers["range"] == "bytes=5-"
        if resume and not ignored:
            return httpx.Response(
                206, content=value[5:], headers={"content-range": f"bytes 5-{len(value) - 1}/{len(value)}"}
            )
        return httpx.Response(200, content=value)

    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
        await download_asset(tmp_path, spec, client, lambda done: progress.append(done))
    assert target.read_bytes() == value
    assert not partial.exists()
    assert requests and progress[-1] == len(value)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["wrong_hash", "wrong_range", "too_large", "redirect_private"])
async def test_bad_download_never_replaces_existing_file(tmp_path, mode):
    spec = asset()
    target = tmp_path / spec["target"]
    target.parent.mkdir(parents=True)
    target.write_bytes(b"preserve corrupted original for recovery")
    original = target.read_bytes()
    if mode == "wrong_range":
        target.with_name(target.name + ".part").write_bytes(b"verif")

    def upstream(request):
        if mode == "redirect_private":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:3307/private"})
        if mode == "wrong_range":
            return httpx.Response(206, content=b"remaining", headers={"content-range": "bytes 0-8/20"})
        return httpx.Response(200, content=b"x" * (spec["size_bytes"] + (1 if mode == "too_large" else 0)))

    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
        with pytest.raises(ValueError):
            await download_asset(tmp_path, spec, client, lambda done: None)
    assert target.read_bytes() == original


@pytest.mark.asyncio
async def test_catalog_cannot_escape_workspace(tmp_path):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        with pytest.raises(ValueError):
            await download_asset(tmp_path, asset() | {"target": "../outside.ckpt"}, client, lambda _: None)


def setup_manager(tmp_path, transport, control_preparer=None):
    registry_root = tmp_path / "data/registry"
    registry_root.mkdir(parents=True, exist_ok=True)
    dataset = {
        "id": "original-k562",
        "cell_line": "K562",
        "enabled": True,
        "control_path": "data/raw/old-control.h5ad",
        "control_sha256": "b" * 64,
        "expression_scale": "log1p_cp10k",
    }
    (registry_root / "datasets.json").write_text(json.dumps({"datasets": [dataset]}))
    models = [{"id": f"model-{cell}", "cell_line": cell, "enabled": True} for cell in ("K562", "RPE1")]
    (registry_root / "models.json").write_text(json.dumps({"models": models}))
    registry = AssetRegistry(tmp_path, registry_root)
    container = SimpleNamespace(registry=registry, settings=SimpleNamespace(project_root=tmp_path))
    catalog = {
        "packs": [
            {
                "cell_line": cell,
                "repo": "official",
                "revision": "a" * 40,
                "license": "Non-commercial",
                "source_url": "https://huggingface.co/arcinstitute/ST-HVG-Replogle",
                "files": [asset(cell.lower())],
            }
            for cell in ("K562", "RPE1")
        ]
    }
    return ResourceManager(container, catalog=catalog, transport=transport, control_preparer=control_preparer)


@pytest.mark.asyncio
async def test_only_requested_background_is_downloaded_and_old_dataset_is_kept(tmp_path):
    calls = []

    def upstream(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=b"verified model bytes")

    async def prepare(cell, output, report):
        assert cell == "K562"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"verified control fixture")

    manager = setup_manager(tmp_path, httpx.MockTransport(upstream), prepare)
    await manager.start("K562", True)
    await manager.task
    assert manager.jobs["K562"]["status"] == "completed"
    assert calls and all("k562" in call for call in calls)
    assert not (tmp_path / asset("rpe1")["target"]).exists()
    rows = manager.container.registry.datasets
    assert rows[0]["id"] != "original-k562"
    assert any(row["id"] == "original-k562" for row in rows)
    assert manager.container.registry.dataset_for("K562").payload["id"] == rows[0]["id"]
    # A second request reuses verified model and registered control without any network call.
    calls.clear()
    await manager.start("K562", True)
    await manager.task
    assert not calls
    assert len(manager.container.registry.datasets) == 2


@pytest.mark.asyncio
async def test_license_and_duplicate_job_gate_and_cancellation(tmp_path):
    started = asyncio.Event()

    async def upstream(request):
        started.set()
        await asyncio.Event().wait()

    manager = setup_manager(tmp_path, httpx.MockTransport(upstream))
    with pytest.raises(ValueError):
        await manager.start("K562", False)
    await manager.start("K562", True)
    await started.wait()
    with pytest.raises(RuntimeError):
        await manager.start("RPE1", True)
    await manager.cancel("K562")
    assert manager.jobs["K562"]["status"] == "cancelled"
    # Persisted interrupted jobs are not falsely marked ready after a process restart.
    saved = manager.state_path
    state = json.loads(saved.read_text())
    state["K562"]["status"] = "downloading"
    saved.write_text(json.dumps(state))
    restored = ResourceManager(manager.container, catalog=manager.catalog)
    assert restored.jobs["K562"]["status"] == "interrupted"


@pytest.mark.asyncio
async def test_cancel_before_task_starts_releases_cross_process_lock(tmp_path):
    manager = setup_manager(tmp_path, httpx.MockTransport(lambda _: httpx.Response(500)))
    await manager.start("K562", True)
    await manager.cancel("K562")
    assert manager.active_cell is None
    assert manager.jobs["K562"]["status"] == "cancelled"
    await manager.start("RPE1", True)
    await manager.cancel("RPE1")


@pytest.mark.asyncio
async def test_other_api_process_observes_live_job_without_cancelling_owner(tmp_path):
    started = asyncio.Event()
    finish = asyncio.Event()

    async def upstream(request):
        started.set()
        await finish.wait()
        return httpx.Response(200, content=b"verified model bytes")

    async def prepare(cell, output, report):
        output.write_bytes(b"verified control fixture")

    owner = setup_manager(tmp_path, httpx.MockTransport(upstream), prepare)
    observer_container = SimpleNamespace(
        settings=owner.container.settings,
        registry=AssetRegistry(tmp_path, owner.container.registry.registry_root),
    )
    observer = ResourceManager(observer_container, catalog=owner.catalog)
    await owner.start("K562", True)
    await started.wait()
    try:
        state = observer.snapshot()
        assert state["active_cell"] == "K562" and not state["can_cancel"]
        assert state["items"][0]["job"]["status"] == "downloading"
        with pytest.raises(RuntimeError):
            await observer.start("RPE1", True)
        with pytest.raises(RuntimeError):
            await observer.cancel("K562")
        await observer.close()
        assert not owner.task.done()
        finish.set()
        await owner.task
        state = observer.snapshot()
        assert state["active_cell"] is None
        assert state["items"][0]["job"]["status"] == "completed"
        assert state["items"][0]["ready"]
    finally:
        await owner.close()


def test_official_checkpoint_requires_all_pinned_companions(tmp_path):
    from backend.app.core.errors import AssetNotReadyError
    from backend.app.core.model_assets import official_bundles
    from backend.app.core.registry import RegistryEntry

    registry_root = tmp_path / "data/registry"
    registry_root.mkdir(parents=True)
    for name in ("models", "datasets"):
        (registry_root / f"{name}.json").write_text(json.dumps({name: []}))
    registry = AssetRegistry(tmp_path, registry_root)
    bundle = official_bundles()[0]
    checkpoint = next(item for item in bundle["files"] if item["name"] == "checkpoints/final.ckpt")
    entry = RegistryEntry(
        {
            "id": "official",
            "cell_line": bundle["cell_line"],
            "checkpoint_sha256": checkpoint["sha256"],
            "model_dir": "models/official",
        },
        tmp_path,
    )
    assert not registry.model_companions_valid_cached(entry)
    with pytest.raises(AssetNotReadyError):
        registry.verify_model_companions(entry)
    custom = RegistryEntry(entry.payload | {"checkpoint_sha256": "f" * 64}, tmp_path)
    assert registry.model_companions_valid_cached(custom)


@pytest.mark.asyncio
async def test_cancelling_control_preparation_reaps_its_real_child(tmp_path, monkeypatch):
    from backend.app.services.resource_control import run_control_process

    started = asyncio.Event()
    children = []
    spawn = asyncio.create_subprocess_exec

    async def small_child(*args, **kwargs):
        # Keep the OS pipes and termination behavior real without querying the
        # atlas or waiting for a scientific process to finish.
        code = 'import json,time; print(json.dumps({"message":"started"}),flush=True); time.sleep(60)'
        child = await spawn(sys.executable, "-c", code, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", small_child)
    task = asyncio.create_task(
        run_control_process(tmp_path, "RPE1", tmp_path / "control.h5ad", lambda _: started.set())
    )
    try:
        await asyncio.wait_for(started.wait(), 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert children and children[0].returncode is not None
        assert not (tmp_path / "control.h5ad").exists()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def test_resource_api_only_accepts_fixed_backgrounds_and_same_origin(tmp_path):
    from fastapi.testclient import TestClient

    from backend.app.config import Settings
    from backend.app.main import create_app

    root = tmp_path / "data/registry"
    root.mkdir(parents=True)
    for name in ("models", "datasets"):
        (root / f"{name}.json").write_text(json.dumps({name: []}))
    app = create_app(
        Settings(
            _env_file=None,
            project_root=tmp_path,
            database_url=f"sqlite+pysqlite:///{tmp_path / 'api.db'}",
            create_database_schema=True,
        )
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/resources")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert len(response.json()["items"]) == 4
        assert all(not row["ready"] for row in response.json()["items"])
        assert (
            client.post("/api/v1/resources/K562/download", json={"accepted_license": False}).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/resources/K562/download",
                json={"accepted_license": True},
                headers={"origin": "https://evil.example"},
            ).status_code
            == 403
        )
        assert (
            client.post("/api/v1/resources/unknown/download", json={"accepted_license": True}).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/resources/K562/download",
                json={"accepted_license": True, "url": "https://evil.example"},
            ).status_code
            == 422
        )
