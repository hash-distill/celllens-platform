import json
from types import SimpleNamespace

import anndata as ad
import h5py
import numpy as np
import pandas as pd
import pytest

from backend.app.api.research import ImportRequest
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.core.storage import RunStore
from backend.app.services.controlled_import import (
    _h5_preflight,
    get_import,
    import_analysis_request,
    import_h5ad,
)
from backend.app.services.measured_results import result_directory
from backend.app.services.measured_store import MeasuredStore
from backend.app.services.measured_worker import execute_measured_job
from backend.app.services.research_findings import ResearchFindings
from backend.app.services.research_results import ResearchResults
from backend.tests.test_measured_analysis import measured_inputs


def container_at(root):
    root.mkdir(parents=True, exist_ok=True)
    settings = SimpleNamespace(
        project_root=root,
        derived_root=root / "data/derived/runs",
        api_prefix="/api/v1",
        allow_synthetic_results=False,
        controlled_import_enabled=True,
        controlled_import_root=root / "incoming",
        controlled_import_max_bytes=16 * 1024 * 1024,
    )
    store = RunStore(f"sqlite:///{(root / 'test.sqlite').as_posix()}", create_schema=True)
    return SimpleNamespace(settings=settings, store=store)


def frozen_measured(root):
    container = container_at(root)
    identifier = "measured_" + "a" * 24
    request = {"id": identifier, "cell_line": "K562", "perturbation": "ALDOA", "max_cells": 256, "seed": 42}
    inputs, _ = measured_inputs(root)
    store = MeasuredStore(container.store.session_factory)
    store.create(request)
    staging = root / "staging"
    final = result_directory(root, identifier)
    final.parent.mkdir(parents=True)
    execute_measured_job(
        root, request, staging, final, lambda *args: None, inputs=inputs, metabolism=False, compute_umap=False
    )
    store.update(
        identifier, status="completed", progress=100, manifest_sha256=file_sha256(final / "manifest.json")
    )
    return container, identifier, final


def test_measured_reader_and_persistent_findings_bind_exact_manifest(tmp_path):
    container, identifier, directory = frozen_measured(tmp_path)
    before = {path.name: file_sha256(path) for path in directory.iterdir() if path.is_file()}
    reader = ResearchResults(container)
    result = reader.read("measured", identifier)
    assert result["groups"] == [
        {"id": "control", "source_kind": "measured", "count": 3},
        {"id": "observed", "source_kind": "measured", "count": 2},
    ]
    assert result["units"]["expression"] == "mean(log1p(CP10K))"
    assert not result["availability"]["function"]["available"]
    assert not result["availability"]["comparison"]["available"]
    finding = ResearchFindings(container).create(
        "measured",
        identifier,
        {"gene_id": "ALDOA", "group_id": "observed", "projection_id": "pca"},
        "保存来源，稍后复查",
    )
    # A new service instance reads the persisted database, independent of browser state.
    findings = ResearchFindings(container_at(tmp_path)).list("measured", identifier)
    assert findings["total"] == 1
    assert findings["items"][0]["id"] == finding["id"]
    assert finding["manifest_sha256"] == result["provenance"]["manifest_sha256"]
    bundle = reader.export("measured", identifier, findings["items"])
    assert bundle["tables"]["genes.csv"]["rows"][0]["gene"] == "ALDOA"
    assert bundle["findings"][0]["matches_current_result"]
    assert before == {path.name: file_sha256(path) for path in directory.iterdir() if path.is_file()}
    with pytest.raises(ValueError, match="不属于"):
        ResearchFindings(container).create("measured", identifier, {"gene_id": "INVENTED"}, "test")
    with pytest.raises(ValueError, match="4000"):
        ResearchFindings(container).create("measured", identifier, {}, "a" * 4001)
    with (directory / "genes.csv").open("a") as handle:
        handle.write("changed")
    with pytest.raises(ValueError, match="变化"):
        reader.read("measured", identifier)


def prediction_container(root, *, contract=None, synthetic=False):
    container = container_at(root)
    identifier = "run_legacy"
    directory = container.settings.derived_root / identifier
    directory.mkdir(parents=True)
    summary = {
        "run_id": identifier,
        "top_genes": [{"id": "ALDOA", "predicted_delta": 1}],
        "metabolic_tasks": [],
        "result_kind": "synthetic_demo" if synthetic else "frozen_model_result",
    }
    atomic_write_json(directory / "summary.json", summary)
    (directory / "gene_deltas.csv").write_text("gene,control,predicted,predicted_delta\nALDOA,1,2,1\n")
    if contract:
        atomic_write_json(directory / "expression_contract.json", contract)
    record = SimpleNamespace(
        status=SimpleNamespace(value="completed"),
        warnings=[],
        request=SimpleNamespace(cell_line="K562", perturbation="ALDOA", mode="precomputed"),
    )
    container.store.get = lambda identifier: record
    container.store.artifacts = lambda identifier: []
    return container, identifier, directory


def test_historical_unknown_scale_is_not_relabelled_and_export_is_sanitized(tmp_path):
    container, identifier, directory = prediction_container(tmp_path)
    manifest = {
        "assets": {
            "control_path": "C:\\private\\input.h5ad",
            "password": "private-value",
            "source_url": "https://user:password@example.test/input",
            "control_sha256": "a" * 64,
        },
        "outputs": {"summary.json": {"sha256": file_sha256(directory / "summary.json")}},
    }
    atomic_write_json(directory / "manifest.json", manifest)
    reader = ResearchResults(container)
    result = reader.read("prediction", identifier)
    assert result["units"]["expression"] is None
    assert all(group["count"] is None for group in result["groups"])
    assert not result["availability"]["comparison"]["available"]
    bundle = reader.export("prediction", identifier, [])
    encoded = json.dumps(bundle)
    assert "private-value" not in encoded and "user:password" not in encoded
    assert "C:\\\\private" not in encoded
    assert bundle["source_manifest"]["assets"]["control_sha256"] == "a" * 64
    summary_path = directory / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary["top_genes"] = []
    atomic_write_json(summary_path, summary)
    with pytest.raises(ValueError, match="清单"):
        reader.read("prediction", identifier)


def test_synthetic_legacy_results_are_not_scientific_fallback(tmp_path):
    container, identifier, _ = prediction_container(tmp_path, synthetic=True)
    with pytest.raises(ValueError, match="合成演示"):
        ResearchResults(container).read("prediction", identifier)


def import_fixture(root, *, sparse=False, **overrides):
    from scipy import sparse as sp

    container = container_at(root)
    incoming = container.settings.controlled_import_root
    incoming.mkdir(exist_ok=True)
    matrix = np.array([[10, 90], [20, 80], [40, 60], [80, 20]], dtype=float)
    frame = ad.AnnData(
        sp.csr_matrix(matrix) if sparse else matrix,
        obs=pd.DataFrame(
            {"condition": ["CTRL", "CTRL", "KO", "KO"], "total": [1000.0] * 4},
            index=[f"cell_{i}" for i in range(4)],
        ),
        var=pd.DataFrame(index=["ALDOA", "GAPDH"]),
    )
    path = incoming / "experiment.h5ad"
    frame.write_h5ad(path)
    request = ImportRequest(
        relative_path=path.name,
        expression_scale="raw_counts",
        total_counts_key="total",
        group_key="condition",
        control_label="CTRL",
        target_label="KO",
        cell_line="Custom",
        perturbation="ALDOA",
        max_cells=256,
    ).model_dump()
    request.update(overrides)
    return container, request, path, matrix


@pytest.mark.parametrize("sparse", [False, True])
def test_import_denominator_survives_adapter_and_measured_pipeline(tmp_path, sparse):
    container, request, path, matrix = import_fixture(tmp_path, sparse=sparse)
    original = file_sha256(path)
    imported = import_h5ad(container.settings, request)
    assert imported["normalization"]["before_gene_crop"]
    assert imported["group_counts"] == {"control": 2, "observed": 2}
    assert not imported["custom_prediction_available"]
    control = ad.read_h5ad(tmp_path / imported["groups"]["control"]["path"])
    actual = control.X.toarray() if hasattr(control.X, "toarray") else control.X
    # Use 1000 full-library counts, never normalize the 100-count panel to 10K.
    np.testing.assert_allclose(actual, np.log1p(matrix[:2] * 10))
    job = import_analysis_request(tmp_path, {"import_id": imported["import_id"]})
    job["id"] = "measured_" + "b" * 24
    final = result_directory(tmp_path, job["id"])
    final.parent.mkdir(parents=True)
    summary = execute_measured_job(
        tmp_path,
        job,
        tmp_path / "analysis-stage",
        final,
        lambda *args: None,
        metabolism=False,
        compute_umap=False,
    )
    table = pd.read_csv(final / "genes.csv")
    assert summary["cell_line"] == "Custom"
    assert set(summary["counts"]) == {"control", "observed"}
    expected = np.log1p(matrix[2:] * 10).mean(0) - np.log1p(matrix[:2] * 10).mean(0)
    np.testing.assert_allclose(table["observed_delta"], expected)
    assert original == file_sha256(path)
    assert not (final / "predicted.h5ad").exists()
    frozen_source = tmp_path / "data/imports" / imported["import_id"] / "source.h5ad"
    with frozen_source.open("ab") as handle:
        handle.write(b"changed")
    with pytest.raises(ValueError, match="快照"):
        get_import(tmp_path, imported["import_id"])


@pytest.mark.parametrize(
    "change", ["duplicate", "nan", "inf", "negative", "fraction", "missing_group", "small_total"]
)
def test_import_rejects_invalid_science(tmp_path, change):
    container, request, path, _ = import_fixture(tmp_path)
    frame = ad.read_h5ad(path)
    if change == "duplicate":
        frame.var_names = ["ALDOA", "ALDOA"]
    elif change == "missing_group":
        request["target_label"] = "absent"
    elif change == "small_total":
        frame.obs["total"] = 1
    else:
        frame.X[0, 0] = {"nan": np.nan, "inf": np.inf, "negative": -1, "fraction": 0.5}[change]
    frame.write_h5ad(path)
    with pytest.raises(ValueError):
        import_h5ad(container.settings, request)
    assert not list((tmp_path / "data/imports").glob("import_*"))


def test_import_is_opt_in_confined_and_bounded(tmp_path):
    container, request, path, _ = import_fixture(tmp_path)
    request["relative_path"] = "../outside.h5ad"
    with pytest.raises(ValueError, match="越界"):
        import_h5ad(container.settings, request)
    request["relative_path"] = str(path)
    with pytest.raises(ValueError, match="相对"):
        import_h5ad(container.settings, request)
    request["relative_path"] = path.name
    container.settings.controlled_import_max_bytes = 1
    with pytest.raises(ValueError, match="大小"):
        import_h5ad(container.settings, request)
    container.settings.controlled_import_enabled = False
    with pytest.raises(ValueError, match="启用"):
        import_h5ad(container.settings, request)


def test_h5ad_external_links_and_decompression_bombs_are_rejected(tmp_path):
    linked = tmp_path / "linked.h5ad"
    with h5py.File(linked, "w") as handle:
        handle["X"] = h5py.ExternalLink("outside.h5ad", "/X")
    with pytest.raises(ValueError, match="链接"):
        _h5_preflight(linked)
    oversized = tmp_path / "oversized.h5ad"
    with h5py.File(oversized, "w") as handle:
        handle.create_dataset("X", shape=(20000, 60000), dtype="float64", chunks=True, compression="gzip")
    with pytest.raises(ValueError, match="上限"):
        _h5_preflight(oversized)


def test_research_api_roundtrip_and_input_validation(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.app.api.research import router

    container, identifier, _ = frozen_measured(tmp_path)
    app = FastAPI()
    app.state.container = container
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as client:
        url = f"/api/v1/research/results/measured/{identifier}"
        result = client.get(url)
        assert result.status_code == 200
        assert result.headers["cache-control"] == "no-store"
        body = {
            "record_kind": "measured",
            "record_id": identifier,
            "selection": {"gene_id": "ALDOA"},
            "note": "可复查注释",
        }
        saved = client.post("/api/v1/research/findings", json=body)
        assert saved.status_code == 201, saved.text
        assert client.get("/api/v1/research/findings").json()["total"] == 1
        export = client.get(url + "/export")
        assert export.status_code == 200
        assert export.json()["findings"][0]["selection"] == {"gene_id": "ALDOA"}
        body["selection"] = {"gene_id": "UNKNOWN"}
        assert client.post("/api/v1/research/findings", json=body).status_code == 409
        body["note"] = "x" * 4001
        assert client.post("/api/v1/research/findings", json=body).status_code == 422
        assert client.get("/api/v1/research/results/measured/not_found").status_code == 404
        assert client.post("/api/v1/research/imports", json={"relative_path": "test.h5ad"}).status_code == 422


def test_import_api_enqueues_real_measured_record_with_frozen_import(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.app.api.research import router
    from backend.app.db.models import MeasuredAnalysisModel
    from backend.app.services.measured_jobs import MeasuredJobs

    container, body, _, _ = import_fixture(tmp_path)
    container.settings.worker_mode = "external"
    app = FastAPI()
    app.state.container = container
    app.state.measured = MeasuredJobs(container)
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as client:
        imported = client.post("/api/v1/research/imports", json=body)
        assert imported.status_code == 201, imported.text
        identifier = imported.json()["import_id"]
        queued = client.post(f"/api/v1/research/imports/{identifier}/analyses")
        assert queued.status_code == 202, queued.text
        assert queued.json()["source_kind"] == "measured"
        assert queued.json()["cell_line"] == "Custom"
        assert queued.json()["status"] == "queued"
        with container.store.session_factory() as session:
            row = session.get(MeasuredAnalysisModel, queued.json()["id"])
            assert row.request_json["import_id"] == identifier
            assert row.request_json["import_manifest_sha256"] == imported.json()["manifest_sha256"]


@pytest.mark.parametrize("scale", ["cp10k", "log1p_cp10k"])
def test_declared_normalized_scales_are_not_normalized_again(tmp_path, scale):
    container, body, path, matrix = import_fixture(tmp_path)
    frame = ad.read_h5ad(path)
    frame.X = matrix * 10 if scale == "cp10k" else np.log1p(matrix * 10)
    frame.write_h5ad(path)
    body.update(expression_scale=scale, total_counts_key=None)
    imported = import_h5ad(container.settings, body)
    canonical = ad.read_h5ad(tmp_path / imported["groups"]["control"]["path"])
    np.testing.assert_allclose(canonical.X, np.log1p(matrix[:2] * 10))


def test_prediction_reader_uses_frozen_counts_and_invalidates_unindexed_tables(tmp_path):
    contract = {
        "analysis_version": "expression-cp10k-v2",
        "gene_units": "mean(log1p(CP10K))",
        "gene_count": 1,
        "source_scales": {"control": "log1p_cp10k", "predicted": "log1p_cp10k", "observed": "log1p_cp10k"},
        "population_selection": {"selected_prediction_cells": 500},
        "validation_population": {
            "status": "common_batches_only",
            "selected_cells": {"control": 42, "predicted": 35, "observed": 27},
        },
    }
    container, identifier, directory = prediction_container(tmp_path, contract=contract)
    reader = ResearchResults(container)
    first = reader.read("prediction", identifier)
    assert {group["id"]: group["count"] for group in first["groups"]} == {
        "control": 42,
        "predicted": 35,
        "observed": 27,
    }
    # Inline observed counts do not establish a separately verified matched comparison.
    assert not first["availability"]["comparison"]["available"]
    assert first["populations"]["original"]["availability"]["available"]
    assert first["provenance"]["fingerprint_basis"] == "artifact-index"
    (directory / "gene_deltas.csv").write_text("gene,control,predicted,predicted_delta\nALDOA,1,3,2\n")
    second = reader.read("prediction", identifier)
    assert first["provenance"]["manifest_sha256"] != second["provenance"]["manifest_sha256"]


def test_public_export_never_queries_or_contains_private_findings(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.app.api.research import router

    container, identifier, _ = frozen_measured(tmp_path)
    private = ResearchFindings(container).create(
        "measured", identifier, {"gene_id": "ALDOA"}, "private-note-never-public"
    )
    container.settings.deployment_mode = "public"

    def forbidden(*args):
        pytest.fail("Public export must not access private findings")

    monkeypatch.setattr(ResearchFindings, "for_export", forbidden)
    app = FastAPI()
    app.state.container = container
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as client:
        exported = client.get(f"/api/v1/research/results/measured/{identifier}/export")
        assert exported.status_code == 200, exported.text
        assert exported.json()["findings"] == []
        assert "private-note-never-public" not in exported.text
        assert exported.json()["result"]["references"]["summary"].startswith("/api/v1/")
        assert exported.json()["source_manifest"]["inputs"]["groups"]["control"]["path"] == (
            "[private input location omitted]"
        )
    # Defense at the service layer as well as at the HTTP handler.
    assert ResearchResults(container).export("measured", identifier, [private])["findings"] == []


def test_sanitize_removes_embedded_locations_and_preserves_api_references():
    from backend.app.services.research_results import sanitize

    source = {
        "warning": "Unable to load 'D:\\private samples\\control.h5ad' for scoring",
        "references": {"detail": "/api/v1/measured/analyses/measured_example"},
        "inputs": {"D:\\private\\source.h5ad": "a" * 64},
        "source_filename": "private-sample.h5ad",
    }
    cleaned = sanitize(source, public=True)
    text = json.dumps(cleaned)
    assert "private samples" not in text and "private-sample.h5ad" not in text
    assert "D:" not in text
    assert cleaned["references"] == source["references"]
    assert list(cleaned["inputs"].values()) == ["a" * 64]


def test_reader_rejects_missing_manifest_output_and_wrong_background(tmp_path):
    container, identifier, directory = prediction_container(tmp_path)
    table = directory / "gene_deltas.csv"
    atomic_write_json(
        directory / "manifest.json", {"outputs": {"gene_deltas.csv": {"sha256": file_sha256(table)}}}
    )
    table.unlink()
    with pytest.raises(ValueError, match="登记的文件缺失"):
        ResearchResults(container).read("prediction", identifier)
    atomic_write_json(directory / "manifest.json", {"request": {"cell_line": "RPE1"}})
    with pytest.raises(ValueError, match="背景"):
        ResearchResults(container).read("prediction", identifier)


@pytest.mark.parametrize("backgrounds", [["RPE1"] * 4, ["Custom", "Custom", "Custom", "RPE1"]])
def test_import_does_not_overwrite_mismatching_or_mixed_source_background(tmp_path, backgrounds):
    container, body, path, _ = import_fixture(tmp_path)
    frame = ad.read_h5ad(path)
    frame.obs["cell_line"] = backgrounds
    frame.write_h5ad(path)
    with pytest.raises(ValueError, match="原始 cell_line"):
        import_h5ad(container.settings, body)


def test_import_retains_verified_background_and_original_group_identity(tmp_path):
    container, body, path, _ = import_fixture(tmp_path)
    frame = ad.read_h5ad(path)
    frame.obs["cell_line"] = "CUSTOM"
    frame.write_h5ad(path)
    imported = import_h5ad(container.settings, body)
    assert imported["background_validation"] == "verified_obs_cell_line"
    observed = ad.read_h5ad(tmp_path / imported["groups"]["observed"]["path"])
    assert set(observed.obs["source_group_label"]) == {"KO"}
    assert imported["contract"]["control_label"] == "CTRL"


def test_full_matrix_declaration_cannot_conflict_with_explicit_library_totals(tmp_path):
    container, body, _, _ = import_fixture(tmp_path, full_library=True)
    with pytest.raises(ValueError, match="完整基因矩阵声明"):
        import_h5ad(container.settings, body)
