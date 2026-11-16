"""Scientific adapter regressions using small, explicitly synthetic matrix fixtures."""

import csv
import io
import json
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import pytest

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.comparison_diagnostics import VERSION, prepare_diagnostics
from backend.app.services.measured_comparison import ComparisonUnavailable, load_comparison
from backend.app.services.research_results import ResearchResults
from backend.tests.test_research_contract import prediction_container


def frozen_comparison(
    root: Path, run_id="run_fixture", *, duplicated=False, degenerate=False, observed_suffix=""
):
    original = root / "data/derived/runs" / run_id
    bundle = root / "data/derived/comparisons" / run_id
    original.mkdir(parents=True, exist_ok=True)
    bundle.mkdir(parents=True)
    raw = root / "data/raw/fixture"
    raw.mkdir(parents=True, exist_ok=True)
    panel = raw / "panel.txt"
    panel.write_text("A\nB\nC\n", encoding="utf-8")
    arrays = {
        "control": [[1, 2, 3], [1, 2, 3], [5, 3, 4]],
        "predicted": [[2, 2, 4], [6, 4, 4], [6, 4, 4]],
        "observed": [[2, 3, 3], [5, 5, 5]],
    }
    if degenerate:
        arrays = {group: [[1, 1, 1]] * len(rows) for group, rows in arrays.items()}
    batches = {"control": ["a", "a", "b"], "predicted": ["a", "b", "b"], "observed": ["a", "b"]}
    paths, means = {}, {}
    for group, rows in arrays.items():
        names = [f"{group}_{i}" for i in range(len(rows))]
        if group == "observed":
            names = [name + observed_suffix for name in names]
        if duplicated and group == "predicted":
            names[1] = names[0]
        frame = ad.AnnData(
            np.array(rows, dtype=np.float64),
            obs=pd.DataFrame({"gem_group": batches[group], "gene": "ALDOA"}, index=names),
            var=pd.DataFrame(index=["A", "B", "C"]),
        )
        path = original / "predicted.h5ad" if group == "predicted" else raw / f"{group}.h5ad"
        frame.write_h5ad(path)
        paths[group] = path
        means[group] = np.asarray(rows).mean(axis=0)
    contract = {
        "analysis_version": "expression-cp10k-v2",
        "gene_units": "mean(log1p(CP10K))",
        "source_scales": {group: "log1p_cp10k" for group in arrays},
        "population_selection": {"perturbation_column": "gene", "selected_prediction_cells": 3},
    }
    atomic_write_json(bundle / "expression_contract.json", contract)
    prediction_contract = {
        **contract,
        "source_scales": {"control": "log1p_cp10k", "predicted": "log1p_cp10k"},
    }
    atomic_write_json(original / "expression_contract.json", prediction_contract)
    atomic_write_json(original / "summary.json", {"run_id": run_id, "result_kind": "frozen_model_result"})
    (original / "metabolic_task_scores.csv").write_text(
        ",T,source\nc0,1,control\nc1,2,control\nc2,3,control\np0,1,predicted\np1,2,predicted\np2,3,predicted\n"
    )
    atomic_write_json(
        original / "manifest.json",
        {
            "request": {"cell_line": "K562", "perturbation": "ALDOA"},
            "assets": {
                "control_sha256": file_sha256(paths["control"]),
                "gene_list_sha256": file_sha256(panel),
                "expression_key": "X",
            },
            "outputs": {
                path.name: {"sha256": file_sha256(path)} for path in original.iterdir() if path.is_file()
            },
        },
    )
    pred, obs = means["predicted"] - means["control"], means["observed"] - means["control"]
    mse, baseline = float(np.mean((pred - obs) ** 2)), float(np.mean(obs**2))
    genes = [
        {
            "id": gene,
            **{group: float(values[i]) for group, values in means.items()},
            "predicted_delta": float(pred[i]),
            "observed_delta": float(obs[i]),
            "absolute_error": float(abs(pred[i] - obs[i])),
        }
        for i, gene in enumerate(["A", "B", "C"])
    ]
    report = {
        "status": "available",
        "run_id": run_id,
        "cell_line": "K562",
        "perturbation": "ALDOA",
        "source": {"observed_sha256": file_sha256(paths["observed"]), "revision": "fixture-revision"},
        "parameters": {"population_counts": {group: len(rows) for group, rows in arrays.items()}},
        "population_matching": {
            "batch_key": "gem_group",
            "common_batches": ["a", "b"],
            "input_cells": {group: len(rows) for group, rows in arrays.items()},
        },
        "expression": {
            "mse": mse,
            "no_change_mse": baseline,
            "mse_relative_to_no_change": mse / baseline if baseline > 0 else None,
            "signed_delta_pearson": float(np.corrcoef(pred, obs)[0, 1])
            if np.std(pred) > 0 and np.std(obs) > 0
            else None,
        },
        "genes": genes,
        "tasks": [{**genes[0], "id": "T"}, {**genes[0], "id": "T2"}],
    }
    atomic_write_json(bundle / "comparison.json", report)
    (bundle / "metabolic_coverage.csv").write_text(
        "task,gene_fraction,evidence_level,missing_genes\nT,1,supported,\nT2,0.5,insufficient,D\nT3,0,insufficient,A\n"
    )
    inputs = {path.relative_to(root).as_posix(): file_sha256(path) for path in [*paths.values(), panel]}
    atomic_write_json(
        bundle / "manifest.json",
        {
            "run_id": run_id,
            "source_manifest_sha256": file_sha256(original / "manifest.json"),
            "inputs": inputs,
            "outputs": {path.name: file_sha256(path) for path in bundle.iterdir()},
        },
    )
    return original, bundle


def test_diagnostics_are_explicit_immutable_and_do_not_reopen_matrices_on_read(tmp_path, monkeypatch):
    original, bundle = frozen_comparison(tmp_path)
    before = {str(path): file_sha256(path) for folder in (original, bundle) for path in folder.iterdir()}
    initial = load_comparison(tmp_path, "run_fixture")
    assert initial["batch_sensitivity"]["status"] == "unavailable"
    assert not (tmp_path / "data/derived/comparison_diagnostics").exists()
    prepared = prepare_diagnostics(tmp_path, "run_fixture")
    # Independent batch means: control [3,2.5,3.5], prediction [4,3,4], observed [3.5,4,4].
    assert prepared["batch_sensitivity"]["equal_batch_weight"]["mse_relative_to_no_change"] == pytest.approx(
        5 / 11
    )
    assert prepared["task_statistics"]["distinct_mean_triplets_8dp"] == 1
    assert before == {
        str(path): file_sha256(path) for folder in (original, bundle) for path in folder.iterdir()
    }
    monkeypatch.setattr(ad, "read_h5ad", lambda *a, **kw: pytest.fail("GET must not open matrices"))
    loaded = load_comparison(tmp_path, "run_fixture")
    assert loaded["batch_sensitivity"]["status"] == "available"
    assert loaded["task_coverage"]["by_evidence_level"]["supported"] == 1
    assert loaded["task_coverage"]["unscored_task_count"] == 1
    assert loaded["tasks"][1]["missing_genes"] == "D"
    assert loaded["tasks"][0]["same_score_structure_task_count"] == 2
    assert (
        prepare_diagnostics(tmp_path, "run_fixture")["diagnostics_sha256"] == prepared["diagnostics_sha256"]
    )
    sidecar = tmp_path / "data/derived/comparison_diagnostics" / VERSION / "run_fixture/diagnostics.json"
    sidecar.write_text("{}")
    invalid = load_comparison(tmp_path, "run_fixture")
    assert invalid["status"] == "available" and invalid["batch_sensitivity"]["status"] == "invalid"
    assert invalid["evaluation_protocol"]["reference_selection_sha256"] is None


def test_duplicate_cells_are_rejected_before_preparing(tmp_path):
    frozen_comparison(tmp_path, duplicated=True)
    with pytest.raises(ComparisonUnavailable, match="duplicate cell IDs"):
        prepare_diagnostics(tmp_path, "run_fixture")


def test_zero_baseline_and_constant_vectors_are_undefined_not_false_evidence(tmp_path):
    from backend.app.services.comparison_diagnostics import _verify_metric

    frozen_comparison(tmp_path, degenerate=True)
    document = prepare_diagnostics(tmp_path, "run_fixture")
    sensitivity = document["batch_sensitivity"]
    assert sensitivity["pooled_cells"]["mse"] == 0
    assert sensitivity["pooled_cells"]["signed_delta_pearson"] is None
    assert sensitivity["equal_batch_weight"]["mse_relative_to_no_change"] is None
    assert sensitivity["baseline_conclusion_consistent"] is None
    assert "为零" in sensitivity["baseline_comparison_reason"]
    assert _verify_metric(None, None) and _verify_metric(0, 0)
    assert not _verify_metric(None, 0) and not _verify_metric(float("inf"), float("inf"))


def test_reference_fingerprint_ignores_run_id_but_changes_with_measured_cells(tmp_path):
    first = tmp_path / "one"
    second = tmp_path / "two"
    third = tmp_path / "three"
    fingerprints = []
    for root, run_id, suffix in ((first, "run_a", ""), (second, "run_b", ""), (third, "run_c", "_other")):
        frozen_comparison(root, run_id, observed_suffix=suffix)
        document = prepare_diagnostics(root, run_id)
        fingerprints.append(document["evaluation_protocol"]["reference_selection_sha256"])
    assert fingerprints[0] == fingerprints[1]
    assert fingerprints[0] != fingerprints[2]


def test_frozen_input_tamper_rejects_comparison_and_no_diagnostic_is_created(tmp_path):
    _, bundle = frozen_comparison(tmp_path)
    with (bundle / "metabolic_coverage.csv").open("a") as stream:
        stream.write("T4,1,supported,\n")
    with pytest.raises(ComparisonUnavailable, match="hash"):
        prepare_diagnostics(tmp_path, "run_fixture")
    assert not (tmp_path / "data/derived/comparison_diagnostics").exists()


def test_research_separates_populations_binds_diagnostics_and_never_reads_private_comparison(
    tmp_path, monkeypatch
):
    container, run_id, _ = prediction_container(tmp_path)
    frozen_comparison(tmp_path, run_id)
    reader = ResearchResults(container)
    before = reader.read("prediction", run_id)
    assert {row["id"]: row["count"] for row in before["groups"]} == {"control": 3, "predicted": 3}
    assert before["availability"]["comparison"]["available"]
    matched = before["populations"]["matched_comparison"]
    assert {row["id"]: row["count"] for row in matched["groups"]}["observed"] == 2
    assert before["provenance"]["fingerprint_basis"] == "original-and-matched-comparison"
    reader.validate_selection("prediction", run_id, {"group_id": "observed"})
    with pytest.raises(ValueError, match="群体"):
        reader.validate_selection("prediction", run_id, {"group_id": "observed", "projection_id": "pca"})
    prepare_diagnostics(tmp_path, run_id)
    after = reader.read("prediction", run_id)
    assert after["provenance"]["manifest_sha256"] != before["provenance"]["manifest_sha256"]
    assert after["populations"]["original"] == before["populations"]["original"]
    container.settings.deployment_mode = "public"
    from backend.app.services import measured_comparison

    monkeypatch.setattr(measured_comparison, "load_comparison", lambda *a, **kw: pytest.fail("private read"))
    public = reader.read("prediction", run_id)
    assert not public["availability"]["comparison"]["available"]
    assert "comparison_sha256" not in json.dumps(public["populations"]["matched_comparison"])


def test_comparison_csv_carries_full_provenance_and_own_task_coverage(tmp_path, monkeypatch):
    from backend.app.services import export_tables
    from backend.tests.test_export_tables import export_app

    app, _ = export_app(tmp_path)
    root, bundle = frozen_comparison(tmp_path, "run_export")
    # export_app registers an earlier fixture manifest; use this complete synthetic frozen manifest.
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["request"]["perturbation"] = "MYC"
    atomic_write_json(root / "manifest.json", manifest)
    comp = json.loads((bundle / "comparison.json").read_text())
    comp["perturbation"] = "MYC"
    atomic_write_json(bundle / "comparison.json", comp)
    bound = json.loads((bundle / "manifest.json").read_text())
    bound["source_manifest_sha256"] = file_sha256(root / "manifest.json")
    bound["outputs"]["comparison.json"] = file_sha256(bundle / "comparison.json")
    atomic_write_json(bundle / "manifest.json", bound)
    monkeypatch.setattr(
        export_tables, "_manifest", lambda *a: (root, manifest, file_sha256(root / "manifest.json"))
    )
    content, _ = export_tables.export_table(app.state.container, "run_export", "tasks", "comparison")
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    assert rows[0]["coverage"] == "1.0" and rows[1]["missing_genes"] == "D"
    assert rows[0]["comparison_sha256"] == file_sha256(bundle / "comparison.json")
    assert rows[0]["comparison_manifest_sha256"] == file_sha256(bundle / "manifest.json")
    assert rows[0]["observed_sha256"] == comp["source"]["observed_sha256"]
    assert rows[0]["source_revision"] == "fixture-revision"
    assert json.loads(rows[0]["selection_json"])["common_batches"] == ["a", "b"]
    assert rows[0]["metadata_url"].endswith("comparison/download?table=json")
    app.state.container.settings.deployment_mode = "public"
    monkeypatch.setattr(export_tables, "load_comparison", lambda *a, **kw: pytest.fail("private read"))
    with pytest.raises(ValueError, match="Public"):
        export_tables.table_metadata(app.state.container, "run_export", "comparison")


def test_preparation_endpoint_is_explicit_same_origin_and_serialized(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.app.api.comparisons import _diagnostics_lock
    from backend.app.main import create_app
    from backend.app.schemas import CreateRunRequest, RunStatus
    from backend.app.services import comparison_diagnostics
    from backend.tests.test_measured_comparison import write_bundle
    from backend.tests.test_system_integration import _settings, _write_registry

    _write_registry(tmp_path)
    app = create_app(_settings(tmp_path))
    calls = []
    monkeypatch.setattr(comparison_diagnostics, "prepare_diagnostics", lambda *args: calls.append(args))
    with TestClient(app) as client:
        app.state.container.store.create("run_test", CreateRunRequest(cell_line="K562", perturbation="AAMP"))
        app.state.container.store.transition("run_test", RunStatus.COMPLETED, 100)
        write_bundle(tmp_path)
        url = "/api/v1/runs/run_test/comparison"
        assert client.get(url).status_code == 200 and not calls
        assert (
            client.post(url + "/diagnostics/prepare", headers={"Origin": "http://other.test"}).status_code
            == 403
        )
        assert not calls
        _diagnostics_lock.acquire()
        try:
            assert client.post(url + "/diagnostics/prepare").status_code == 409
        finally:
            _diagnostics_lock.release()
        assert not calls
        assert client.post(url + "/diagnostics/prepare").status_code == 200 and len(calls) == 1
        app.state.container.settings.deployment_mode = "public"
        assert client.post(url + "/diagnostics/prepare").status_code == 403
        assert len(calls) == 1


def test_unified_export_keeps_original_and_matched_tables_and_provenance_distinct(tmp_path, monkeypatch):
    container, run_id, _ = prediction_container(tmp_path)
    original, comparison_directory = frozen_comparison(tmp_path, run_id)
    prepare_diagnostics(tmp_path, run_id)
    before = {
        str(path): file_sha256(path)
        for folder in (original, comparison_directory)
        for path in folder.iterdir()
        if path.is_file()
    }
    reader = ResearchResults(container)
    document = reader.export("prediction", run_id, [])
    assert document["tables_population"] == document["summary_population"] == "original"
    assert document["source_manifest_population"] == "original"
    assert all(table["population"] == "original" for table in document["tables"].values())
    assert document["tables"]["gene_deltas.csv"]["rows"][0] == {
        "gene": "ALDOA",
        "control": "1",
        "predicted": "2",
        "predicted_delta": "1",
    }
    original_export = document["population_exports"]["original"]
    matched = document["population_exports"]["matched_comparison"]
    assert {row["id"] for row in original_export["groups"]} == {"control", "predicted"}
    assert {row["id"] for row in matched["groups"]} == {"control", "predicted", "observed"}
    assert matched["tables"]["genes"]["population"] == "matched_comparison"
    assert matched["tables"]["genes"]["rows"][0]["id"] == "A"
    assert matched["tables"]["genes"]["rows"][0]["control"] == pytest.approx(7 / 3)
    assert matched["tables"]["genes"]["source_sha256"] == file_sha256(
        comparison_directory / "comparison.json"
    )
    assert matched["tables"]["tasks"]["rows"][1]["missing_genes"] == "D"
    assert matched["evaluation_protocol"]["reference_selection_sha256"]
    assert matched["batch_sensitivity"]["status"] == "available"
    assert before == {
        str(path): file_sha256(path)
        for folder in (original, comparison_directory)
        for path in folder.iterdir()
        if path.is_file()
    }
    container.settings.deployment_mode = "public"
    from backend.app.services import measured_comparison

    monkeypatch.setattr(
        measured_comparison, "load_comparison", lambda *a, **kw: pytest.fail("private export read")
    )
    public = reader.export("prediction", run_id, [])
    assert public["tables_population"] == "original"
    assert not public["population_exports"]["matched_comparison"]["availability"]["available"]
    assert "tables" not in public["population_exports"]["matched_comparison"]
