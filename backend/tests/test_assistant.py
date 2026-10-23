import json

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.assistant import AssistantService, Connection
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
        connection(token_parameter=token_parameter, max_tokens=2048), [{"role": "user", "content": "data"}]
    )
    assert result["text"] == "辅助解读" and result["finish_reason"] == "length"
    assert "secret-key" not in json.dumps(result)


@pytest.mark.asyncio
async def test_gemini_uses_official_compatible_endpoint_and_budget():
    async def handler(request):
        assert request.url == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        assert request.headers["authorization"] == "Bearer secret-key"
        body = json.loads(request.content)
        assert body["max_tokens"] == 2048 and "max_completion_tokens" not in body
        assert body["messages"][0] == {"role": "system", "content": "scientific boundary"}
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Gemini text"}, "finish_reason": "stop"}]}
        )

    result = await AssistantService(Settings(_env_file=None), httpx.MockTransport(handler)).complete(
        connection(
            provider="gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            max_tokens=2048,
        ),
        [{"role": "system", "content": "scientific boundary"}, {"role": "user", "content": "summary"}],
    )
    assert result["provider"] == "gemini" and result["text"] == "Gemini text"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason,normalized",
    [
        ("end_turn", "stop"),
        ("stop_sequence", "stop"),
        ("max_tokens", "length"),
        ("refusal", "content_filter"),
    ],
)
async def test_claude_native_headers_system_text_and_usage(reason, normalized):
    async def handler(request):
        assert request.url == "https://api.anthropic.com/v1/messages"
        assert request.headers["x-api-key"] == "secret-key"
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert "authorization" not in request.headers
        body = json.loads(request.content)
        assert body["system"] == "scientific boundary"
        assert body["messages"] == [{"role": "user", "content": "summary"}]
        assert body["max_tokens"] == 2048 and "max_completion_tokens" not in body
        assert not body["stream"] and "tools" not in body
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "thinking", "thinking": "private reasoning"},
                    {"type": "text", "text": "Claude text"},
                    {"type": "text", "text": "secret-key"},
                ],
                "stop_reason": reason,
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 4,
                    "cache_creation_input_tokens": 5,
                    "cache_read_input_tokens": 3,
                },
            },
        )

    result = await AssistantService(Settings(_env_file=None), httpx.MockTransport(handler)).complete(
        connection(provider="anthropic", base_url="https://api.anthropic.com/v1", max_tokens=2048),
        [{"role": "system", "content": "scientific boundary"}, {"role": "user", "content": "summary"}],
    )
    assert result["provider"] == "anthropic"
    assert result["text"] == "Claude text\n\n[REDACTED]"
    assert result["finish_reason"] == normalized
    assert result["usage"] == {"prompt_tokens": 28, "completion_tokens": 4, "total_tokens": 32}
    assert "private reasoning" not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,url", [("custom", "https://api.openai.com/v1"), ("anthropic", "https://api.anthropic.com/v1")]
)
@pytest.mark.parametrize("mode", ["error", "redirect", "large", "invalid", "empty", "timeout"])
async def test_upstream_errors_do_not_leak(mode, provider, url):
    async def handler(request):
        if mode == "timeout":
            raise httpx.ReadTimeout("secret-key")
        if mode == "error":
            return httpx.Response(401, text="secret-key")
        if mode == "redirect":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:8000"})
        if mode == "large":
            return httpx.Response(200, content=b"s" * 8_000_000)
        if mode == "empty":
            return httpx.Response(200, json={"choices": [{"message": {"content": None}}]})
        return httpx.Response(200, text="secret-key")

    service = AssistantService(Settings(_env_file=None), transport=httpx.MockTransport(handler))
    with pytest.raises(HTTPException) as error:
        await service.complete(connection(provider=provider, base_url=url), [])
    assert "secret-key" not in str(error.value.detail)


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
        assert client.get("/api/v1/assistant/capabilities").json()["model_default_lengths"] is True
        providers = client.get("/api/v1/assistant/capabilities").json()["providers"]
        assert {provider["id"] for provider in providers} == {
            "openai",
            "gemini",
            "anthropic",
            "deepseek",
            "siliconflow",
            "custom",
        }


@pytest.mark.parametrize("provider", ["custom", "gemini", "anthropic"])
@pytest.mark.parametrize("purpose", ["interpret", "figure", "comparison"])
def test_interpret_uses_registered_run_and_checks_preview_before_network(tmp_path, provider, purpose):
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
        response = (
            {"content": [{"type": "text", "text": "解读"}], "stop_reason": "end_turn", "usage": {}}
            if provider == "anthropic"
            else {"choices": [{"message": {"content": "解读"}, "finish_reason": "stop"}]}
        )
        return httpx.Response(200, json=response)

    app.state.assistant = AssistantService(settings, httpx.MockTransport(upstream))
    with TestClient(app) as client:
        preview = client.get(
            "/api/v1/assistant/context", params={"source_kind": "run", "source_id": "run_fixture"}
        ).json()
        assert preview["data"]["top_genes"][0]["predicted_delta"] == -1
        assert "历史结果" in preview["data"]["expression_contract"]
        assert preview["request_budget"]["system_bytes"] > 0
        assert preview["request_budget"]["user_bytes"][purpose] > 0
        urls = {
            "custom": "https://api.openai.com/v1",
            "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
            "anthropic": "https://api.anthropic.com/v1",
        }
        body = connection(
            provider=provider, base_url=urls[provider], max_tokens=2048, context_window=32768
        ).model_dump(mode="json") | {
            "api_key": "secret-key",
            "source_kind": "run",
            "source_id": "run_fixture",
            "context_sha256": "a" * 64,
            "purpose": purpose,
        }
        assert client.post("/api/v1/assistant/interpret", json=body).status_code == 409
        assert not calls
        body["context_sha256"] = preview["context_sha256"]
        response = client.post("/api/v1/assistant/interpret", json=body)
        assert response.status_code == 200 and response.json()["context_sha256"] == preview["context_sha256"]
        assert "request_budget" not in json.dumps(calls[0])
        assert response.json()["input_tokens_estimate"] + body["max_tokens"] <= body["context_window"]
        if provider == "anthropic":
            assert "不等于" in calls[0]["system"]
            assert calls[0]["messages"][0]["role"] == "user"
        else:
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


def test_provider_origin_mismatch_is_rejected_before_sending_key():
    service = AssistantService(Settings(_env_file=None))
    with pytest.raises(HTTPException) as error:
        service.endpoint("https://api.openai.com/v1", "anthropic")
    assert error.value.detail["code"] == "PROVIDER_MISMATCH"
    proxy = AssistantService(Settings(_env_file=None, assistant_extra_origins="https://models.example.org"))
    assert (
        proxy.endpoint("https://models.example.org/v1", "anthropic")
        == "https://models.example.org/v1/messages"
    )
