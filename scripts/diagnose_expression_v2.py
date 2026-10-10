"""Freeze and evaluate two existing real AAMP predictions; never tune on outcomes."""

import argparse
import hashlib
import json
import shutil
from importlib.metadata import version

import anndata as ad
import numpy as np
import pandas as pd

from backend.app.config import get_settings
from backend.app.core.cache import code_fingerprint
from backend.app.core.registry import AssetRegistry, RegistryEntry
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.core.storage import RunStore
from backend.app.schemas import CreateRunRequest, RunSummary
from backend.app.services.expression_scale import prepare_log_expression
from backend.app.services.gene_identity import GeneIdentityAdapter
from backend.app.services.pipeline import _render_report
from backend.app.services.scientific_analysis import (
    ScientificAnalysisService,
    _align_sources,
    _expression_view,
    _match_validation_batches,
    _select_prediction_population,
)
from scripts.reanalyse_expression_v2 import PROOF, ROOT, assert_originals, publish

CASES = (
    ("K562", "run_4d0b3038ea8642af", "data/raw/replogle-k562/heldout.h5ad"),
    (
        "Jurkat",
        "run_5e06e0fd0b9140a7",
        "reports/metabolic-full-coverage-2026-10-09/se-observed-diagnostic-shared-batches/jurkat-measured.h5ad",
    ),
)


def official_expression_metrics(control, predicted, observed) -> dict:
    from cell_eval import PerturbationAnndataPair, metrics_registry

    c, p, o = control.copy(), predicted.copy(), observed.copy()
    c.obs["evaluation_perturbation"] = "control"
    p.obs["evaluation_perturbation"] = o.obs["evaluation_perturbation"] = "AAMP"
    real, pred = ad.concat([c, o], index_unique="-"), ad.concat([c, p], index_unique="-")
    pair = PerturbationAnndataPair(real, pred, "evaluation_perturbation", "control")
    measured = {}
    for name in ("mse", "mae", "mse_delta", "mae_delta", "pearson_delta"):
        value = metrics_registry.compute(name, pair)
        measured[name] = (
            {str(k): float(v) for k, v in value.items()} if isinstance(value, dict) else float(value)
        )
    return {
        "package_version": version("cell-eval"),
        "metrics": measured,
        "scope": "official selected expression metrics; DE uses separately documented Scanpy",
        "full_profile_executed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    baseline = json.loads((PROOF / "baseline.json").read_text())
    assert_originals(baseline)
    output_report = PROOF / "expression-diagnostics.json"
    if args.publish:
        store = RunStore(get_settings().database_url)
        try:
            for item in json.loads(output_report.read_text())["items"]:
                publish(item, store)
                print(f"published diagnostic {item['new_run_id']}", flush=True)
        finally:
            store.engine.dispose()
        return
    if output_report.exists():
        raise ValueError("Preserve the completed diagnostic")
    registry = AssetRegistry(ROOT, ROOT / "data/registry")
    protocol = {
        "selected_before_evaluation": True,
        "perturbation": "AAMP",
        "selection_basis": "existing real AAMP predictions and locally available measured AAMP cells",
        "no_new_observed_data_generated": True,
        "held_out_validation": False,
        "checkpoint_training_exclusion_verified": False,
        "batch_matching": "intersection of recorded gem_group across control/predicted/observed",
        "baseline": "no_change",
        "top_k": [50, 100, 200],
        "fdr": 0.05,
        "cases": [
            {
                "context": c,
                "source_run_id": run,
                "observed_path": path,
                "observed_sha256": file_sha256(ROOT / path),
            }
            for c, run, path in CASES
        ],
    }
    protocol_path = PROOF / "diagnostic-protocol.json"
    if protocol_path.exists():
        if json.loads(protocol_path.read_text()) != protocol:
            raise ValueError("The frozen diagnostic protocol changed")
    else:
        atomic_write_json(protocol_path, protocol)
    code_hash = code_fingerprint(ROOT)
    script_hash = file_sha256(ROOT / "scripts/diagnose_expression_v2.py")
    service = ScientificAnalysisService(
        ROOT / "data/registry/sccellfie/human", gene_identity_root=ROOT / "data/registry/gene_identity"
    )
    items = []
    for context, source_id, observed_path in CASES:
        old = ROOT / "data/derived/runs" / source_id
        original = json.loads((old / "manifest.json").read_text())
        request = CreateRunRequest.model_validate({**original["request"], "mode": "validation"})
        model = registry.model_for(context)
        dataset = RegistryEntry(
            {
                **registry.dataset_for(context).payload,
                "observed_path": observed_path,
                "observed_sha256": file_sha256(ROOT / observed_path),
                "validation_batch_key": "gem_group",
            },
            ROOT,
        )
        new_id = (
            "run_"
            + hashlib.sha256(
                f"{source_id}:expression-diagnostic:{code_hash}:{script_hash}".encode()
            ).hexdigest()[:16]
        )
        out = PROOF / "recomputed" / new_id
        out.mkdir(parents=True, exist_ok=False)
        shutil.copy2(old / "predicted.h5ad", out / "predicted.h5ad")
        result = service.run(new_id, request, model, dataset, out / "predicted.h5ad", out)
        if result.summary["warnings"]:
            raise ValueError(result.summary["warnings"])
        document = json.loads((out / "validation_metrics.json").read_text())
        c = prepare_log_expression(ad.read_h5ad(dataset.path("control_path")), "log1p_cp10k")
        p, _ = _select_prediction_population(ad.read_h5ad(out / "predicted.h5ad"), "gene", "AAMP")
        p = prepare_log_expression(p, "log1p_cp10k")
        o = ad.read_h5ad(dataset.path("observed_path"))
        o = prepare_log_expression(o[o.obs["gene"].astype(str).str.upper() == "AAMP"].copy(), "log1p_cp10k")
        c, p = [_expression_view(x, "X_hvg", model.path("gene_list_path"), strict=True) for x in (c, p)]
        assert c is not None and p is not None
        # Apply the same frozen gene identity and common-column selection as
        # the service. No observed values are filled, imputed or duplicated.
        o = _expression_view(o, "X_hvg", model.path("gene_list_path"))
        adapter = GeneIdentityAdapter.load(ROOT / "data/registry/gene_identity", service.database_root)
        c, p, o = [adapter.adapt(x)[0] for x in (c, p, o)]
        (c, p, o), _, _ = _align_sources(c, p, o)
        c, p, o, matching = _match_validation_batches(c, p, o, "gem_group")
        official = official_expression_metrics(c, p, o)
        official_mse = official["metrics"]["mse_delta"]
        if isinstance(official_mse, dict):
            official_mse = official_mse["AAMP"]
        if not np.isclose(official_mse, document["expression"]["mse"], rtol=1e-5, atol=1e-8):
            raise ValueError("Official CellEval and service MSE disagree")
        atomic_write_json(out / "official_cell_eval_expression.json", official)
        summary = RunSummary.model_validate(result.summary)
        atomic_write_json(out / "summary.json", summary.model_dump(mode="json"))
        (out / "report.html").write_text(_render_report(summary), encoding="utf-8")
        atomic_write_json(
            out / "manifest.json",
            {
                "request": request.model_dump(mode="json"),
                "assets": {
                    **original["assets"],
                    "observed_sha256": dataset.payload["observed_sha256"],
                    "model_expression_scale": "log1p_cp10k",
                    "dataset_expression_scale": "log1p_cp10k",
                },
                "code_sha256": code_hash,
                "analysis_script_sha256": script_hash,
                "prediction_reused": True,
                "reanalysis_of": source_id,
                "original_manifest_sha256": file_sha256(old / "manifest.json"),
                "diagnostic_protocol_sha256": file_sha256(PROOF / "diagnostic-protocol.json"),
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
            "population_matching": matching,
            "expression": document["expression"],
            "differential_expression": document["differential_expression"],
            "official_cell_eval": official,
            "held_out_validation": False,
        }
        items.append(item)
        print(
            f"{context}: MSE/baseline={document['expression']['mse_relative_to_no_change']:.4f}, "
            f"DE overlap={document['differential_expression']['overlap_at_n']}",
            flush=True,
        )
    assert_originals(baseline)
    atomic_write_json(
        output_report, {"protocol": protocol, "items": items, "all_original_files_unchanged": True}
    )
    pd.DataFrame([{"context": x["request"]["cell_line"], **x["expression"]} for x in items]).to_csv(
        PROOF / "expression-diagnostics.csv", index=False
    )


if __name__ == "__main__":
    main()
