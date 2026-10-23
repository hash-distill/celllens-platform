import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.assistant import AssistantService
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.tests.test_measured_api import make_app, wait_completed


@pytest.fixture
def measured_context(tmp_path, monkeypatch):
    app, groups = make_app(tmp_path, monkeypatch)
    calls = []

    async def upstream(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "受控测试回复"}}]})

    app.state.assistant = AssistantService(app.state.container.settings, httpx.MockTransport(upstream))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/measured/analyses", json={"cell_line": "K562", "perturbation": "ALDOA"}
        )
        identifier = response.json()["id"]
        wait_completed(client, identifier)
        yield client, app, identifier, tmp_path / "data/derived/measured" / identifier, groups, calls


def preview(client, identifier, **selection):
    return client.get(
        "/api/v1/assistant/context",
        params={"source_kind": "measured", "source_id": identifier, **selection},
    )


def interpretation(identifier, digest, **selection):
    return {
        "source_kind": "measured",
        "source_id": identifier,
        "context_sha256": digest,
        "base_url": "https://api.openai.com/v1",
        "api_key": "fixture-secret",
        "model": "fixture-model",
        **selection,
    }


def refreeze(app, identifier, directory):
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["files"] = {name: file_sha256(directory / name) for name in manifest["files"]}
    atomic_write_json(path, manifest)
    app.state.measured.store.update(identifier, manifest_sha256=file_sha256(path))


def test_measured_context_has_real_group_values_units_and_no_prediction(measured_context):
    client, _, identifier, _, _, calls = measured_context
    response = preview(client, identifier)
    assert response.status_code == 200, response.text
    context = response.json()
    assert context["source_kind"] == "measured" and context["source_id"] == identifier
    data = context["data"]
    assert data["counts"] == {"control": 3, "observed": 2}
    assert data["expression_units"] == "mean(log1p(CP10K))"
    aldoa = next(row for row in data["top_genes"] if row["gene"] == "ALDOA")
    assert aldoa == {"gene": "ALDOA", "control": 2.0, "observed": 3.0, "observed_delta": 1.0}
    assert "predicted" not in json.dumps(data) and "figure" not in data
    assert data["metabolism"]["available"] is False
    assert "scCellFie" in " ".join(data["limitations"])
    assert "manifest.json" in context["artifact_sha256"]
    reply = client.post(
        "/api/v1/assistant/interpret", json=interpretation(identifier, context["context_sha256"])
    )
    assert reply.status_code == 200, reply.text
    assert len(calls) == 1 and identifier in calls[0]["messages"][1]["content"]
    assert "inputs/observed.h5ad" not in json.dumps(calls)


@pytest.mark.parametrize(
    "source_kind,source_id",
    [
        ("run", "measured_" + "a" * 24),
        ("measured", "run_fixture"),
        ("measured", "measured_short"),
        ("measured", "measured_" + "A" * 24),
    ],
)
def test_source_kind_must_match_identifier_in_get_and_post(measured_context, source_kind, source_id):
    client, _, _, _, _, calls = measured_context
    assert (
        client.get(
            "/api/v1/assistant/context",
            params={
                "source_kind": source_kind,
                "source_id": source_id,
            },
        ).status_code
        == 422
    )
    body = interpretation(source_id, "a" * 64) | {"source_kind": source_kind}
    assert client.post("/api/v1/assistant/interpret", json=body).status_code == 422
    assert not calls


@pytest.mark.parametrize("target", ["summary", "input", "manifest"])
def test_measured_tampering_is_rejected_before_network(measured_context, target):
    client, _, identifier, directory, groups, calls = measured_context
    initial = preview(client, identifier)
    assert initial.status_code == 200, initial.text
    path = {
        "summary": directory / "summary.json",
        "input": Path(groups["groups"]["observed"]["path"]),
        "manifest": directory / "manifest.json",
    }[target]
    with path.open("ab") as stream:
        stream.write(b"changed")
    assert preview(client, identifier).status_code == 409
    assert (
        client.post(
            "/api/v1/assistant/interpret",
            json=interpretation(
                identifier,
                initial.json()["context_sha256"],
            ),
        ).status_code
        == 409
    )
    assert not calls


@pytest.mark.parametrize("field,value", [("analysis_id", "measured_" + "f" * 24), ("source_kind", "run")])
def test_registered_but_misidentified_summary_is_rejected(measured_context, field, value):
    client, app, identifier, directory, _, calls = measured_context
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    summary[field] = value
    atomic_write_json(directory / "summary.json", summary)
    refreeze(app, identifier, directory)
    response = preview(client, identifier)
    assert response.status_code == 409, response.text
    assert not calls


def test_selected_gene_reads_full_table_and_selection_changes_context_hash(measured_context):
    client, app, identifier, directory, _, calls = measured_context
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    summary["top_genes"] = []
    atomic_write_json(directory / "summary.json", summary)
    refreeze(app, identifier, directory)
    first = preview(client, identifier, view="genes", feature_kind="gene", feature_id="ALDOA")
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert data["top_genes"] == []
    assert data["selected_feature"]["row"]["observed_delta"] == 1.0
    assert data["selected_feature"]["source"] == "genes.csv"
    second = preview(client, identifier, view="genes", feature_kind="gene", feature_id="GAPDH")
    assert second.status_code == 200
    assert second.json()["context_sha256"] != first.json()["context_sha256"]
    reply = client.post(
        "/api/v1/assistant/interpret",
        json=interpretation(
            identifier,
            first.json()["context_sha256"],
            view="genes",
            feature_kind="gene",
            feature_id="GAPDH",
        ),
    )
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "CONTEXT_CHANGED"
    assert not calls
    missing = preview(client, identifier, view="genes", feature_kind="gene", feature_id="ALD")
    assert missing.status_code == 422
    task = preview(client, identifier, view="metabolism", feature_kind="task", feature_id="task-1")
    assert task.status_code == 422


@pytest.mark.parametrize("view", ["chart", "comparison"])
def test_measured_context_does_not_claim_unsupported_views(measured_context, view):
    client, _, identifier, _, _, calls = measured_context
    response = preview(client, identifier, view=view)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "UNSUPPORTED_SELECTION"
    assert not calls


def test_measured_context_rejects_incomplete_result_and_unknown_id(measured_context):
    client, app, identifier, _, _, calls = measured_context
    assert preview(client, "measured_" + "f" * 24).status_code == 404
    app.state.measured.store.update(identifier, status="failed")
    assert preview(client, identifier).status_code == 409
    assert not calls


@pytest.mark.parametrize("purpose", ["figure", "comparison"])
def test_measured_interpret_rejects_unsupported_purpose_before_network(measured_context, purpose):
    client, _, identifier, _, _, calls = measured_context
    context = preview(client, identifier)
    assert context.status_code == 200, context.text
    response = client.post(
        "/api/v1/assistant/interpret",
        json=interpretation(identifier, context.json()["context_sha256"], purpose=purpose),
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "UNSUPPORTED_PURPOSE"
    assert not calls


@pytest.mark.parametrize("dependency", ["source_reference", "analysis_assets"])
def test_measured_context_verifies_dependencies_beyond_summary(measured_context, dependency):
    client, app, identifier, directory, _, calls = measured_context
    asset = app.state.container.settings.project_root / "fixture-dependency.json"
    asset.write_text('{"version":1}', encoding="utf-8")
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if dependency == "source_reference":
        manifest["inputs"]["groups"]["observed"]["source_reference"] = {
            "path": asset.name,
            "sha256": file_sha256(asset),
        }
    else:
        manifest["inputs"]["analysis_assets"] = {asset.name: file_sha256(asset)}
    atomic_write_json(path, manifest)
    app.state.measured.store.update(identifier, manifest_sha256=file_sha256(path))
    initial = preview(client, identifier)
    assert initial.status_code == 200, initial.text
    asset.write_text('{"version":2}', encoding="utf-8")
    response = client.post(
        "/api/v1/assistant/interpret", json=interpretation(identifier, initial.json()["context_sha256"])
    )
    assert response.status_code == 409 and not calls


def test_selected_task_retains_scores_coverage_and_expression_derived_units(measured_context):
    client, app, identifier, directory, _, _ = measured_context
    (directory / "tasks.csv").write_text(
        "task,label,control,observed,observed_delta,gene_fraction,missing_genes\n"
        "fixture-task,Synthetic test task,2,1,-1,0.5,GENE2\n",
        encoding="utf-8",
    )
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["files"]["tasks.csv"] = file_sha256(directory / "tasks.csv")
    atomic_write_json(path, manifest)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    summary["metabolism"] = {
        "available": True,
        "units": "expression-derived scCellFie task/reaction support score",
        "top_tasks": [],
        "coverage": {"available_metabolic_genes": 1, "database_metabolic_genes": 2},
    }
    atomic_write_json(directory / "summary.json", summary)
    refreeze(app, identifier, directory)
    response = preview(client, identifier, view="metabolism", feature_kind="task", feature_id="fixture-task")
    assert response.status_code == 200, response.text
    selected = response.json()["data"]["selected_feature"]
    assert selected["source"] == "tasks.csv" and selected["id"] == "fixture-task"
    assert selected["row"]["observed_delta"] == -1 and selected["row"]["gene_fraction"] == 0.5
    assert selected["row"]["missing_genes"] == "GENE2"
    assert "expression-derived" in selected["units"]


def test_refrozen_artifact_invalidates_previous_measured_preview(measured_context):
    client, app, identifier, directory, _, calls = measured_context
    first = preview(client, identifier)
    assert first.status_code == 200, first.text
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    summary["warnings"].append("fixture revision")
    atomic_write_json(directory / "summary.json", summary)
    refreeze(app, identifier, directory)
    second = preview(client, identifier)
    assert second.status_code == 200
    assert first.json()["context_sha256"] != second.json()["context_sha256"]
    response = client.post(
        "/api/v1/assistant/interpret", json=interpretation(identifier, first.json()["context_sha256"])
    )
    assert response.status_code == 409 and response.json()["detail"]["code"] == "CONTEXT_CHANGED"
    assert not calls
