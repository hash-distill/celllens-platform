"""Authoritative figure context and user questions; provider responses are protocol fixtures."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.assistant import AssistantService
from backend.app.config import Settings
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.main import create_app
from backend.app.schemas import CreateRunRequest, RunStatus


@pytest.fixture
def assistant_client(tmp_path, monkeypatch):
    registry = tmp_path / "data/registry"
    registry.mkdir(parents=True)
    for name in ("models", "datasets"):
        (registry / f"{name}.json").write_text(json.dumps({name: []}))
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        database_url=f"sqlite+pysqlite:///{tmp_path / 'assistant.db'}",
        create_database_schema=True,
    )
    app = create_app(settings)
    store = app.state.container.store
    store.create("run_figure", CreateRunRequest(cell_line="K562", perturbation="MYC"))
    root = settings.derived_root / "run_figure"
    root.mkdir(parents=True)
    for name, document in {
        "summary.json": {
            "cell_line": "K562",
            "perturbation": "MYC",
            "top_genes": [{"id": "ORIGINAL_GENE", "control": 100, "predicted": 900, "predicted_delta": 800}],
            "metabolic_tasks": [
                {"id": "ORIGINAL_TASK", "control": 500, "predicted": 900, "predicted_delta": 400}
            ],
            "result_kind": "frozen_model_result",
        },
        "manifest.json": {
            "assets": {},
            "source_type": "online",
            "request": {"cell_line": "K562", "perturbation": "MYC"},
        },
    }.items():
        path = root / name
        path.write_text(json.dumps(document))
        store.register_artifact(
            "run_figure",
            name,
            f"run_figure/{name}",
            file_sha256(path),
            path.stat().st_size,
            "application/json",
        )
    store.transition("run_figure", RunStatus.COMPLETED, 100)
    calls, figure_calls = [], []
    stats = {
        "n": 12,
        "n_valid": 12,
        "n_displayed": 8,
        "mean": 2.0,
        "median": 1.5,
        "q25": 1.0,
        "q75": 3.0,
        "ecdf": [[1, 0.5]],
    }

    def figure(run_id, request, feature_kind, feature_id, embedding, space):
        figure_calls.append((run_id, feature_kind, feature_id, embedding, space))
        return {
            "method": "joint-umap" if embedding == "umap" else "control-reference-pca",
            "embedding_space": space,
            "fit_source": "joint" if embedding == "umap" else "control",
            "feature": {"kind": feature_kind, "id": feature_id or "MYC", "units": "log1p(CP10K)"},
            "gene_count": 2000,
            "explained_variance_ratio": [] if embedding == "umap" else [0.25, 0.12],
            "embedding_parameters": {"n_neighbors": 15, "min_dist": 0.3, "random_state": 42},
            "embedding_preprocessing": {"feature_count": 2000, "feature_ids": ["PRIVATE_GENE"]},
            "distributions": {
                "control": stats,
                "predicted": stats | {"mean": 1.0},
                "observed": stats | {"mean": 1.8},
            },
            "total_cells": 36,
            "displayed_cells": 24,
            "points": [{"cell_id": "PRIVATE_CELL", "x": 999, "y": 999}],
            "provenance": {"manifest_sha256": "a" * 64},
            "limitations": ["Unpaired populations; no significance test."],
        }

    monkeypatch.setattr("backend.app.assistant._cell_state", figure, raising=False)

    async def upstream(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "图表解读协议模拟"}, "finish_reason": "stop"}]}
        )

    app.state.assistant = AssistantService(settings, httpx.MockTransport(upstream))
    with TestClient(app) as client:
        yield client, calls, figure_calls, stats


def params(**changes):
    return {
        "source_kind": "run",
        "source_id": "run_figure",
        "view": "chart",
        "embedding": "pca",
        "space": "expression",
        "feature_kind": "gene",
        "feature_id": "MYC",
    } | changes


def body(preview, **changes):
    return {
        "base_url": "https://api.openai.com/v1",
        "model": "fixture",
        "api_key": "fixture-key",
        "source_kind": "run",
        "source_id": "run_figure",
        "purpose": "figure",
        "context_sha256": preview["context_sha256"],
        **preview["selection"],
    } | changes


@pytest.mark.parametrize("embedding", ["pca", "umap"])
@pytest.mark.parametrize(
    "space,kind,feature", [("expression", "gene", "MYC"), ("metabolic", "task", "task 1")]
)
def test_figure_summary_is_selected_bounded_and_rechecked(assistant_client, embedding, space, kind, feature):
    client, calls, figure_calls, stats = assistant_client
    query = params(embedding=embedding, space=space, feature_kind=kind, feature_id=feature)
    response = client.get("/api/v1/assistant/context", params=query)
    assert response.status_code == 200
    preview = response.json()
    chart = preview["data"]["figure"]
    assert chart["feature"]["id"] == feature
    assert chart["distributions"]["predicted"]["mean_delta_vs_control"] == -1.0
    assert chart["distributions"]["observed"]["mean_delta_vs_control"] == pytest.approx(-0.2)
    assert chart["embedding_space"] == space
    assert chart["displayed_cells"] == 24
    assert figure_calls[-1] == ("run_figure", kind, feature, embedding, space)
    serialized = json.dumps(preview)
    for private in ("PRIVATE_CELL", "PRIVATE_GENE", '"points"', '"ecdf"'):
        assert private not in serialized
    assert not calls  # Preview never calls a provider.
    response = client.post("/api/v1/assistant/interpret", json=body(preview, question="为什么预测均值下降？"))
    assert response.status_code == 200
    assert response.json()["question"] == "为什么预测均值下降？"
    messages = calls[-1]["messages"]
    assert "为什么预测均值下降" in messages[-1]["content"]
    assert "PCA" in messages[0]["content"] and "UMAP" in messages[0]["content"]
    assert "图像" in messages[0]["content"]
    assert response.json()["selection"] == preview["selection"]
    before = len(calls)
    stats["mean"] = 2.5
    assert client.post("/api/v1/assistant/interpret", json=body(preview)).status_code == 409
    assert len(calls) == before


def test_selected_method_and_feature_are_part_of_context_identity(assistant_client):
    client, calls, _, _ = assistant_client
    preview = client.get("/api/v1/assistant/context", params=params()).json()
    for changes in ({"embedding": "umap"}, {"feature_id": "ALDOA"}, {"view": "overview"}):
        assert client.post("/api/v1/assistant/interpret", json=body(preview, **changes)).status_code == 409
    assert not calls


def test_questions_and_selections_are_validated_before_network(assistant_client):
    client, calls, _, _ = assistant_client
    preview = client.get("/api/v1/assistant/context", params=params()).json()
    for changes in (
        {"question": "a" * 1201},
        {"view": "arbitrary"},
        {"embedding": "tsne"},
        {"feature_id": "a" * 501},
        {"data": {"invented": 9}},
    ):
        response = client.post("/api/v1/assistant/interpret", json=body(preview, **changes))
        assert response.status_code == 422
        assert "fixture-key" not in response.text
    assert not calls


@pytest.mark.parametrize("purpose", ["genes", "metabolism"])
def test_data_purposes_work_without_loading_a_figure(assistant_client, purpose):
    client, calls, figure_calls, _ = assistant_client
    preview = client.get("/api/v1/assistant/context", params=params(view=purpose)).json()
    assert "figure" not in preview["data"]
    assert not figure_calls
    assert client.post("/api/v1/assistant/interpret", json=body(preview, purpose=purpose)).status_code == 200
    assert calls


@pytest.fixture
def matched_comparison(assistant_client):
    client, _, _, _ = assistant_client
    root = client.app.state.container.settings.project_root
    directory = root / "data/derived/comparisons/run_figure"
    directory.mkdir(parents=True)
    report = {
        "status": "available",
        "run_id": "run_figure",
        "cell_line": "K562",
        "perturbation": "MYC",
        "units": {"expression": "mean(log1p(CP10K))", "tasks": "expression-derived scCellFie score"},
        "population_matching": {
            "common_batches": ["matched-batch"],
            "cells": {"control": 8, "predicted": 7, "observed": 6},
        },
        "genes": [
            {
                "id": f"MATCHED_{index}",
                "control": 2,
                "predicted": 2 + (-index if index % 2 == 0 else index),
                "observed": 3,
                "predicted_delta": -index if index % 2 == 0 else index,
                "observed_delta": 1,
            }
            for index in range(25)
        ],
        "tasks": [
            {
                "id": "MATCHED_TASK",
                "control": 1,
                "predicted": 2,
                "observed": 4,
                "predicted_delta": 1,
                "observed_delta": 3,
            }
        ],
    }
    atomic_write_json(directory / "comparison.json", report)
    atomic_write_json(
        directory / "manifest.json",
        {
            "run_id": "run_figure",
            "source_manifest_sha256": file_sha256(root / "data/derived/runs/run_figure/manifest.json"),
            "inputs": {},
            "outputs": {"comparison.json": file_sha256(directory / "comparison.json")},
        },
    )
    return directory, report


def test_comparison_context_uses_only_matched_rows_and_population(assistant_client, matched_comparison):
    client, calls, figure_calls, _ = assistant_client
    _, report = matched_comparison
    response = client.get("/api/v1/assistant/context", params=params(view="comparison"))
    assert response.status_code == 200, response.text
    context = response.json()
    genes = context["data"]["top_genes"]
    assert len(genes) == 20 and genes[0]["id"] == "MATCHED_24" and genes[-1]["id"] == "MATCHED_5"
    assert genes[0]["control"] == 2 and genes[0]["predicted"] == -22 and genes[0]["observed"] == 3
    assert context["data"]["metabolic_tasks"] == report["tasks"]
    assert context["data"]["population_matching"] == report["population_matching"]
    assert context["data"]["units"] == report["units"]
    assert "匹配" in context["scope"] and "原实验" in context["scope"]
    assert "ORIGINAL_" not in json.dumps(context) and not figure_calls
    assert (
        client.post("/api/v1/assistant/interpret", json=body(context, purpose="comparison")).status_code
        == 200
    )
    assert "MATCHED_TASK" in calls[-1]["messages"][-1]["content"]
    assert "ORIGINAL_" not in calls[-1]["messages"][-1]["content"]
    overview = client.get("/api/v1/assistant/context", params=params(view="overview")).json()
    assert overview["data"]["top_genes"][0]["predicted"] == 900
    chart = client.get("/api/v1/assistant/context", params=params(view="chart")).json()
    assert chart["data"]["top_genes"][0]["id"] == "ORIGINAL_GENE"


def test_comparison_context_requires_verified_comparison(assistant_client):
    client, calls, _, _ = assistant_client
    response = client.get("/api/v1/assistant/context", params=params(view="comparison"))
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "COMPARISON_UNAVAILABLE"
    assert not calls


def test_comparison_context_rejects_tampered_rows_before_network(assistant_client, matched_comparison):
    client, calls, _, _ = assistant_client
    directory, report = matched_comparison
    context = client.get("/api/v1/assistant/context", params=params(view="comparison")).json()
    report["genes"][0]["observed"] = 999
    atomic_write_json(directory / "comparison.json", report)
    response = client.post("/api/v1/assistant/interpret", json=body(context, purpose="comparison"))
    assert response.status_code == 409 and not calls


@pytest.mark.parametrize("table,key", [("genes", "top_genes"), ("tasks", "metabolic_tasks")])
def test_comparison_missing_rows_never_fall_back_to_original(
    assistant_client, matched_comparison, table, key
):
    client, _, _, _ = assistant_client
    directory, report = matched_comparison
    report[table] = []
    atomic_write_json(directory / "comparison.json", report)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["outputs"]["comparison.json"] = file_sha256(directory / "comparison.json")
    atomic_write_json(directory / "manifest.json", manifest)
    response = client.get("/api/v1/assistant/context", params=params(view="comparison"))
    assert response.status_code == 200, response.text
    assert response.json()["data"][key] == []
