"""Connection settings: controlled upstreams, no real credentials or paid requests."""

import json

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.assistant import AssistantService, Connection, DiscoveryConnection
from backend.app.config import Settings


def credentials(**changes):
    return dict(provider="openai", base_url="https://api.openai.com/v1", api_key="test-private-key") | changes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message,finish_reason,code,expected",
    [
        (
            {"content": None, "reasoning_content": "private upstream reasoning"},
            "length",
            "OUTPUT_BUDGET_EXHAUSTED",
            "思考阶段",
        ),
        ({"content": "  "}, "length", "OUTPUT_BUDGET_EXHAUSTED", "2,048"),
        (
            {"content": None, "reasoning_content": "private upstream reasoning"},
            "stop",
            "REASONING_ONLY_COMPLETION",
            "正式解读",
        ),
        ({"content": None}, "content_filter", "UPSTREAM_REFUSED", "拒绝"),
        ({"content": None, "refusal": "private refusal"}, "stop", "UPSTREAM_REFUSED", "拒绝"),
        ({"content": None}, "tool_calls", "UNSUPPORTED_COMPLETION", "工具调用"),
        ({"content": None}, "stop", "EMPTY_COMPLETION", "空正文"),
    ],
)
async def test_empty_answers_explain_actual_finish_without_exposing_reasoning(
    message, finish_reason, code, expected
):
    calls = []

    async def upstream(request):
        calls.append(request)
        return httpx.Response(
            200, json={"choices": [{"message": message, "finish_reason": finish_reason}]}
        )

    service = AssistantService(Settings(_env_file=None), httpx.MockTransport(upstream))
    conn = Connection(
        **credentials(provider="deepseek", base_url="https://api.deepseek.com"),
        model="chosen",
        max_tokens=2048,
    )
    with pytest.raises(HTTPException) as error:
        await service.complete(conn, [{"role": "user", "content": "解读实测结果"}])
    assert error.value.detail["code"] == code
    assert expected in error.value.detail["message"]
    assert "private" not in str(error.value.detail)
    assert "test-private-key" not in str(error.value.detail)
    assert len(calls) == 1 and service.pending == 0


@pytest.mark.asyncio
async def test_reasoning_is_not_used_instead_of_final_answer():
    async def upstream(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "最终解读", "reasoning_content": "private reasoning"},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    service = AssistantService(Settings(_env_file=None), httpx.MockTransport(upstream))
    result = await service.complete(Connection(**credentials(), model="chosen"), [])
    assert result["text"] == "最终解读"
    assert "private reasoning" not in json.dumps(result)


@pytest.mark.asyncio
async def test_model_default_allows_long_reasoning_without_discarding_final_answer():
    async def upstream(request):
        payload = json.loads(request.content)
        assert "max_tokens" not in payload and "max_completion_tokens" not in payload
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "最终科研解读", "reasoning_content": "r" * 200_000},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    service = AssistantService(Settings(_env_file=None), httpx.MockTransport(upstream))
    conn = Connection(
        **credentials(provider="deepseek", base_url="https://api.deepseek.com"), model="chosen"
    )
    result = await service.complete(conn, [{"role": "user", "content": "科研摘要"}])
    assert result["text"] == "最终科研解读"
    assert "reasoning_content" not in result
    assert service.pending == 0


@pytest.mark.asyncio
async def test_oversized_model_reply_is_still_rejected_without_retry():
    calls = []

    async def upstream(request):
        calls.append(request)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "x" * 8_000_000}, "finish_reason": "stop"}]}
        )

    service = AssistantService(Settings(_env_file=None), httpx.MockTransport(upstream))
    with pytest.raises(HTTPException) as error:
        await service.complete(Connection(**credentials(), model="chosen"), [])
    assert error.value.detail["code"] == "UPSTREAM_TOO_LARGE"
    assert len(calls) == 1 and service.pending == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "deepseek", "gemini", "siliconflow", "custom"])
async def test_default_lengths_are_omitted_from_upstream_request(provider):
    from backend.app.assistant import PROVIDER_CONFIG

    async def upstream(request):
        payload = json.loads(request.content)
        assert "max_tokens" not in payload and "max_completion_tokens" not in payload
        assert "context_window" not in payload
        return httpx.Response(200, json={"choices": [{"message": {"content": "默认长度解读"}}]})

    service = AssistantService(Settings(_env_file=None), httpx.MockTransport(upstream))
    conn = Connection(
        **credentials(provider=provider, base_url=PROVIDER_CONFIG[provider]["base_url"] or "https://api.openai.com/v1"),
        model="chosen",
    )
    assert conn.max_tokens is None and conn.context_window is None
    result = await service.complete(conn, [{"role": "user", "content": "科研摘要"}])
    assert result["text"] == "默认长度解读" and result["context_window"] is None


@pytest.mark.asyncio
async def test_claude_default_output_uses_declared_model_limit():
    calls = []

    async def upstream(request):
        calls.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "chosen", "max_tokens": 64000}]})
        assert json.loads(request.content)["max_tokens"] == 64000
        return httpx.Response(200, json={"content": [{"type": "text", "text": "解读"}]})

    service = AssistantService(Settings(_env_file=None), httpx.MockTransport(upstream))
    conn = Connection(
        **credentials(provider="anthropic", base_url="https://api.anthropic.com/v1"), model="chosen"
    )
    assert (await service.complete(conn, []))["text"] == "解读"
    assert calls == ["GET", "POST"]


@pytest.mark.asyncio
async def test_claude_missing_declared_limit_does_not_guess_or_generate():
    async def upstream(request):
        assert request.method == "GET"
        return httpx.Response(200, json={"data": [{"id": "chosen"}]})

    service = AssistantService(Settings(_env_file=None), httpx.MockTransport(upstream))
    conn = Connection(
        **credentials(provider="anthropic", base_url="https://api.anthropic.com/v1"), model="chosen"
    )
    with pytest.raises(HTTPException) as error:
        await service.complete(conn, [])
    assert error.value.detail["code"] == "OUTPUT_LIMIT_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
async def test_discovery_protocol_pagination_and_metadata(provider):
    urls = {
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    }
    calls = []

    async def upstream(request):
        calls.append(request)
        assert request.method == "GET" and request.url.path.endswith("/models")
        header = "x-api-key" if provider == "anthropic" else "authorization"
        assert "test-private-key" in request.headers[header]
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "text-a", "display_name": "Text A", "context_window": 64000},
                        {"id": "test-private-key"},
                        {"id": "bad\nmodel"},
                    ],
                    "has_more": True,
                    "last_id": "text-a",
                },
            )
        assert request.url.params["after_id" if provider == "anthropic" else "after"] == "text-a"
        return httpx.Response(200, json={"data": [{"id": "text-b"}, {"id": "text-a"}]})

    service = AssistantService(Settings(_env_file=None), httpx.MockTransport(upstream))
    result = await service.models(
        DiscoveryConnection(**credentials(provider=provider, base_url=urls[provider]))
    )
    assert [model["id"] for model in result["models"]] == ["text-a", "text-b"]
    assert result["models"][0]["context_window"] == 64000
    assert "context_window" not in result["models"][1]
    assert "test-private-key" not in json.dumps(result)
    assert not result["truncated"] and service.pending == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["redirect", "error", "invalid", "large", "timeout"])
async def test_discovery_failures_are_bounded_and_redacted(mode):
    async def upstream(request):
        if mode == "timeout":
            raise httpx.ReadTimeout("test-private-key")
        if mode == "redirect":
            return httpx.Response(302, headers={"location": "https://evil.test"})
        if mode == "error":
            return httpx.Response(401, text="test-private-key")
        if mode == "large":
            return httpx.Response(200, content=b"a" * 600000)
        return httpx.Response(200, json={"data": "test-private-key"})

    service = AssistantService(Settings(_env_file=None), httpx.MockTransport(upstream))
    with pytest.raises(HTTPException) as error:
        await service.models(DiscoveryConnection(**credentials()))
    assert "test-private-key" not in str(error.value.detail) and service.pending == 0


@pytest.mark.asyncio
async def test_discovery_rejects_address_before_sending_key():
    async def upstream(request):
        pytest.fail("Rejected origin must not receive credentials")

    service = AssistantService(Settings(_env_file=None), httpx.MockTransport(upstream))
    with pytest.raises(HTTPException):
        await service.models(DiscoveryConnection(**credentials(base_url="https://evil.test/v1")))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,options,expected",
    [
        ("openai", {"reasoning_effort": "high"}, {"reasoning_effort": "high"}),
        ("gemini", {"reasoning_effort": "low"}, {"reasoning_effort": "low"}),
        ("deepseek", {"reasoning_effort": "none"}, {"thinking": {"type": "disabled"}}),
        (
            "deepseek",
            {"reasoning_effort": "max"},
            {"thinking": {"type": "enabled"}, "reasoning_effort": "max"},
        ),
        (
            "anthropic",
            {"thinking_mode": "enabled", "thinking_budget": 1024},
            {"thinking": {"type": "enabled", "budget_tokens": 1024}},
        ),
        (
            "anthropic",
            {"thinking_mode": "adaptive", "reasoning_effort": "high"},
            {"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}},
        ),
    ],
)
async def test_provider_specific_options_reach_actual_payload(provider, options, expected):
    from backend.app.assistant import PROVIDER_CONFIG

    async def upstream(request):
        payload = json.loads(request.content)
        for name, value in expected.items():
            assert payload[name] == value
        if provider == "anthropic":
            assert "reasoning_effort" not in payload
            return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})
        assert "thinking_mode" not in payload and "context_window" not in payload
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    service = AssistantService(Settings(_env_file=None), httpx.MockTransport(upstream))
    conn = Connection(
        **credentials(provider=provider, base_url=PROVIDER_CONFIG[provider]["base_url"]),
        model="chosen",
        max_tokens=2048,
        **options,
    )
    await service.complete(conn, [{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_budget_rejects_before_network_without_truncating_evidence():
    async def upstream(request):
        pytest.fail("Context budget must be checked before contacting provider")

    service = AssistantService(Settings(_env_file=None), httpx.MockTransport(upstream))
    conn = Connection(**credentials(), model="chosen", context_window=4096)
    with pytest.raises(HTTPException) as error:
        await service.complete(conn, [{"role": "user", "content": "实验数据" * 3000}])
    assert error.value.detail["code"] == "CONTEXT_BUDGET_EXCEEDED"


@pytest.mark.parametrize(
    "changes",
    [
        {"provider": "siliconflow", "reasoning_effort": "high"},
        {"provider": "gemini", "reasoning_effort": "max"},
        {"provider": "deepseek", "reasoning_effort": "medium"},
        {"provider": "openai", "thinking_mode": "enabled"},
        {"provider": "anthropic", "thinking_mode": "enabled", "thinking_budget": 2048, "max_tokens": 2048},
        {"provider": "anthropic", "reasoning_effort": "high"},
        {"context_window": 1024},
        {"max_tokens": 4096, "context_window": 4096},
    ],
)
def test_invalid_parameter_combinations_rejected(changes):
    with pytest.raises(ValidationError):
        Connection(**(credentials() | {"model": "chosen"} | changes))


@pytest.mark.asyncio
async def test_keyless_local_compatible_service_and_full_endpoint_normalization():
    async def upstream(request):
        assert "authorization" not in request.headers
        assert request.url == "http://127.0.0.1:11434/v1/chat/completions"
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})

    service = AssistantService(
        Settings(_env_file=None, assistant_extra_origins="http://127.0.0.1:11434"),
        httpx.MockTransport(upstream),
    )
    conn = Connection(
        provider="custom", base_url="http://127.0.0.1:11434/v1/chat/completions", model="local", api_key=""
    )
    assert (await service.complete(conn, []))["text"] == "hello"
