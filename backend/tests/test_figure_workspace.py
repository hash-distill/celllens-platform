"""Figure export tests use explicitly synthetic, tiny fixtures, not biological validation."""

from __future__ import annotations

import base64
import csv
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.figure_workspace import (
    FigureSpec,
    FigureWorkspace,
    csv_bytes,
    export_payload,
    validate_expression_metadata,
)
from backend.app.services.measured_store import MeasuredStore
from backend.tests.test_research_contract import frozen_measured, prediction_container


def read_csv(content):
    return list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))


def test_long_figure_caption_retains_final_interpretation_in_pdf_and_svg(tmp_path):
    container, identifier, _ = frozen_measured(tmp_path)
    note = "Descriptive evidence only. " * 40 + "FINAL_BOUNDARY_NOT_CAUSAL"
    payload = FigureWorkspace(container).payload(
        "measured", identifier, FigureSpec(chart="distribution", gene="ALDOA", note=note)
    )
    svg = export_payload(payload, "svg").decode()
    assert "FINAL_BOUNDARY_NOT_CAUSAL" in svg
    pdf = PdfReader(io.BytesIO(export_payload(payload, "pdf")))
    assert "FINAL_BOUNDARY_NOT_CAUSAL" in pdf.pages[0].extract_text()
    assert float(pdf.pages[0].mediabox.height) > 6.2 * 72


def reseal(container, identifier, directory):
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["files"] = {
        item.relative_to(directory).as_posix(): file_sha256(item)
        for item in directory.rglob("*")
        if item.is_file() and item.name != "manifest.json"
    }
    atomic_write_json(path, manifest)
    MeasuredStore(container.store.session_factory).update(identifier, manifest_sha256=file_sha256(path))


def test_all_export_formats_read_back_same_frozen_distribution(tmp_path):
    container, identifier, directory = frozen_measured(tmp_path)
    before = {path.name: file_sha256(path) for path in directory.iterdir() if path.is_file()}
    workspace = FigureWorkspace(container)
    spec = FigureSpec(chart="distribution", gene="ALDOA", group="observed", title="Synthetic fixture")
    payload = workspace.payload("measured", identifier, spec)
    assert [row["value"] for row in payload["rows"]] == [4, 2]
    assert {row["source"] for row in payload["rows"]} == {"observed"}
    outputs = {
        format: export_payload(payload, format) for format in ("svg", "png", "pdf", "csv", "html", "zip")
    }
    svg = ET.fromstring(outputs["svg"])
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    collections = [
        g for g in svg.findall(".//svg:g", namespace) if g.attrib.get("id", "").startswith("PathCollection")
    ]
    assert sum(len(g.findall(".//svg:use", namespace)) for g in collections) == 2
    with Image.open(io.BytesIO(outputs["png"])) as image:
        assert image.size == (1800, 1116)
        image.verify()
    pdf = PdfReader(io.BytesIO(outputs["pdf"]))
    assert len(pdf.pages) == 1
    assert "Synthetic fixture" in pdf.pages[0].extract_text()
    csv_rows = read_csv(outputs["csv"])
    assert [float(row["value"]) for row in csv_rows] == [4, 2]
    html = outputs["html"].decode()
    encoded_csv = re.search(r'data:text/csv;base64,([^" ]+)', html).group(1)
    encoded_recipe = re.search(r'data:application/json;base64,([^" ]+)', html).group(1)
    assert base64.b64decode(encoded_csv) == outputs["csv"]
    assert json.loads(base64.b64decode(encoded_recipe)) == payload
    with zipfile.ZipFile(io.BytesIO(outputs["zip"])) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {
            "index.html",
            "figure.svg",
            "figure.png",
            "figure.pdf",
            "figure-data.csv",
            "figure-recipe.json",
            "README.txt",
        }
        assert archive.read("figure-data.csv") == outputs["csv"]
        assert json.loads(archive.read("figure-recipe.json")) == payload
        ET.fromstring(archive.read("figure.svg"))
        assert len(PdfReader(io.BytesIO(archive.read("figure.pdf"))).pages) == 1
    assert before == {path.name: file_sha256(path) for path in directory.iterdir() if path.is_file()}


def test_saved_recipes_persist_and_reject_changed_result_or_plot_data(tmp_path, monkeypatch):
    container, identifier, directory = frozen_measured(tmp_path)
    workspace = FigureWorkspace(container)
    spec = FigureSpec(chart="distribution", gene="ALDOA")
    saved = workspace.save("measured", identifier, spec)
    assert len(saved["figure_source_sha256"]) == 64
    assert FigureWorkspace(container).saved("measured", identifier)["items"][0] == saved
    assert (
        workspace.saved_payload("measured", identifier, saved["id"])["figure_source_sha256"]
        == saved["figure_source_sha256"]
    )
    original = workspace.payload

    def changed_rows(*args):
        payload = original(*args)
        # Simulate a separately registered prepared bundle whose original result
        # fingerprint stays unchanged; saved plot-data fingerprint must still reject it.
        payload["figure_source_sha256"] = "f" * 64
        return payload

    monkeypatch.setattr(workspace, "payload", changed_rows)
    with pytest.raises(ValueError, match="图表数据指纹"):
        workspace.saved_payload("measured", identifier, saved["id"])
    monkeypatch.setattr(workspace, "payload", original)
    metadata = json.loads((directory / "expression_preview.json").read_text())
    metadata["cells"][0]["cell_id"] = "renamed-but-resealed-fixture"
    atomic_write_json(directory / "expression_preview.json", metadata)
    reseal(container, identifier, directory)
    with pytest.raises(ValueError, match="结果指纹"):
        workspace.saved_payload("measured", identifier, saved["id"])
    with pytest.raises(KeyError):
        workspace.saved_payload("prediction", identifier, saved["id"])


def test_context_and_export_reads_never_compute_or_mutate(tmp_path, monkeypatch):
    from backend.app.services import cell_state, pathway_analysis

    container, identifier, directory = frozen_measured(tmp_path)
    before = {path.name: file_sha256(path) for path in directory.iterdir() if path.is_file()}

    def forbidden(*args, **kwargs):
        pytest.fail("Figure reads must never fit, reconstruct or run ORA")

    for name in ("reference_pca", "joint_umap", "_reconstruct", "cell_state_document"):
        monkeypatch.setattr(cell_state, name, forbidden)
    monkeypatch.setattr(pathway_analysis, "analyze_pathways", forbidden)
    workspace = FigureWorkspace(container)
    context = workspace.context("measured", identifier)
    assert context["availability"] == {"projection": True, "distribution": True, "pathways": False}
    payload = workspace.payload("measured", identifier, FigureSpec(chart="projection", group="control"))
    assert len(payload["rows"]) == 3
    assert {row["source"] for row in payload["rows"]} == {"control"}
    export_payload(payload, "svg")
    assert before == {path.name: file_sha256(path) for path in directory.iterdir() if path.is_file()}
    (directory / "expression_preview.npz").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="变化"):
        workspace.context("measured", identifier)


def test_historical_missing_artifacts_are_unavailable_without_backfill(tmp_path):
    container, identifier, directory = prediction_container(tmp_path)
    before = {path.name: file_sha256(path) for path in directory.iterdir() if path.is_file()}
    workspace = FigureWorkspace(container)
    context = workspace.context("prediction", identifier)
    assert not any(context["availability"].values())
    assert context["genes"] == ["ALDOA"]
    with pytest.raises(ValueError, match="逐细胞表达"):
        workspace.payload("prediction", identifier, FigureSpec(chart="distribution", gene="ALDOA"))
    assert before == {path.name: file_sha256(path) for path in directory.iterdir() if path.is_file()}


def test_unregistered_prediction_pathways_cannot_be_presented_as_frozen_evidence(tmp_path):
    container, identifier, directory = prediction_container(tmp_path)
    workspace = FigureWorkspace(container)
    original = workspace.context("prediction", identifier)
    atomic_write_json(
        directory / "pathways.json",
        {
            "status": "complete",
            "results": [
                {
                    "pathway_id": "R-HSA-UNREGISTERED",
                    "pathway_name": "Unregistered fixture",
                    "direction": "up",
                    "hit_count": 1,
                    "fdr": 0.01,
                    "p_value": 0.001,
                }
            ],
        },
    )
    context = workspace.context("prediction", identifier)
    assert (
        context["result"]["provenance"]["manifest_sha256"]
        == original["result"]["provenance"]["manifest_sha256"]
    )
    assert not context["availability"]["pathways"]
    assert "经登记" in context["reasons"]["pathways"]
    assert "pathways.json" not in context["result"]["provenance"]["files"]
    with pytest.raises(ValueError, match="预测结果尚未接入经登记"):
        workspace.payload("prediction", identifier, FigureSpec(chart="pathways"))
    with pytest.raises(ValueError, match="预测结果尚未接入经登记"):
        workspace.save("prediction", identifier, FigureSpec(chart="pathways"))


@pytest.mark.parametrize(
    "change",
    ["unknown_source", "predicted_in_measured", "duplicate_cell", "duplicate_gene", "bounds", "units"],
)
def test_metadata_identity_validation(change):
    metadata = {
        "genes": ["ALDOA"],
        "cells": [{"cell_id": "one", "source": "control"}],
        "units": "log1p(CP10K)",
    }
    if change == "unknown_source":
        metadata["cells"][0]["source"] = "unknown"
    elif change == "predicted_in_measured":
        metadata["cells"][0]["source"] = "predicted"
    elif change == "duplicate_cell":
        metadata["cells"].append(dict(metadata["cells"][0]))
    elif change == "duplicate_gene":
        metadata["genes"].append("ALDOA")
    elif change == "bounds":
        metadata["genes"] = [f"G{i}" for i in range(60001)]
    else:
        metadata["units"] = "unknown"
    with pytest.raises(ValueError):
        validate_expression_metadata(metadata, "measured")


def test_html_svg_escape_injection_and_csv_formula_text(tmp_path):
    container, identifier, _ = frozen_measured(tmp_path)
    malicious = '<script>alert("x")</script><img src=x onerror=alert(1)>'
    payload = FigureWorkspace(container).payload(
        "measured",
        identifier,
        FigureSpec(
            chart="distribution", gene="ALDOA", title=malicious, note=malicious + r" $\notamathcommand$"
        ),
    )
    payload["rows"][0]["cell_id"] = ' \t=HYPERLINK("https://bad.example")'
    payload["rows"][1]["cell_id"] = "+cmd"
    payload["spec"]["gene"] = r"$\notamathcommand$"  # Source identifiers are literal labels too.
    payload["rows"][2]["value"] = -2.0  # Real numeric negatives remain numeric.
    rows = read_csv(csv_bytes(payload))
    assert rows[0]["cell_id"].startswith("'") and rows[1]["cell_id"] == "'+cmd"
    assert float(rows[2]["value"]) == -2
    html = export_payload(payload, "html").decode()
    assert "<script>" not in html and "<img src=x" not in html
    assert "&lt;script&gt;" in html
    assert not re.search(r'(?:src|href)="https?://', html)
    root = ET.fromstring(export_payload(payload, "svg"))
    assert all(not element.tag.endswith("script") for element in root.iter())


def test_pathways_export_uses_exact_selected_sorted_rows(tmp_path):
    container, identifier, directory = frozen_measured(tmp_path)
    rows = [
        {
            "pathway_id": f"R-HSA-{i}",
            "pathway_name": f"Synthetic pathway {i}",
            "direction": direction,
            "hit_count": hits,
            "p_value": fdr / 2,
            "fdr": fdr,
            "hit_genes": ["ALDOA"],
        }
        for i, direction, hits, fdr in [
            (1, "up", 2, 0.1),
            (2, "down", 1, 0),
            (3, "up", 0, 1),
            (4, "up", 3, 0.01),
        ]
    ]
    atomic_write_json(
        directory / "pathways.json",
        {"status": "complete", "results": rows, "parameters": {"multiple_testing": "both directions"}},
    )
    reseal(container, identifier, directory)
    payload = FigureWorkspace(container).payload(
        "measured", identifier, FigureSpec(chart="pathways", direction="up", limit=1)
    )
    assert [row["pathway_id"] for row in payload["rows"]] == ["R-HSA-4"]
    assert payload["pathway_analysis"]["parameters"]["multiple_testing"] == "both directions"
    assert len(read_csv(export_payload(payload, "csv"))) == 1
    ET.fromstring(export_payload(payload, "svg"))


def test_private_figure_routes_require_auth_and_cross_site_posts_are_blocked(tmp_path, monkeypatch):
    from backend.app.main import create_app
    from backend.tests.test_api_runs import _settings, _write_registry

    _write_registry(tmp_path)
    app = create_app(
        _settings(tmp_path, worker_enabled=False, deployment_mode="private", workspace_token="fixture-token")
    )
    monkeypatch.setattr(FigureWorkspace, "context", lambda *args: {"fixture": True})
    base = "/api/v1/figures/measured/measured_" + "a" * 24
    with TestClient(app) as client:
        assert client.get(base + "/context").status_code == 401
        assert client.get(base + "/saved").status_code == 401
        assert client.post(base + "/render", json={}).status_code == 401
        authorized = {"Authorization": "Bearer fixture-token"}
        assert client.get(base + "/context", headers=authorized).json() == {"fixture": True}
        response = client.post(
            base + "/saved", json={}, headers=authorized | {"Origin": "https://elsewhere.test"}
        )
        assert response.status_code == 403
        app.state.container.settings.deployment_mode = "public"
        app.state.container.settings.public_result_ids = "measured_" + "a" * 24
        assert client.get(base + "/context").status_code == 403
        assert client.get(base + "/saved/figure_test/export").status_code == 403


def test_prediction_reads_prepared_expression_only_and_saved_hash_tracks_bundle(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import numpy as np

    from backend.app.services import cell_state
    from backend.tests.test_cell_state import fixture_container
    from backend.tests.test_research_contract import container_at

    container, directory, registrations = fixture_container(tmp_path)
    container.settings.api_prefix = "/api/v1"
    container.store.session_factory = container_at(tmp_path / "database").store.session_factory
    prepared = directory / "cell_state"
    prepared.mkdir()
    source_hash = file_sha256(directory / "manifest.json")
    metadata = {
        "genes": ["MYC", "ENO1", "ENO2"],
        "ids": ["c0", "c1", "c2", "c3", "p0", "p2"],
        "sources": ["control"] * 4 + ["predicted"] * 2,
    }
    prepared_artifact = SimpleNamespace(
        kind="cell_state_preparation", relative_path="run_cells/cell_state/prepared.json", sha256=""
    )
    registrations["run_cells"].append(prepared_artifact)

    def write_prepared(value):
        np.savez_compressed(
            prepared / "plot_data.npz",
            metadata=json.dumps(metadata),
            expression_control=np.array([[0, 1, 3], [2, 4, 1], [3, 2, 6], [1, 4, 5]]),
            expression_predicted=np.array([[value, 2, 4], [3, 4, 6]]),
        )
        atomic_write_json(
            prepared / "prepared.json",
            {
                "schema_version": 1,
                "run_id": "run_cells",
                "source_manifest_sha256": source_hash,
                "figures": {},
                "unavailable": {"expression": "No frozen projection in this fixture"},
                "outputs": {"plot_data.npz": file_sha256(prepared / "plot_data.npz")},
            },
        )
        prepared_artifact.sha256 = file_sha256(prepared / "prepared.json")

    write_prepared(2)
    workspace = FigureWorkspace(container)
    # Isolate distribution provenance from projection availability: no projection
    # fingerprint exists, while the independently registered plot bundle does.
    result = {
        "state": "completed",
        "availability": {"projection": {"available": False}},
        "provenance": {"manifest_sha256": source_hash},
        "limitations": [],
    }
    monkeypatch.setattr(workspace, "source", lambda *args: (result, directory, {}, {}))

    def forbidden(*args, **kwargs):
        pytest.fail("Prediction figures may read prepared arrays only")

    for name in ("_reconstruct", "reference_pca", "joint_umap", "cell_state_document"):
        monkeypatch.setattr(cell_state, name, forbidden)
    spec = FigureSpec(chart="distribution", gene="MYC", group="predicted")
    payload = workspace.payload("prediction", "run_cells", spec)
    assert [row["value"] for row in payload["rows"]] == [2, 3]
    saved = workspace.save("prediction", "run_cells", spec)
    write_prepared(9)  # Re-sealed fixture preserves original result fingerprint.
    with pytest.raises(ValueError, match="图表数据指纹"):
        workspace.saved_payload("prediction", "run_cells", saved["id"])
    with (prepared / "plot_data.npz").open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="missing or changed"):
        workspace.payload("prediction", "run_cells", spec)


def test_multi_figure_report_contains_all_saved_rows_full_notes_and_provenance(tmp_path):
    import html as html_module

    from backend.app.services.figure_workspace import export_report

    container, identifier, directory = frozen_measured(tmp_path)
    workspace = FigureWorkspace(container)
    note = '<script>alert("fixture")</script>\n' + "Full note content. " * 60
    specs = [
        FigureSpec(chart="projection", group="control", title="Control projection", note=note),
        FigureSpec(chart="distribution", gene="ALDOA", group="observed", title="Treatment distribution"),
    ]
    for spec in specs:
        workspace.save("measured", identifier, spec)
    before = {item.name: file_sha256(item) for item in directory.iterdir() if item.is_file()}
    html = export_report(container, "measured", identifier, "html").decode()
    assert html.count("<!doctype html>") == 1 and html.count("<html ") == 1
    assert html.count('<section id="figure-') == 2
    assert html_module.escape(note) in html and "<script>" not in html
    images = re.findall(r'<img[^>]+src="data:image/svg\+xml;base64,([^\"]+)"', html)
    assert len(images) == 2
    for image in images:
        ET.fromstring(base64.b64decode(image))
    with zipfile.ZipFile(io.BytesIO(export_report(container, "measured", identifier, "zip"))) as archive:
        assert archive.testzip() is None
        assert {
            "index.html",
            "report-manifest.json",
            "figures/01.svg",
            "figures/01.csv",
            "figures/01.json",
            "figures/02.svg",
            "figures/02.csv",
            "figures/02.json",
        } <= set(archive.namelist())
        manifest = json.loads(archive.read("report-manifest.json"))
        assert manifest["figure_count"] == 2 and manifest["result"]["provenance"]["manifest_sha256"]
        assert manifest["limitations"]
        for number, saved in enumerate(workspace.saved("measured", identifier)["items"], 1):
            expected = workspace.saved_payload("measured", identifier, saved["id"])
            recipe = json.loads(archive.read(f"figures/{number:02d}.json"))
            assert recipe["rows"] == expected["rows"]
            assert recipe["saved_figure"]["id"] == saved["id"]
            assert archive.read(f"figures/{number:02d}.csv") == csv_bytes(expected)
            match = re.search(rf'download="{number:02d}.csv" href="data:text/csv;base64,([^\"]+)"', html)
            assert base64.b64decode(match.group(1)) == csv_bytes(expected)
    assert before == {item.name: file_sha256(item) for item in directory.iterdir() if item.is_file()}


def test_multi_figure_report_rejects_empty_oversized_and_changed_lists(tmp_path, monkeypatch):
    from backend.app.services.figure_workspace import export_report

    container, identifier, directory = frozen_measured(tmp_path)
    workspace = FigureWorkspace(container)
    with pytest.raises(ValueError, match="尚未保存"):
        export_report(container, "measured", identifier, "html")
    saved = workspace.save("measured", identifier, FigureSpec(chart="distribution", gene="ALDOA"))
    original_saved = FigureWorkspace.saved
    monkeypatch.setattr(FigureWorkspace, "saved", lambda *args: {"items": [saved] * 21, "total": 21})
    with pytest.raises(ValueError, match="20"):
        export_report(container, "measured", identifier, "html")
    monkeypatch.setattr(FigureWorkspace, "saved", original_saved)
    metadata = json.loads((directory / "expression_preview.json").read_text())
    metadata["cells"][0]["cell_id"] = "changed-resealed-report-fixture"
    atomic_write_json(directory / "expression_preview.json", metadata)
    reseal(container, identifier, directory)
    with pytest.raises(ValueError, match="结果指纹"):
        export_report(container, "measured", identifier, "zip")


def test_report_api_formats_headers_and_private_access(tmp_path, monkeypatch):
    from backend.app.main import create_app
    from backend.tests.test_api_runs import _settings, _write_registry

    _write_registry(tmp_path)
    app = create_app(
        _settings(tmp_path, worker_enabled=False, deployment_mode="private", workspace_token="fixture-token")
    )
    calls = []

    def fake_report(container, kind, identifier, format):
        calls.append((kind, identifier, format))
        return b"offline report fixture"

    monkeypatch.setattr("backend.app.api.figures.export_report", fake_report)
    base = "/api/v1/figures/measured/measured_" + "a" * 24 + "/report"
    with TestClient(app) as client:
        assert client.get(base).status_code == 401
        authorized = {"Authorization": "Bearer fixture-token"}
        for format in ("html", "zip"):
            reply = client.get(base, params={"format": format}, headers=authorized)
            assert reply.status_code == 200 and reply.content == b"offline report fixture"
            assert reply.headers["cache-control"] == "no-store"
            assert reply.headers["content-disposition"].endswith(f'celllens-report.{format}"')
            assert reply.headers["x-content-type-options"] == "nosniff"
        assert [call[2] for call in calls] == ["html", "zip"]
        assert client.get(base, params={"format": "pdf"}, headers=authorized).status_code == 422
        app.state.container.settings.deployment_mode = "public"
        app.state.container.settings.public_result_ids = "measured_" + "a" * 24
        assert client.get(base).status_code == 403


def test_delete_recipe_scopes_record_checks_access_and_preserves_analysis(tmp_path, monkeypatch):
    from backend.tests.test_measured_api import make_app, wait_completed

    app, _ = make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        identifiers = []
        for _ in range(2):
            reply = client.post(
                "/api/v1/measured/analyses", json={"cell_line": "K562", "perturbation": "ALDOA"}
            )
            identifier = reply.json()["id"]
            wait_completed(client, identifier)
            identifiers.append(identifier)
        workspace = FigureWorkspace(app.state.container)
        saved = workspace.save("measured", identifiers[0], FigureSpec(chart="distribution", gene="ALDOA"))
        directory = tmp_path / "data/derived/measured" / identifiers[0]
        before = {
            item.relative_to(directory).as_posix(): file_sha256(item)
            for item in directory.rglob("*")
            if item.is_file()
        }
        route = f"/api/v1/figures/measured/{identifiers[0]}/saved/{saved['id']}"
        settings = app.state.container.settings
        settings.deployment_mode = "private"
        settings.workspace_token = "fixture-token"
        authorized = {"Authorization": "Bearer fixture-token"}
        assert client.delete(route).status_code == 401
        assert (
            client.delete(route, headers=authorized | {"Origin": "https://elsewhere.test"}).status_code == 403
        )
        settings.deployment_mode = "public"
        settings.public_result_ids = identifiers[0]
        assert client.delete(route, headers=authorized).status_code == 403
        settings.deployment_mode = "private"
        other = f"/api/v1/figures/measured/{identifiers[1]}/saved/{saved['id']}"
        assert client.delete(other, headers=authorized).status_code == 404
        assert workspace.saved("measured", identifiers[0])["total"] == 1
        response = client.delete(route, headers=authorized)
        assert response.status_code == 204 and response.content == b""
        assert response.headers["cache-control"] == "no-store"
        assert workspace.saved("measured", identifiers[0])["total"] == 0
        assert client.delete(route, headers=authorized).status_code == 404
        assert before == {
            item.relative_to(directory).as_posix(): file_sha256(item)
            for item in directory.rglob("*")
            if item.is_file()
        }


def test_delete_recipe_requires_verified_source(tmp_path):
    from backend.app.db.research_models import ResearchFigureModel

    container, identifier, directory = frozen_measured(tmp_path)
    workspace = FigureWorkspace(container)
    saved = workspace.save("measured", identifier, FigureSpec(chart="distribution", gene="ALDOA"))
    with (directory / "genes.csv").open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="变化"):
        workspace.remove("measured", identifier, saved["id"])
    with container.store.session_factory() as session:
        assert session.get(ResearchFigureModel, saved["id"]) is not None
