from types import SimpleNamespace

import numpy as np
import pytest
from scipy.sparse import csr_matrix, save_npz

from backend.app.services.expression_atlas import ExpressionAtlasSpec, expression_atlas
from backend.app.services.figure_workspace import FigureWorkspace
from backend.tests.test_research_contract import frozen_measured


def fixture(tmp_path, kind="measured"):
    cells = [
        {"source": source, "cell_id": f"cell-{i:03d}"}
        for source in ("control", "observed" if kind == "measured" else "predicted")
        for i in range(21)
    ]
    matrix = np.column_stack([np.arange(42), np.zeros(42)]).astype(float)
    metadata = {"genes": ["A", "B"], "cells": cells, "units": "log1p(CP10K)"}
    path = tmp_path / "data.npz"
    if kind == "measured":
        save_npz(path, csr_matrix(matrix))
    else:
        np.savez(path, expression_control=matrix[:21], expression_predicted=matrix[21:])
    workspace = SimpleNamespace(
        source=lambda *args: ({"provenance": {"manifest_sha256": "fixture"}}, tmp_path, None, None),
        expression_metadata=lambda *args: (metadata, path),
    )
    return workspace, matrix


@pytest.mark.parametrize("kind", ["measured", "prediction"])
def test_atlas_keeps_cell_identities_and_summarizes_full_groups(tmp_path, kind):
    workspace, matrix = fixture(tmp_path, kind)
    result = expression_atlas(
        workspace, kind, "record", ExpressionAtlasSpec(genes=["B", "A"], cells_per_group=10)
    )
    assert result["genes"] == ["B", "A"]
    assert len(result["cells"]) == 20
    assert result["groups"][0]["count"] == 21
    assert result["groups"][0]["genes"][1]["mean"] == matrix[:21, 0].mean()
    assert result["groups"][0]["genes"][1]["positive_fraction"] == 20 / 21
    assert result["groups"][0]["genes"][0]["positive_fraction"] == 0
    assert result["cells"][0]["values"] == [0, 0]
    assert result["cells"][9]["cell_id"] == "cell-020"
    assert result["sampling"]["summary_population"] == "all-frozen-cells"
    assert result == expression_atlas(
        workspace, kind, "record", ExpressionAtlasSpec(genes=["B", "A"], cells_per_group=10)
    )


def test_atlas_rejects_unknown_genes_and_missing_expression(tmp_path):
    workspace, _ = fixture(tmp_path)
    with pytest.raises(ValueError, match="面板"):
        expression_atlas(workspace, "measured", "r", ExpressionAtlasSpec(genes=["UNKNOWN"]))
    workspace.expression_metadata = lambda *args: (None, None)
    with pytest.raises(ValueError, match="历史"):
        expression_atlas(workspace, "measured", "r", ExpressionAtlasSpec(genes=["A"]))


def test_atlas_uses_verified_frozen_sources(tmp_path):
    container, identifier, directory = frozen_measured(tmp_path)
    workspace = FigureWorkspace(container)
    result = expression_atlas(workspace, "measured", identifier, ExpressionAtlasSpec(genes=["ALDOA"]))
    assert result["record_id"] == identifier
    assert result["provenance"]["manifest_sha256"]
    with (directory / "genes.csv").open("a") as stream:
        stream.write("changed")
    with pytest.raises(ValueError):
        expression_atlas(workspace, "measured", identifier, ExpressionAtlasSpec(genes=["ALDOA"]))


def test_chart_assistant_receives_full_distribution_not_only_mean(tmp_path):
    from backend.app.assistant import ContextSelection, build_context, interpretation_messages

    container, identifier, directory = frozen_measured(tmp_path)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(container=container)))
    selection = ContextSelection(view="chart", chart_type="distribution", feature_id="ALDOA")
    result = build_context(request, "measured", identifier, selection)
    assert "data/" not in str(result["data"])
    chart = result["data"]["expression_chart"]
    observed = next(g for g in chart["groups"] if g["source"] == "observed")
    assert observed["count"] == 2
    assert observed["mean"] == observed["median"] == 3
    assert observed["q25"] == 2.5 and observed["q75"] == 3.5
    assert "cells" not in chart and "values" not in str(chart)
    assert "橙线是中位数" in interpretation_messages(result, "figure", "如何读图")[1]["content"]
    other = build_context(
        request,
        "measured",
        identifier,
        ContextSelection(view="chart", chart_type="dotplot", feature_id="ALDOA"),
    )
    assert other["context_sha256"] != result["context_sha256"]
    with (directory / "genes.csv").open("a") as stream:
        stream.write("changed")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        build_context(request, "measured", identifier, selection)
    assert exc.value.status_code == 409


def test_expression_summary_returns_all_genes_with_verified_identity(tmp_path):
    import json

    from fastapi import HTTPException

    from backend.app.api.figures import expression_summary

    container, identifier, directory = frozen_measured(tmp_path)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(container=container)))
    response = expression_summary(identifier, request)
    data = json.loads(response.body)
    assert data["record_id"] == identifier
    assert data["total"] == len(data["items"]) == 4
    assert {row["gene"] for row in data["items"]} == {"ALDOA", "CUSTOM1", "CUSTOM2", "GAPDH"}
    with (directory / "genes.csv").open("a") as stream:
        stream.write("changed")
    with pytest.raises(HTTPException):
        expression_summary(identifier, request)


def test_distribution_interpretation_routes_verified_statistics_and_rejects_changed_selection(tmp_path):
    # This is a protocol test with a recorder, not a real model quality evaluation.
    import asyncio

    from fastapi import HTTPException

    from backend.app.assistant import ContextSelection, InterpretationRequest, build_context, interpret

    container, identifier, _ = frozen_measured(tmp_path)
    calls = []

    async def complete(connection, messages):
        calls.append(messages)
        return {"text": "protocol fixture only"}

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(container=container, assistant=SimpleNamespace(complete=complete))
        )
    )
    selection = ContextSelection(view="chart", chart_type="distribution", feature_id="ALDOA")
    preview = build_context(request, "measured", identifier, selection)
    body = InterpretationRequest(
        source_kind="measured",
        source_id=identifier,
        context_sha256=preview["context_sha256"],
        purpose="figure",
        base_url="https://example.test",
        model="fixture",
        api_key="test-not-a-key",
        question="橙线是均值吗？",
        **selection.model_dump(),
    )
    response = asyncio.run(interpret(body, request))
    assert response["selection"]["chart_type"] == "distribution"
    assert "中位数" in calls[0][1]["content"] and '"q25": 2.5' in calls[0][1]["content"]
    assert "test-not-a-key" not in str(calls)
    changed = body.model_copy(update={"chart_type": "dotplot"})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(interpret(changed, request))
    assert exc.value.status_code == 409 and len(calls) == 1
