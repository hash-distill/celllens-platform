import json
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.app.core.run_manifest import file_sha256
from backend.app.services.controlled_import import capabilities
from backend.app.services.measured_trace import measured_task_evidence


@pytest.fixture
def frozen(tmp_path):
    directory = tmp_path / "data/derived/measured/measured_fixture"
    directory.mkdir(parents=True)
    pd.DataFrame([{"gene": "A", "control": 0, "observed": 2, "observed_delta": 2}]).to_csv(
        directory / "genes.csv", index=False
    )
    pd.DataFrame(
        [{"task": "folding", "control": 0, "observed": 1, "observed_delta": 1, "gene_fraction": 0.5}]
    ).to_csv(directory / "tasks.csv", index=False)
    pd.DataFrame([{"reaction": "r1", "control": 0, "observed": 1, "observed_delta": 1}]).to_csv(
        directory / "reactions.csv", index=False
    )
    database = tmp_path / "data/registry/sccellfie/human"
    database.mkdir(parents=True)
    assets = {
        "Task-Info.csv": "Task,System,Subsystem\nfolding,Processing in the ER,Folding\n",
        "Task_by_Gene.csv": "Task,A,B\nfolding,1,1\n",
        "Task_by_Rxn.csv": "Task,r1,r2\nfolding,1,1\n",
        "Rxn_by_Gene.csv": "Reaction,A,B\nr1,1,1\nr2,0,1\n",
        "Rxn-Info-Recon2-2.json": json.dumps(
            [{"Reaction": "r1", "GPR-symbol": "A and B"}, {"Reaction": "r2", "GPR-symbol": "B"}]
        ),
    }
    for name, text in assets.items():
        (database / name).write_text(text, encoding="utf-8")
    files = {name: file_sha256(database / name) for name in assets}
    (database / "manifest.json").write_text(
        json.dumps({"version": "frozen-v1", "files": files}), encoding="utf-8"
    )
    summary = {
        "analysis_id": "measured_fixture",
        "expression_units": "mean(log1p(CP10K))",
        "metabolism": {
            "available": True,
            "units": "expression support",
            "database_version": "frozen-v1",
            "database_provenance": {
                "manifest_sha256": file_sha256(database / "manifest.json"),
                "files": files,
            },
        },
    }
    return tmp_path, directory, database, summary


def test_read_only_trace_keeps_zero_missing_and_knowledge_distinct(frozen):
    root, directory, _, summary = frozen
    before = {path: file_sha256(path) for path in root.rglob("*") if path.is_file()}
    trace = measured_task_evidence(root, directory, summary, "folding")
    assert trace["coverage"] == {"present": 1, "total": 2, "missing": ["B"]}
    assert trace["task"]["category"] == "Processing in the ER"
    assert trace["genes"][0]["control"] == 0
    assert trace["genes"][1]["control"] is None and trace["genes"][1]["present"] is False
    assert trace["reactions"][0]["gene_rule"] == "A and B"
    assert trace["reactions"][1]["control"] is None
    assert trace["source_kind"] == "measured" and trace["relationship_kind"] == "knowledge_association"
    assert {path: file_sha256(path) for path in root.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("change", ["asset", "manifest", "version", "missing_fingerprint"])
def test_trace_refuses_different_or_unrecorded_knowledge(frozen, change):
    root, directory, database, summary = frozen
    if change == "asset":
        (database / "Task_by_Gene.csv").write_text("Task,A,B\nfolding,1,0\n")
    elif change == "manifest":
        (database / "manifest.json").write_text("{}")
    elif change == "version":
        summary["metabolism"]["database_version"] = "different"
    else:
        summary["metabolism"]["database_provenance"]["files"].pop("Task_by_Rxn.csv")
    with pytest.raises(ValueError):
        measured_task_evidence(root, directory, summary, "folding")


def test_trace_never_substitutes_another_task(frozen):
    root, directory, _, summary = frozen
    with pytest.raises(KeyError):
        measured_task_evidence(root, directory, summary, "unknown")


def test_import_preparation_location_is_never_disclosed_by_public_mode(tmp_path):
    settings = SimpleNamespace(
        deployment_mode="local", controlled_import_enabled=True, controlled_import_root=tmp_path
    )
    assert capabilities(settings)["import_directory"] == str(tmp_path.resolve())
    settings.deployment_mode = "public"
    assert capabilities(settings)["import_directory"] is None
    assert capabilities(settings)["available"] is False


def test_measured_task_route_preserves_identity_and_result_fingerprint(frozen):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.app.api.measured import router

    root, directory, _, summary = frozen
    calls = []

    def verified(identifier):
        calls.append(identifier)
        return directory, summary, {}

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.container = SimpleNamespace(settings=SimpleNamespace(project_root=root))
    app.state.measured = SimpleNamespace(result=verified, store=SimpleNamespace(get=lambda _: ({}, "a" * 64)))
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/measured/analyses/measured_fixture/task-evidence", params={"task": "folding"}
        )
        assert response.status_code == 200
        assert response.json()["analysis_manifest_sha256"] == "a" * 64
        assert response.json()["genes"][0]["control"] == 0
        assert calls == ["measured_fixture"]
        assert (
            client.get(
                "/api/v1/measured/analyses/another/task-evidence", params={"task": "folding"}
            ).status_code
            == 409
        )
        assert (
            client.get(
                "/api/v1/measured/analyses/measured_fixture/task-evidence", params={"task": "unknown"}
            ).status_code
            == 404
        )
