"""Freeze four measured ALDOA diagnostics and real, hash-checked offline replays."""

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

import anndata as ad
import numpy as np
from fastapi.testclient import TestClient

from backend.app.core.precomputed import load_bundle
from backend.app.core.registry import AssetRegistry
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.main import create_app
from backend.app.services.expression_scale import validate_expression

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "reports/four-context-capabilities-2026-10-09"
CONTEXTS = {"K562": "k562", "RPE1": "rpe1", "Jurkat": "jurkat", "HepG2": "hepg2"}
SOURCE = ROOT / "reports/metabolic-full-coverage-2026-10-09/se-measured-aldoa"
FILES = (
    "summary.json",
    "projection.json",
    "gene_deltas.csv",
    "expression_contract.json",
    "metabolic_task_scores.csv",
    "metabolic_coverage.csv",
    "reaction_scores.csv",
    "task_trace.json",
    "official_completeness.json",
    "validation_metrics.json",
    "differential_expression.csv",
    "gene_identity.json",
    "report.html",
)


def assert_originals() -> None:
    baseline = json.loads((PROOF / "baseline.json").read_text())
    for name, digest in baseline["protected_files"].items():
        if file_sha256(ROOT / name) != digest:
            raise ValueError(f"Original changed: {name}")


def prepare() -> None:
    baseline_path = PROOF / "baseline.json"
    if baseline_path.exists():
        raise ValueError("Existing preparation is immutable")
    protected = [p for p in (ROOT / "data/derived/runs").rglob("*") if p.is_file()]
    protected += [p for p in (ROOT / "data/demo").rglob("*") if p.is_file()]
    registry = AssetRegistry(ROOT, ROOT / "data/registry")
    for context in CONTEXTS:
        dataset = registry.dataset_for(context)
        for key in ("control_path", "observed_path"):
            if dataset.payload.get(key):
                protected.append(dataset.path(key))
        model = registry.model_for(context)
        for key in ("checkpoint_path", "gene_list_path", "config_path"):
            protected.append(model.path(key))
    atomic_write_json(
        baseline_path,
        {"protected_files": {p.relative_to(ROOT).as_posix(): file_sha256(p) for p in protected}},
    )
    data_path = ROOT / "data/registry/datasets.json"
    data = json.loads(data_path.read_text())
    inputs = []
    for context, slug in CONTEXTS.items():
        source = SOURCE / slug / "measured.h5ad"
        measured = ad.read_h5ad(source)
        validate_expression(measured.X)
        if set(measured.obs["gene"].astype(str)) != {"ALDOA"} or measured.n_obs < 2:
            raise ValueError(f"Missing real ALDOA cells: {context}")
        if set(measured.obs["cell_line"].astype(str).str.lower()) != {slug}:
            raise ValueError(f"Wrong measured context: {context}")
        provenance = measured.uns["celllens_provenance"]
        if provenance["kind"] != "measured expression unchanged":
            raise ValueError("Only unchanged measured source expressions are accepted")
        destination = ROOT / f"data/raw/replogle-{slug}/diagnostic-aldoa-v1.h5ad"
        if destination.exists():
            raise ValueError(f"Refuse to replace {destination}")
        shutil.copy2(source, destination)
        digest = file_sha256(destination)
        assert digest == file_sha256(source)
        protocol = {
            "schema_version": 1,
            "kind": "matched_observation_diagnostic",
            "cell_line": context,
            "perturbations": ["ALDOA"],
            "observed_sha256": digest,
            "expression_scale": "log1p_cp10k",
            "batch_key": "gem_group",
            "held_out_validation": False,
            "training_exclusion_verified": False,
            "source_revision": str(provenance["revision"]),
            "source_repo": str(provenance["repo"]),
            "source_path": source.relative_to(ROOT).as_posix(),
            "measured_cells": measured.n_obs,
            "measured_source_rows": measured.obs["source_row"].astype(int).tolist(),
            "sampling": "existing fixed measured ALDOA sample; no added or duplicated observed cells",
            "population": "common recorded gem_group only; frequencies not reweighted",
            "evaluation": "expression-cp10k-v2; no-change baseline; cell-level DE diagnostic",
            "prediction_cells": 256,
            "prediction_seed": 43,
        }
        protocol_path = ROOT / f"configs/diagnostics/{slug}-aldoa-v1.json"
        atomic_write_json(protocol_path, protocol)
        dataset = next(row for row in data["datasets"] if row["cell_line"] == context)
        dataset.update(
            observed_path=destination.relative_to(ROOT).as_posix(),
            observed_sha256=digest,
            validation_batch_key="gem_group",
            validation_protocol_path=protocol_path.relative_to(ROOT).as_posix(),
            validation_protocol_sha256=file_sha256(protocol_path),
        )
        inputs.append(protocol)
    atomic_write_json(data_path, data)
    atomic_write_json(PROOF / "inputs.json", {"inputs": inputs, "observed_values_unchanged": True})
    assert_originals()
    print("prepared four unchanged measured datasets and diagnostic-only protocols", flush=True)


def diagnose() -> None:
    path = PROOF / "diagnostics.json"
    if path.exists():
        raise ValueError("Preserve completed diagnostics")
    receipt = {"items": []}
    with TestClient(create_app()) as client:
        for context in CONTEXTS:
            response = client.post(
                "/api/v1/runs",
                json={
                    "cell_line": context,
                    "perturbation": "ALDOA",
                    "mode": "validation",
                    "n_cells": 256,
                    "seed": 43,
                },
            )
            response.raise_for_status()
            creation = response.json()
            if creation["cache_hit"]:
                raise ValueError("Fresh real model computation required")
            run_id = creation["run_id"]
            print(f"{context}: started {run_id}", flush=True)
            deadline = time.monotonic() + 1800
            status = None
            while time.monotonic() < deadline:
                record = client.get(f"/api/v1/runs/{run_id}").json()
                if record["status"] != status:
                    status = record["status"]
                    print(context, status, record["stage_progress"], flush=True)
                if status in {"completed", "failed"}:
                    break
                time.sleep(2)
            if status != "completed":
                raise ValueError(record)
            directory = ROOT / "data/derived/runs" / run_id
            manifest = json.loads((directory / "manifest.json").read_text())
            for name, info in manifest["outputs"].items():
                assert file_sha256(directory / name) == info["sha256"]
            frame = ad.read_h5ad(directory / "predicted.h5ad")
            target = frame.obs["gene"].astype(str).str.upper() == "ALDOA"
            matrix = np.asarray(frame.obsm["X_hvg"])[target]
            assert matrix.shape == (256, 2000) and np.isfinite(matrix).all()
            model = AssetRegistry(ROOT, ROOT / "data/registry").model_for(context)
            panel = model.path("gene_list_path")
            original: Any = frame[target, panel.read_text().splitlines()].X
            original = original.toarray() if hasattr(original, "toarray") else np.asarray(original)
            assert np.abs(matrix - original).mean() > 0
            summary = client.get(f"/api/v1/runs/{run_id}/summary").json()
            assert not summary["warnings"], summary["warnings"]
            validation = client.get(f"/api/v1/runs/{run_id}/validation").json()
            assert validation["held_out_validation"] is False
            item = {
                "cell_line": context,
                "run_id": run_id,
                "cache_hit": False,
                "prediction_cells": 256,
                "expression": validation["expression"],
                "differential_expression": validation["differential_expression"],
                "population": json.loads((directory / "expression_contract.json").read_text())[
                    "validation_population"
                ],
                "manifest_sha256": file_sha256(directory / "manifest.json"),
            }
            receipt["items"].append(item)
            atomic_write_json(PROOF / "diagnostics.partial.json", receipt)
            print(
                f"{context}: MSE/baseline={item['expression']['mse_relative_to_no_change']:.4f}", flush=True
            )
    assert_originals()
    atomic_write_json(path, receipt)


def bundle() -> None:
    results = []
    for item in json.loads((PROOF / "diagnostics.json").read_text())["items"]:
        source = ROOT / "data/derived/runs" / item["run_id"]
        original = json.loads((source / "manifest.json").read_text())
        target = ROOT / "data/demo" / item["cell_line"] / "ALDOA"
        target.mkdir(parents=True, exist_ok=False)
        for name in FILES:
            if file_sha256(source / name) != original["outputs"][name]["sha256"]:
                raise ValueError(f"Source result changed: {name}")
            shutil.copy2(source / name, target / name)
        shutil.copy2(source / "manifest.json", target / "source_manifest.json")
        atomic_write_json(
            target / "manifest.json",
            {
                "kind": "frozen_model_result",
                "source_run_id": item["run_id"],
                "source_manifest_sha256": file_sha256(source / "manifest.json"),
                "files": {p.name: file_sha256(p) for p in target.iterdir() if p.is_file()},
            },
        )
        template, _ = load_bundle(target, item["cell_line"], "ALDOA")
        assert template.result_kind == "frozen_model_result"
        results.append(
            {
                "cell_line": item["cell_line"],
                "source_run_id": item["run_id"],
                "bundle_manifest_sha256": file_sha256(target / "manifest.json"),
            }
        )
    atomic_write_json(PROOF / "bundles.json", {"items": results})
    assert_originals()
    print("four real frozen bundles ready", flush=True)


def replay() -> None:
    results = []
    with TestClient(create_app()) as client:
        for item in json.loads((PROOF / "diagnostics.json").read_text())["items"]:
            response = client.post(
                "/api/v1/runs",
                json={
                    "cell_line": item["cell_line"],
                    "perturbation": "ALDOA",
                    "mode": "precomputed",
                    "n_cells": 64,
                },
            )
            response.raise_for_status()
            run_id = response.json()["run_id"]
            record = client.get(f"/api/v1/runs/{run_id}").json()
            assert record["result_kind"] == "frozen_model_result" and record["status"] == "completed"
            for endpoint in (
                "summary",
                "genes",
                "projection",
                "completeness",
                "validation",
                "provenance",
                "metabolic-tasks?scope=all",
                "reactions",
            ):
                checked = client.get(f"/api/v1/runs/{run_id}/{endpoint}")
                checked.raise_for_status()
            metrics = client.get(f"/api/v1/runs/{run_id}/validation").json()
            assert metrics["expression"] == item["expression"]
            original = ROOT / "data/derived/runs" / item["run_id"]
            new = ROOT / "data/derived/runs" / run_id
            for name in (
                "gene_deltas.csv",
                "metabolic_task_scores.csv",
                "projection.json",
                "validation_metrics.json",
            ):
                assert file_sha256(original / name) == file_sha256(new / name)
            tasks = client.get(f"/api/v1/runs/{run_id}/metabolic-tasks?scope=all").json()["items"]
            task = next(row["id"] for row in tasks if row["trace_available"])
            trace = client.get(f"/api/v1/runs/{run_id}/task-trace", params={"task_id": task})
            trace.raise_for_status()
            assert trace.json()["run_id"] == run_id
            results.append(
                {
                    "cell_line": item["cell_line"],
                    "run_id": run_id,
                    "source_run_id": item["run_id"],
                    "source_metrics_unchanged": True,
                }
            )
    assert_originals()
    atomic_write_json(PROOF / "replays.json", {"items": results, "all_original_files_unchanged": True})
    print("four replay runs passed source, metric and artifact checks", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "diagnose", "bundle", "replay", "verify"))
    args = parser.parse_args()
    if args.phase == "verify":
        assert_originals()
        print("all frozen original files unchanged")
    else:
        {"prepare": prepare, "diagnose": diagnose, "bundle": bundle, "replay": replay}[args.phase]()
