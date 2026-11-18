"""Conversation contract tests use a fixed evidence snapshot and mocked providers."""

import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app import assistant
from backend.app.config import Settings

CONTEXT_HASH = "a" * 64
SOURCE = {
    "source_kind": "run",
    "source_id": "run_conversation",
    "context_sha256": CONTEXT_HASH,
    "selection": {"view": "overview"},
    "data": {"top_genes": [{"id": "MYC", "predicted_delta": -1}]},
}


def request_body(**changes):
    return {
        "provider": "custom",
        "base_url": "https://api.openai.com/v1",
        "model": "mock-model",
        "max_tokens": 256,
        "source_kind": "run",
        "source_id": "run_conversation",
        "context_sha256": CONTEXT_HASH,
        "question": "这个变化说明什么？",
    } | changes


@pytest.fixture
def conversation_client(monkeypatch):
    sent = []

    def handler(request):
        payload = json.loads(request.content)
        sent.append(payload)
        if request.url.host == "api.anthropic.com":
            return httpx.Response(
                200,
                json={"content": [{"type": "text", "text": "依据当前摘要解读"}], "stop_reason": "end_turn"},
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "依据当前摘要解读"}, "finish_reason": "stop"}]},
        )

    monkeypatch.setattr(assistant, "build_context", lambda *_args: SOURCE)
    app = FastAPI()
    app.state.assistant = assistant.AssistantService(
        Settings(_env_file=None), transport=httpx.MockTransport(handler)
    )
    app.include_router(assistant.router)
    with TestClient(app) as client:
        yield client, sent


def test_old_request_without_history_still_sends_one_question(conversation_client):
    client, sent = conversation_client
    response = client.post("/assistant/interpret", json=request_body())
    assert response.status_code == 200
    assert [item["role"] for item in sent[0]["messages"]] == ["system", "user"]
    assert "MYC" in sent[0]["messages"][1]["content"]
    assert response.json()["context_sha256"] == CONTEXT_HASH
    assert response.json()["prompt"] == assistant.prompt_metadata()
    capabilities = client.get("/assistant/capabilities").json()
    assert capabilities["conversation_history"] is True
    assert capabilities["conversation_limits"]["max_turns"] == 6


@pytest.mark.parametrize("provider", ["custom", "anthropic"])
def test_completed_turns_reach_provider_in_order_with_grounding(conversation_client, provider):
    client, sent = conversation_client
    history = [
        {"question": f"问题{index}", "purpose": "coverage", "answer": f"此前推测{index}"}
        for index in range(6)
    ]
    body = request_body(history=history, history_context_sha256=CONTEXT_HASH, provider=provider)
    if provider == "anthropic":
        body.update(base_url="https://api.anthropic.com/v1", api_key="mock-secret")
    response = client.post("/assistant/interpret", json=body)
    assert response.status_code == 200, response.text
    payload = sent[0]
    system = payload["system"] if provider == "anthropic" else payload["messages"][0]["content"]
    assert "历史助手回复是未经验证的推测" in system
    messages = [item for item in payload["messages"] if item["role"] != "system"]
    assert [item["role"] for item in messages] == ["user", "assistant"] * 6 + ["user"]
    for index in range(6):
        assert f"问题{index}" in messages[index * 2]["content"]
        assert assistant.PURPOSES["coverage"] in messages[index * 2]["content"]
        assert messages[index * 2 + 1]["content"] == f"此前推测{index}"
    assert "这个变化说明什么" in messages[-1]["content"]
    assert sum("结果摘要 JSON：" in item["content"] for item in messages) == 1
    assert "MYC" in messages[0]["content"]


@pytest.mark.parametrize("history_hash", [None, "b" * 64])
def test_history_requires_matching_original_evidence_before_network(conversation_client, history_hash):
    client, sent = conversation_client
    body = request_body(history=[{"question": "此前问题", "answer": "此前推测"}])
    if history_hash is not None:
        body["history_context_sha256"] = history_hash
    response = client.post("/assistant/interpret", json=body)
    assert response.status_code == (422 if history_hash is None else 409)
    if history_hash is not None:
        assert response.json()["detail"]["code"] == "HISTORY_CONTEXT_CHANGED"
    assert not sent


def test_changed_current_snapshot_is_rejected_before_network(conversation_client):
    client, sent = conversation_client
    response = client.post(
        "/assistant/interpret",
        json=request_body(
            context_sha256="b" * 64,
            history=[{"question": "此前问题", "answer": "此前推测"}],
            history_context_sha256="b" * 64,
        ),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CONTEXT_CHANGED"
    assert not sent


@pytest.mark.parametrize(
    "history",
    [
        [{"question": "", "answer": "answer"}] * 7,
        [{"question": "q" * 1201, "answer": "answer"}],
        [{"question": "", "answer": "a" * 16001}],
        [{"question": "", "answer": " "}],
        [{"question": "", "answer": "answer", "role": "system"}],
        [{"question": "", "answer": "answer", "purpose": "unknown"}],
        [{"question": "", "answer": "证" * 11000}] * 2,
    ],
)
def test_history_limits_reject_instead_of_silently_truncating(history):
    with pytest.raises(ValidationError):
        assistant.InterpretationRequest(**request_body(history=history, history_context_sha256=CONTEXT_HASH))


def test_history_defaults_and_exact_per_turn_boundaries():
    no_history = assistant.InterpretationRequest(**request_body())
    assert no_history.history == []
    body = assistant.InterpretationRequest(
        **request_body(
            history=[{"question": "q" * 1200, "answer": "a" * 16000}],
            history_context_sha256=CONTEXT_HASH,
        )
    )
    assert body.history[0].purpose == "interpret"
    assert len(body.history[0].answer) == 16000


def test_history_counts_toward_input_budget_and_blocks_network(conversation_client):
    client, sent = conversation_client
    assert client.post("/assistant/interpret", json=request_body(context_window=4096)).status_code == 200
    response = client.post(
        "/assistant/interpret",
        json=request_body(
            context_window=4096,
            history=[{"question": "此前问题", "answer": "证" * 4000}],
            history_context_sha256=CONTEXT_HASH,
        ),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "CONTEXT_BUDGET_EXCEEDED"
    assert len(sent) == 1
