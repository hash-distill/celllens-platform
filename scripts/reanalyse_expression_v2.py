"""Reanalyse frozen predictions into new immutable runs; preserve every old file."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from backend.app.config import get_settings
from backend.app.core.cache import code_fingerprint
from backend.app.core.registry import AssetRegistry
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.core.storage import RunStore
from backend.app.schemas import CreateRunRequest, RunStatus, RunSummary
from backend.app.services.expression_scale import ANALYSIS_VERSION
from backend.app.services.pipeline import _artifact_kind, _mime_type, _render_report
from backend.app.services.scientific_analysis import ScientificAnalysisService

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "reports/scientific-scale-v2-2026-10-09"


def assert_originals(baseline: dict) -> None:
    for run_id, files in baseline["original_runs"].items():
        for name, expected in files.items():
            path = ROOT / "data/derived/runs" / run_id / name
            if file_sha256(path) != expected:
                raise ValueError(f"Frozen original changed: {run_id}/{name}")


def compare_tables(old: Path, new: Path, column: str) -> dict:
    if not old.is_file() or not new.is_file():
        return {"available": False}
    a, b = pd.read_csv(old, index_col=0), pd.read_csv(new, index_col=0)
    if column == "predicted_delta":
        names = a.index.intersection(b.index)
        av, bv = a.loc[names, column].to_numpy(), b.loc[names, column].to_numpy()
    else:
        a = a.drop(columns=["source"]).groupby(a["source"]).mean()
        b = b.drop(columns=["source"]).groupby(b["source"]).mean()
        names = a.columns.intersection(b.columns)
        av = (a.loc["predicted", names] - a.loc["control", names]).to_numpy()
        bv = (b.loc["predicted", names] - b.loc["control", names]).to_numpy()
    finite = np.isfinite(av) & np.isfinite(bv)
    av, bv, names = av[finite], bv[finite], names[finite]
    old_top = set(names[np.argsort(np.abs(av))[-20:]])
    new_top = set(names[np.argsort(np.abs(bv))[-20:]])
    return {
        "available": True,
        "paired_items": len(av),
        "mean_absolute_delta_change": float(np.mean(np.abs(av - bv))),
        "direction_changed_count": int(np.sum(np.sign(av) != np.sign(bv))),
        "top20_overlap": len(old_top & new_top),
    }


def publish(item: dict, store: RunStore) -> None:
    run_id = item["new_run_id"]
    source = PROOF / "recomputed" / run_id
    final = ROOT / "data/derived/runs" / run_id
    request = CreateRunRequest.model_validate(item["request"])
    if final.exists():
        raise ValueError(f"Refuse to replace a published run: {final}")
    # Everything is verified and complete before its new record is published.
    manifest = json.loads((source / "manifest.json").read_text())
    for name, info in manifest["outputs"].items():
        if file_sha256(source / name) != info["sha256"]:
            raise ValueError(f"Changed recomputation: {run_id}/{name}")
    store.create(run_id, request)
    shutil.copytree(source, final)
    for path in final.iterdir():
        if path.is_file():
            store.register_artifact(
                run_id,
                _artifact_kind(path),
                f"{run_id}/{path.name}",
                file_sha256(path),
                path.stat().st_size,
                _mime_type(path),
            )
    for status, progress in [
        (RunStatus.STATE_RUNNING, 15),
        (RunStatus.ADAPTING, 45),
        (RunStatus.METABOLIC_RUNNING, 65),
        (RunStatus.VALIDATING, 85),
        (RunStatus.COMPLETED, 100),
    ]:
        store.transition(
            run_id,
            status,
            progress,
            warnings=item["warnings"],
            message=f"{ANALYSIS_VERSION}: frozen prediction reused; analysis recomputed",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true", help="Publish already verified new runs")
    args = parser.parse_args()
    baseline = json.loads((PROOF / "baseline.json").read_text())
    assert_originals(baseline)
    report_path = PROOF / "reanalysis.json"
    if args.publish:
        report = json.loads(report_path.read_text())
        store = RunStore(get_settings().database_url)
        try:
            for item in report["items"]:
                publish(item, store)
                print(f"published {item['new_run_id']}", flush=True)
        finally:
            store.engine.dispose()
        assert_originals(baseline)
        return
    if report_path.exists():
        raise ValueError("Preserve previous recomputation; use --publish or a new analysis version")
    registry = AssetRegistry(ROOT, ROOT / "data/registry")
    service = ScientificAnalysisService(
        ROOT / "data/registry/sccellfie/human", gene_identity_root=ROOT / "data/registry/gene_identity"
    )
    code_hash = code_fingerprint(ROOT)
    items = []
    for source_id in baseline["original_runs"]:
        old = ROOT / "data/derived/runs" / source_id
        original = json.loads((old / "manifest.json").read_text())
        request = CreateRunRequest.model_validate(original["request"])
        model, dataset = registry.model_for(request.cell_line), registry.dataset_for(request.cell_line)
        if original["assets"]["model_id"] != model.payload["id"]:
            raise ValueError(f"Different model contract: {source_id}")
        for entry, key, hash_key in [
            (model, "gene_list_path", "gene_list_sha256"),
            (dataset, "control_path", "control_sha256"),
        ]:
            actual = registry.verify_entry(entry, key, hash_key)
            if original["assets"].get(hash_key) != actual:
                raise ValueError(f"Cannot reanalyse with a different {key}: {source_id}")
        new_id = (
            "run_" + hashlib.sha256(f"{source_id}:{ANALYSIS_VERSION}:{code_hash}".encode()).hexdigest()[:16]
        )
        out = PROOF / "recomputed" / new_id
        out.mkdir(parents=True, exist_ok=False)
        shutil.copy2(old / "predicted.h5ad", out / "predicted.h5ad")
        result = service.run(new_id, request, model, dataset, out / "predicted.h5ad", out)
        if result.summary["warnings"]:
            raise ValueError(f"Reanalysis needs investigation: {source_id}: {result.summary['warnings']}")
        summary = RunSummary.model_validate(result.summary)
        atomic_write_json(out / "summary.json", summary.model_dump(mode="json"))
        (out / "report.html").write_text(_render_report(summary), encoding="utf-8")
        atomic_write_json(
            out / "manifest.json",
            {
                "request": request.model_dump(mode="json"),
                "assets": {
                    **original["assets"],
                    "model_expression_scale": model.payload["expression_scale"],
                    "dataset_expression_scale": dataset.payload["expression_scale"],
                },
                "analysis_version": ANALYSIS_VERSION,
                "code_sha256": code_hash,
                "prediction_reused": True,
                "reanalysis_of": source_id,
                "original_manifest_sha256": file_sha256(old / "manifest.json"),
                "outputs": {
                    p.name: {"sha256": file_sha256(p), "size_bytes": p.stat().st_size}
                    for p in out.iterdir()
                    if p.is_file()
                },
                "warnings": result.summary["warnings"],
            },
        )
        item = {
            "source_run_id": source_id,
            "new_run_id": new_id,
            "request": request.model_dump(mode="json"),
            "warnings": result.summary["warnings"],
            "prediction_byte_identical": file_sha256(old / "predicted.h5ad")
            == file_sha256(out / "predicted.h5ad"),
            "genes": compare_tables(old / "gene_deltas.csv", out / "gene_deltas.csv", "predicted_delta"),
            "metabolism": compare_tables(
                old / "metabolic_task_scores.csv", out / "metabolic_task_scores.csv", "task"
            ),
        }
        items.append(item)
        print(f"recomputed {source_id} -> {new_id}: {request.cell_line}/{request.perturbation}", flush=True)
    assert_originals(baseline)
    atomic_write_json(
        report_path,
        {
            "analysis_version": ANALYSIS_VERSION,
            "items": items,
            "all_original_files_unchanged": True,
            "new_inference_executed": False,
        },
    )


if __name__ == "__main__":
    main()
