from __future__ import annotations

import json
import shutil
from pathlib import Path

import anndata as ad
import pytest

from backend.app.core.run_manifest import file_sha256
from backend.app.services.pathway_analysis import (
    DEFAULT_MANIFEST,
    PathwayResourceError,
    measured_pathway_species,
)
from backend.app.services.perturbation_catalog import SOURCE
from backend.tests.test_measured_analysis import analyse, measured_inputs


def install_resource(root: Path) -> Path:
    target = root / "data/registry/pathways/reactome_v98"
    shutil.copytree(DEFAULT_MANIFEST.parent, target)
    return target


def test_detection_uses_only_actual_aligned_selected_cells(tmp_path):
    install_resource(tmp_path)
    inputs, _ = measured_inputs(tmp_path)
    inputs["source"] = dict(SOURCE)
    for group, entry in inputs["groups"].items():
        frame = ad.read_h5ad(entry["path"])
        frame.X[:, 0] = 0
        if group == "control":
            # ALDOA exists in the file, but only in an excluded batch.
            frame.X[-1, 0] = 7
            frame.obs["gem_group"] = ["batch-one", "batch-one", "excluded-batch"]
        frame.write_h5ad(entry["path"])
        entry["sha256"] = file_sha256(Path(entry["path"]))
    summary = analyse(tmp_path, inputs)
    document = json.loads((tmp_path / "result/pathways.json").read_text(encoding="utf-8"))
    assert "ALDOA" not in document["detectable_genes"]
    assert document["background_genes"] == ["GAPDH"]
    assert document["coverage"]["qc_detectable_count"] == 3
    assert document["species_basis"] == "fixed_human_source_revision"
    assert document["status"] == "no_candidates"
    assert "results" not in summary["pathways"]
    assert len(summary["provenance"]["analysis_assets"]) == 2
    assert (tmp_path / "result/pathways.csv").read_text().startswith("pathway_id,pathway_name,")


def test_missing_resource_and_private_unknown_do_not_fail_expression(tmp_path):
    inputs, _ = measured_inputs(tmp_path)
    inputs["source"] = dict(SOURCE)
    summary = analyse(tmp_path, inputs)
    assert summary["pathways"]["status"] == "resource_unavailable"
    assert summary["gene_count"] == 4
    inputs["source"] = {"kind": "controlled_private_h5ad"}
    install_resource(tmp_path)
    summary = analyse(tmp_path, inputs)
    assert summary["pathways"]["status"] == "species_unknown"
    assert not summary["pathways"]["available"]
    assert summary["provenance"]["analysis_assets"] == {}
    document = json.loads((tmp_path / "result/pathways.json").read_text(encoding="utf-8"))
    assert document["results"] == []


def test_present_but_altered_resource_rejects_analysis(tmp_path):
    resource = install_resource(tmp_path)
    with (resource / "ReactomePathways.gmt.zip").open("ab") as stream:
        stream.write(b"changed")
    inputs, _ = measured_inputs(tmp_path)
    inputs["source"] = dict(SOURCE)
    with pytest.raises(PathwayResourceError, match="SHA-256"):
        analyse(tmp_path, inputs)


def test_resource_change_during_analysis_is_rejected(tmp_path, monkeypatch):
    from backend.app.services import pathway_analysis

    resource = install_resource(tmp_path)
    original = pathway_analysis.analyze_pathways

    def mutate_after_compute(*args, **kwargs):
        result = original(*args, **kwargs)
        with (resource / "ReactomePathways.gmt.zip").open("ab") as stream:
            stream.write(b"changed")
        return result

    monkeypatch.setattr(pathway_analysis, "analyze_pathways", mutate_after_compute)
    inputs, _ = measured_inputs(tmp_path)
    inputs["source"] = dict(SOURCE)
    with pytest.raises(PathwayResourceError, match="changed during"):
        analyse(tmp_path, inputs)


def test_species_requires_frozen_contract_agreement():
    request = {"dataset_id": "example", "cell_line": "K562"}
    inputs = {"dataset_version": {"species": "human"}, "contrast": {"species": "Homo sapiens"}}
    assert measured_pathway_species(request, inputs)[0] == "Homo sapiens"
    inputs["contrast"]["species"] = "mouse"
    assert measured_pathway_species(request, inputs) == ("unknown", "conflicting_dataset_species")
    assert measured_pathway_species({"import_id": "example", "cell_line": "K562"}, {})[0] == "unknown"
    assert (
        measured_pathway_species({"import_id": "example"}, {"input_contract": {"species": "human"}})[0]
        == "Homo sapiens"
    )


def test_new_worker_freezes_pathways_and_read_never_recomputes(tmp_path, monkeypatch):
    from backend.app.services import pathway_analysis
    from backend.app.services.measured_results import result_directory, verified_result
    from backend.app.services.measured_worker import execute_measured_job

    resource = install_resource(tmp_path)
    inputs, _ = measured_inputs(tmp_path)
    inputs["source"] = dict(SOURCE)
    identifier = "measured_" + "d" * 24
    request = {"id": identifier, "cell_line": "K562", "perturbation": "ALDOA", "seed": 42, "max_cells": 256}
    final = result_directory(tmp_path, identifier)
    execute_measured_job(
        tmp_path,
        request,
        final.with_name(identifier + ".staging"),
        final,
        lambda *args: None,
        inputs=inputs,
        metabolism=False,
        compute_umap=False,
    )
    digest = file_sha256(final / "manifest.json")
    before = file_sha256(final / "pathways.json")

    def forbidden(*args, **kwargs):
        pytest.fail("Frozen reads must not recalculate ORA")

    monkeypatch.setattr(pathway_analysis, "analyze_pathways", forbidden)
    _, summary, manifest = verified_result(tmp_path, identifier, digest)
    assert {"pathways.json", "pathways.csv"} <= set(manifest["files"])
    assert manifest["files"]["pathways.json"] == before
    assert summary["pathways"]["hashes"]["analysis_sha256"]
    assert len(manifest["inputs"]["analysis_assets"]) == 2
    with (resource / "ReactomePathways.gmt.zip").open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="知识库"):
        verified_result(tmp_path, identifier, digest)
    assert file_sha256(final / "pathways.json") == before
