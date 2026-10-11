import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from backend.app.assistant import AssistantService, Connection, build_context
from backend.app.config import Settings
from backend.app.core.run_manifest import file_sha256
from backend.app.main import create_app
from backend.app.schemas import CreateRunRequest, RunStatus


def connection(**changes):
    values = dict(base_url="https://api.openai.com/v1", model="user-model", api_key="secret-key")
    return Connection(**(values | changes))


@pytest.mark.parametrize(
    "url",
    [
        "http://api.openai.com/v1",
        "https://evil.test/v1",
        "http://127.0.0.1:8000",
        "https://secret@api.openai.com/v1",
        "https://api.openai.com/v1?key=secret",
        "https://api.openai.com:444/v1",
        "https://api.openai.com/v1#secret",
    ],
)
def test_url_restrictions(url):
    with pytest.raises(HTTPException):
        AssistantService(Settings(_env_file=None)).endpoint(url)


@pytest.mark.asyncio
@pytest.mark.parametrize("token_parameter", ["max_completion_tokens", "max_tokens"])
async def test_completion_is_bounded_and_read_only(token_parameter):
    async def handler(request):
        body = json.loads(request.content)
        assert request.url == "https://api.openai.com/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer secret-key"
        assert body["model"] == "user-model"
        assert body[token_parameter] == 2048
        assert (
            "max_tokens" if token_parameter == "max_completion_tokens" else "max_completion_tokens"
        ) not in body
        assert "tools" not in body and "temperature" not in body
        assert "secret-key" not in request.content.decode()
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "辅助解读"}, "finish_reason": "length"}],
                "usage": {"total_tokens": 20},
            },
        )

    service = AssistantService(Settings(_env_file=None), transport=httpx.MockTransport(handler))
    result = await service.complete(
        connection(token_parameter=token_parameter), [{"role": "user", "content": "data"}]
    )
    assert result["text"] == "辅助解读" and result["finish_reason"] == "length"
    assert "secret-key" not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["error", "redirect", "large", "invalid", "empty", "timeout"])
async def test_upstream_errors_do_not_leak(mode):
    async def handler(request):
        if mode == "timeout":
            raise httpx.ReadTimeout("secret-key")
        if mode == "error":
            return httpx.Response(401, text="secret-key")
        if mode == "redirect":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:8000"})
        if mode == "large":
            return httpx.Response(200, content=b"s" * 140_000)
        if mode == "empty":
            return httpx.Response(200, json={"choices": [{"message": {"content": None}}]})
        return httpx.Response(200, text="secret-key")

    service = AssistantService(Settings(_env_file=None), transport=httpx.MockTransport(handler))
    with pytest.raises(HTTPException) as error:
        await service.complete(connection(), [])
    assert "secret-key" not in str(error.value.detail)


def test_context_is_filtered_and_tampering_rejected(tmp_path):
    settings = Settings(_env_file=None, project_root=tmp_path)
    analysis_id = "ana_" + "a" * 32
    root = settings.user_analysis_root / analysis_id
    root.mkdir(parents=True)
    report = {
        "analysis_id": analysis_id,
        "dataset_id": "ds_" + "b" * 32,
        "qc": {"n_cells": 32, "n_genes": 6546, "groups": {"a": 16, "b": 16}},
        "genes": [{"gene": "MYC", "group": "a", "mean_log1p_cp10k": 2}],
        "projection": {"points": [{"cell_id": "private-cell"}]},
        "provenance": {
            "source_sha256": "c" * 64,
            "metadata": {"description": "private-description", "expression_scale": "raw_counts"},
        },
    }
    path = root / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    analysis = {
        "id": analysis_id,
        "status": "completed",
        "artifacts": {"report.json": {"sha256": file_sha256(path)}},
    }
    container = SimpleNamespace(settings=settings, user_store=SimpleNamespace(analysis=lambda *_: analysis))
    request = Request({"type": "http", "app": SimpleNamespace(state=SimpleNamespace(container=container))})
    context = build_context(request, "analysis", analysis_id)
    text = json.dumps(context)
    assert "private-cell" not in text and "private-description" not in text
    assert context["data"]["qc"]["n_cells"] == 32
    assert len(context["context_sha256"]) == 64
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(HTTPException):
        build_context(request, "analysis", analysis_id)


def test_assistant_api_limits_and_validation_redaction(tmp_path):
    registry = tmp_path / "data" / "registry"
    registry.mkdir(parents=True)
    for name in ["models", "datasets"]:
        (registry / (name + ".json")).write_text(json.dumps({name: []}))
    app = create_app(
        Settings(
            _env_file=None,
            project_root=tmp_path,
            database_url=f"sqlite+pysqlite:///{tmp_path / 'test.db'}",
            create_database_schema=True,
        )
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/assistant/test", json={"api_key": "secret-key", "model": {"secret": "secret-key"}}
        )
        assert response.status_code == 422 and "secret-key" not in response.text
        assert response.headers["cache-control"] == "no-store"
        response = client.post("/api/v1/assistant/test", json={}, headers={"origin": "https://evil.test"})
        assert response.status_code == 403
        response = client.post("/api/v1/assistant/test", content=b"s" * 70_000)
        assert response.status_code == 413
        assert client.get("/api/v1/assistant/capabilities").json()["protocol"] == "chat/completions"


def test_interpret_uses_registered_run_and_checks_preview_before_network(tmp_path):
    registry = tmp_path / "data" / "registry"
    registry.mkdir(parents=True)
    for name in ["models", "datasets"]:
        (registry / (name + ".json")).write_text(json.dumps({name: []}))
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        database_url=f"sqlite+pysqlite:///{tmp_path / 'assistant.db'}",
        create_database_schema=True,
    )
    app = create_app(settings)
    store = app.state.container.store
    store.create("run_fixture", CreateRunRequest(cell_line="K562", perturbation="MYC"))
    root = settings.derived_root / "run_fixture"
    root.mkdir(parents=True)
    docs = {
        "summary.json": {
            "run_id": "run_fixture",
            "cell_line": "K562",
            "perturbation": "MYC",
            "top_genes": [{"id": "MYC", "predicted_delta": -1}],
            "result_kind": "frozen_model_result",
        },
        "manifest.json": {
            "source_type": "online",
            "assets": {"checkpoint_path": "private/path", "checkpoint_sha256": "b" * 64},
        },
    }
    for filename, document in docs.items():
        path = root / filename
        path.write_text(json.dumps(document), encoding="utf-8")
        store.register_artifact(
            "run_fixture",
            filename,
            f"run_fixture/{filename}",
            file_sha256(path),
            path.stat().st_size,
            "application/json",
        )
    store.transition("run_fixture", RunStatus.COMPLETED, 100)
    calls = []

    async def upstream(request):
        calls.append(json.loads(request.content))
        assert "private/path" not in request.content.decode()
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "解读"}, "finish_reason": "stop"}]}
        )

    app.state.assistant = AssistantService(settings, httpx.MockTransport(upstream))
    with TestClient(app) as client:
        preview = client.get(
            "/api/v1/assistant/context", params={"source_kind": "run", "source_id": "run_fixture"}
        ).json()
        assert preview["data"]["top_genes"][0]["predicted_delta"] == -1
        assert "历史结果" in preview["data"]["expression_contract"]
        body = connection().model_dump(mode="json") | {
            "api_key": "secret-key",
            "source_kind": "run",
            "source_id": "run_fixture",
            "context_sha256": "a" * 64,
        }
        assert client.post("/api/v1/assistant/interpret", json=body).status_code == 409
        assert not calls
        body["context_sha256"] = preview["context_sha256"]
        response = client.post("/api/v1/assistant/interpret", json=body)
        assert response.status_code == 200 and response.json()["context_sha256"] == preview["context_sha256"]
        assert calls[0]["messages"][0]["role"] == "system"
        assert "不等于" in calls[0]["messages"][0]["content"]
        # Interpretations never mutate source files or the run record.
        assert json.loads((root / "summary.json").read_text()) == docs["summary.json"]
        assert store.get("run_fixture").status == RunStatus.COMPLETED
        (root / "summary.json").write_text("{}")
        assert (
            client.get(
                "/api/v1/assistant/context", params={"source_kind": "run", "source_id": "run_fixture"}
            ).status_code
            == 409
        )


def test_local_origin_requires_explicit_deployer_configuration():
    default = AssistantService(Settings(_env_file=None))
    with pytest.raises(HTTPException):
        default.endpoint("http://127.0.0.1:11434/v1")
    local = AssistantService(Settings(_env_file=None, assistant_extra_origins="http://127.0.0.1:11434"))
    assert local.endpoint("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434/v1/chat/completions"
    with pytest.raises(HTTPException):
        local.endpoint("http://127.0.0.1:8000/v1")
