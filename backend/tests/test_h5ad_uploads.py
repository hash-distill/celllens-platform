import asyncio
import io
import json
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import anndata as ad
import h5py
import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect

from backend.app.access import WorkspaceAccessMiddleware
from backend.app.api.uploads import router
from backend.app.core.run_manifest import file_sha256
from backend.app.services.controlled_import import capabilities as legacy_capabilities
from backend.app.services.controlled_import import get_import
from backend.app.services.h5ad_uploads import (
    UploadTooLarge,
    capabilities,
    delete_upload,
    get_upload,
    import_upload,
    receive_upload,
)


def settings_at(root, **overrides):
    values = dict(
        project_root=root,
        deployment_mode="local",
        api_prefix="/api/v1",
        workspace_token="",
        public_result_ids="",
        h5ad_upload_enabled=True,
        h5ad_upload_max_bytes=1_000_000,
        h5ad_upload_max_total_bytes=2_000_000,
        h5ad_upload_ttl_seconds=86_400,
        h5ad_upload_timeout_seconds=5,
        controlled_import_enabled=False,
        controlled_import_root=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def h5ad_bytes(root, *, missing=False):
    path = root / "fixture.h5ad"
    obs = pd.DataFrame(
        {
            "condition": ["CTRL", "CTRL", "KO", "KO"],
            "total_counts": [1000, 1000, 1000, 1000],
            "cell_line": ["Custom"] * 4,
            "batch": pd.Categorical(["one", "one", "two", None if missing else "two"]),
        },
        index=["cell0", "cell1", "cell2", "cell3"],
    )
    frame = ad.AnnData(
        np.array([[10, 90], [20, 80], [40, 60], [80, 20]], dtype=float),
        obs=obs,
        var=pd.DataFrame(index=["ALDOA", "GAPDH"]),
    )
    frame.write_h5ad(path)
    return path.read_bytes()


async def chunks(data, size=2048):
    for offset in range(0, len(data), size):
        yield data[offset : offset + size]


def app_at(settings, *, middleware=False):
    app = FastAPI()
    app.state.container = SimpleNamespace(settings=settings)
    app.include_router(router, prefix=settings.api_prefix)
    if middleware:
        app.add_middleware(WorkspaceAccessMiddleware, settings=settings)
    return app


def import_body():
    return {
        "expression_scale": "raw_counts",
        "total_counts_key": "total_counts",
        "group_key": "condition",
        "control_label": "CTRL",
        "target_label": "KO",
        "cell_line": "Custom",
        "perturbation": "ALDOA",
    }


def test_browser_roundtrip_metadata_and_immutable_import_without_server_directory(tmp_path):
    settings = settings_at(tmp_path)
    assert capabilities(settings)["available"]
    assert not legacy_capabilities(settings)["available"]
    payload = h5ad_bytes(tmp_path, missing=True)
    with TestClient(app_at(settings, middleware=True)) as client:
        prefix = "/api/v1/research/uploads"
        assert client.get(prefix + "/capabilities").json()["available"]
        response = client.post(
            prefix,
            params={"filename": "我的实验.h5ad"},
            content=payload,
            headers={"content-type": "application/octet-stream"},
        )
        assert response.status_code == 201, response.text
        metadata = response.json()
        assert metadata["bytes"] == len(payload)
        assert metadata["cells"] == 4 and metadata["genes"] == 2
        assert metadata["suggested_cell_line"] == "Custom"
        assert metadata["gene_preview"] == ["ALDOA", "GAPDH"]
        assert "expression_scale" not in metadata
        assert "path" not in metadata and str(tmp_path) not in response.text
        columns = {column["name"]: column for column in metadata["obs_columns"]}
        assert columns["condition"]["values"] == [{"label": "CTRL", "count": 2}, {"label": "KO", "count": 2}]
        assert columns["total_counts"]["kind"] == "numeric"
        assert columns["batch"]["missing_count"] == 1
        url = prefix + "/" + metadata["upload_id"]
        assert client.get(url).json() == metadata
        created = client.post(url + "/imports", json=import_body())
        assert created.status_code == 201, created.text
        imported = created.json()
        assert imported["source_filename"] == "我的实验.h5ad"
        assert imported["source_sha256"] == metadata["sha256"]
        assert imported["normalization"]["denominator"] == "total_counts"
        assert "relative_path" not in imported["contract"]
        assert client.delete(url).status_code == 204
        assert client.get(url).status_code == 404
        # Upload cleanup cannot change the independent frozen source or normalized import.
        assert get_import(tmp_path, imported["import_id"])["manifest_sha256"] == imported["manifest_sha256"]
        control = ad.read_h5ad(tmp_path / imported["groups"]["control"]["path"])
        np.testing.assert_allclose(control.X, np.log1p(np.array([[10, 90], [20, 80]]) * 10))


@pytest.mark.parametrize("filename", ["../x.h5ad", "C:\\x.h5ad", "/tmp/x.h5ad", "x.csv", "x.h5ad ", ".h5ad"])
def test_rejects_paths_and_non_h5ad_names(tmp_path, filename):
    with TestClient(app_at(settings_at(tmp_path))) as client:
        response = client.post(
            "/api/v1/research/uploads",
            params={"filename": filename},
            content=b"x",
            headers={"content-type": "application/octet-stream"},
        )
        assert response.status_code == 422
    assert not list(tmp_path.rglob("source.*"))


def test_http_guards_for_private_public_csrf_and_content_type(tmp_path):
    settings = settings_at(tmp_path, deployment_mode="private", workspace_token="test-token")
    url = "/api/v1/research/uploads?filename=experiment.h5ad"
    with TestClient(app_at(settings, middleware=True)) as client:
        assert client.post(url, content=b"x").status_code == 401
        headers = {"authorization": "Bearer test-token", "content-type": "application/octet-stream"}
        assert (
            client.post(url, content=b"x", headers={**headers, "origin": "https://evil.test"}).status_code
            == 403
        )
        assert (
            client.post(url, content=b"x", headers={**headers, "sec-fetch-site": "cross-site"}).status_code
            == 403
        )
        assert (
            client.post(url, content=b"x", headers={"authorization": "Bearer test-token"}).status_code == 415
        )
        assert client.get("/api/v1/research/uploads/capabilities", headers=headers).json()["available"]
    settings.deployment_mode = "public"
    with TestClient(app_at(settings, middleware=True)) as client:
        assert client.post(url, content=b"x").status_code == 403
    # Service/router defense also holds independently of the access middleware.
    with TestClient(app_at(settings)) as client:
        assert not client.get("/api/v1/research/uploads/capabilities").json()["available"]
        assert client.post(url, content=b"x", headers=headers).status_code == 403


@pytest.mark.asyncio
async def test_declared_and_actual_chunked_limits_and_disconnect_cleanup(tmp_path):
    settings = settings_at(tmp_path, h5ad_upload_max_bytes=8)
    with pytest.raises(UploadTooLarge):
        await receive_upload(settings, "x.h5ad", chunks(b"123456789"), 9)
    with pytest.raises(UploadTooLarge):
        await receive_upload(settings, "x.h5ad", chunks(b"123456789", 3))

    async def disconnected():
        yield b"1234"
        raise ClientDisconnect()

    with pytest.raises(ClientDisconnect):
        await receive_upload(settings, "x.h5ad", disconnected())

    async def cancelled():
        yield b"1234"
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await receive_upload(settings, "x.h5ad", cancelled())
    with pytest.raises(ValueError, match="Content-Length"):
        await receive_upload(settings, "x.h5ad", chunks(b"1234"), 5)
    assert not list((tmp_path / "data/uploads").glob("upload_*"))


@pytest.mark.asyncio
async def test_invalid_hdf_external_links_and_invalid_ids_never_escape_storage(tmp_path):
    settings = settings_at(tmp_path)
    with pytest.raises(ValueError, match="有效的 H5AD"):
        await receive_upload(settings, "invalid.h5ad", chunks(b"not an HDF file"))
    unsafe = io.BytesIO()
    with h5py.File(unsafe, "w") as handle:
        handle["X"] = h5py.ExternalLink("outside.h5ad", "/X")
    with pytest.raises(ValueError, match="链接"):
        await receive_upload(settings, "external.h5ad", chunks(unsafe.getvalue()))
    for identifier in ("../fixture.h5ad", "upload_" + "a" * 31, "unknown"):
        with pytest.raises(KeyError):
            get_upload(settings, identifier)
        with pytest.raises(KeyError):
            delete_upload(settings, identifier)
    assert not list((tmp_path / "data/uploads").glob("upload_*"))


@pytest.mark.asyncio
async def test_quota_expiry_integrity_and_safe_cleanup(tmp_path):
    data = h5ad_bytes(tmp_path)
    settings = settings_at(tmp_path, h5ad_upload_max_total_bytes=len(data) + 1)
    metadata = await receive_upload(settings, "one.h5ad", chunks(data))
    with pytest.raises(UploadTooLarge):
        await receive_upload(settings, "two.h5ad", chunks(data))
    directory = tmp_path / "data/uploads" / metadata["upload_id"]
    path = directory / "metadata.json"
    metadata["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    path.write_text(json.dumps(metadata), encoding="utf-8")
    replacement = await receive_upload(settings, "two.h5ad", chunks(data), len(data))
    assert not directory.exists()
    source = tmp_path / "data/uploads" / replacement["upload_id"] / "source.h5ad"
    before = file_sha256(source)
    source.write_bytes(source.read_bytes() + b"change")
    assert file_sha256(source) != before
    with pytest.raises(ValueError, match="改变"):
        get_upload(settings, replacement["upload_id"])
    with pytest.raises(ValueError, match="改变"):
        import_upload(settings, replacement["upload_id"], import_body())


@pytest.mark.asyncio
async def test_duplicate_ids_rejected_and_large_group_options_are_bounded(tmp_path):
    path = tmp_path / "many.h5ad"
    size = 1005
    frame = ad.AnnData(
        np.ones((size, 1)),
        obs=pd.DataFrame(
            {"condition": [f"label{i}" for i in range(size)]}, index=[f"cell{i}" for i in range(size)]
        ),
        var=pd.DataFrame(index=["ALDOA"]),
    )
    frame.write_h5ad(path)
    settings = settings_at(tmp_path)
    metadata = await receive_upload(settings, "many.h5ad", chunks(path.read_bytes()))
    column = metadata["obs_columns"][0]
    assert column["unique_count"] == size
    assert len(column["values"]) == 1000 and column["truncated"]
    frame.obs_names = ["same"] * size
    frame.write_h5ad(path)
    with pytest.raises(ValueError, match="必须唯一"):
        await receive_upload(settings, "duplicate.h5ad", chunks(path.read_bytes()))


def test_upload_import_rejects_path_override_and_missing_scientific_declarations(tmp_path):
    with TestClient(app_at(settings_at(tmp_path))) as client:
        endpoint = "/api/v1/research/uploads/upload_" + "a" * 32 + "/imports"
        body = import_body()
        body["relative_path"] = "../../outside.h5ad"
        assert client.post(endpoint, json=body).status_code == 422
        body.pop("relative_path")
        body.pop("total_counts_key")
        assert client.post(endpoint, json=body).status_code == 422


@pytest.mark.asyncio
async def test_cancellation_waits_for_inspection_before_cleanup_and_releases_lease(tmp_path, monkeypatch):
    from backend.app.services import h5ad_uploads

    settings = settings_at(tmp_path)
    data = h5ad_bytes(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    actual_inspect = h5ad_uploads.inspect_h5ad

    def blocked_inspect(path):
        entered.set()
        assert release.wait(5)
        # The cancelled request must preserve the source until this reader is done.
        assert path.is_file()
        return actual_inspect(path)

    monkeypatch.setattr(h5ad_uploads, "inspect_h5ad", blocked_inspect)
    pending = asyncio.create_task(receive_upload(settings, "cancelled.h5ad", chunks(data)))
    assert await asyncio.to_thread(entered.wait, 5)
    pending.cancel()
    try:
        with pytest.raises(RuntimeError, match="另一个服务"):
            await receive_upload(settings, "concurrent.h5ad", chunks(data))
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert not list((tmp_path / "data/uploads").glob("upload_*"))
    monkeypatch.setattr(h5ad_uploads, "inspect_h5ad", actual_inspect)
    completed = await receive_upload(settings, "retry.h5ad", chunks(data))
    assert completed["cells"] == 4


@pytest.mark.asyncio
async def test_stalled_stream_times_out_and_cleans_received_bytes(tmp_path):
    settings = settings_at(tmp_path, h5ad_upload_timeout_seconds=0.05)

    async def stalled():
        yield b"partial bytes"
        await asyncio.Event().wait()

    with pytest.raises(TimeoutError):
        await receive_upload(settings, "stalled.h5ad", stalled())
    assert not list((tmp_path / "data/uploads").glob("upload_*"))


def test_http_checks_size_before_parsing_and_rejects_invalid_hdf(tmp_path):
    settings = settings_at(tmp_path, h5ad_upload_max_bytes=8)
    with TestClient(app_at(settings)) as client:
        endpoint = "/api/v1/research/uploads?filename=sample.h5ad"
        headers = {"content-type": "application/octet-stream"}
        assert client.post(endpoint, content=b"123456789", headers=headers).status_code == 413
        assert client.post(endpoint, content=b"invalid", headers=headers).status_code == 422
        assert client.post(endpoint, content=b"", headers=headers).status_code == 422
    assert not list((tmp_path / "data/uploads").glob("upload_*"))


@pytest.mark.asyncio
@pytest.mark.parametrize("middleware", [False, True])
@pytest.mark.parametrize("disconnect", [False, True])
async def test_asgi_disconnect_after_body_before_publish(tmp_path, middleware, disconnect, monkeypatch):
    from backend.app.services import h5ad_uploads

    data = h5ad_bytes(tmp_path)
    settings = settings_at(tmp_path)
    app = app_at(settings, middleware=middleware)
    messages = asyncio.Queue()
    messages.put_nowait({"type": "http.request", "body": data, "more_body": False})
    inspected = threading.Event()
    release = threading.Event()
    actual_inspect = h5ad_uploads.inspect_h5ad

    def inspect_while_client_disconnects(path):
        inspected.set()
        assert release.wait(5)
        return actual_inspect(path)

    monkeypatch.setattr(h5ad_uploads, "inspect_h5ad", inspect_while_client_disconnects)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/research/uploads",
        "raw_path": b"/api/v1/research/uploads",
        "query_string": b"filename=sample.h5ad",
        "root_path": "",
        "headers": [(b"host", b"localhost"), (b"content-type", b"application/octet-stream")],
        "client": ("127.0.0.1", 12345),
        "server": ("localhost", 80),
    }
    responses = []

    async def send(message):
        responses.append(message)

    pending = asyncio.create_task(app(scope, messages.get, send))
    try:
        assert await asyncio.to_thread(inspected.wait, 5)
        if disconnect:
            messages.put_nowait({"type": "http.disconnect"})
    finally:
        release.set()
    await asyncio.wait_for(pending, 5)
    status = next(message["status"] for message in responses if message["type"] == "http.response.start")
    assert status == (400 if disconnect else 201)
    stored = list((tmp_path / "data/uploads").glob("upload_*"))
    assert len(stored) == (0 if disconnect else 1)
