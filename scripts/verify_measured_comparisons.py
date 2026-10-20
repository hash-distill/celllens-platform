"""Verify real comparison populations, paired values and selected official Cell-Eval metrics."""

import json
from importlib.metadata import version
from pathlib import Path

import anndata as ad
import numpy as np

from backend.app.config import get_settings
from backend.app.core.registry import AssetRegistry
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.core.storage import RunStore
from backend.app.services.expression_scale import prepare_log_expression
from backend.app.services.gene_identity import GeneIdentityAdapter
from backend.app.services.measured_comparison import load_comparison, observation_for
from backend.app.services.scientific_analysis import (
    _align_sources,
    _expression_view,
    _match_validation_batches,
    _select_prediction_population,
)

ROOT = Path(__file__).resolve().parents[1]


def verify(run_id, registry, adapter):
    from cell_eval import PerturbationAnndataPair, metrics_registry

    doc = load_comparison(ROOT, run_id)
    if doc is None:
        return None
    original_root = ROOT / "data/derived/runs" / run_id
    original = json.loads((original_root / "manifest.json").read_text())
    for filename, entry in original["outputs"].items():
        assert file_sha256(original_root / filename) == entry["sha256"], filename
    context, target = doc["cell_line"], doc["perturbation"]
    model, dataset = registry.model_for(context), registry.dataset_for(context)
    obs = observation_for(ROOT, context, target)
    assert obs is not None
    c, p, o = (
        ad.read_h5ad(dataset.path("control_path")),
        ad.read_h5ad(original_root / "predicted.h5ad"),
        ad.read_h5ad(ROOT / obs["path"]),
    )
    assert not o.obs["source_row"].duplicated().any()
    assert set(o.obs["gene"]) == {target}
    assert set(o.obs["cell_line"]) == {context.lower()}
    p, _ = _select_prediction_population(p, model.payload["perturbation_column"], target)
    embed = model.payload.get("expression_key") or model.payload.get("embed_key")
    panel = model.path("gene_list_path")
    c, p, o = [
        _expression_view(prepare_log_expression(x, "log1p_cp10k"), embed, panel, strict=False)
        for x in (c, p, o)
    ]
    c, p, o, population = _match_validation_batches(c, p, o, "gem_group")
    c, p, o = [adapter.adapt(x)[0] for x in (c, p, o)]
    (c, p, o), genes, _ = _align_sources(c, p, o)
    for name, values in zip(["control", "predicted", "observed"], [c, p, o], strict=True):
        assert doc["parameters"]["population_counts"][name] == values.n_obs
    means = [np.asarray(x.X.mean(axis=0)).reshape(-1).astype(float) for x in (c, p, o)]
    saved = {row["id"]: row for row in doc["genes"]}
    assert len(saved) == len(genes)
    for i, gene in enumerate(genes):
        np.testing.assert_allclose(
            [saved[gene][key] for key in ["control", "predicted", "observed"]],
            [m[i] for m in means],
            rtol=1e-6,
            atol=1e-7,
        )
    pd, od = means[1] - means[0], means[2] - means[0]
    np.testing.assert_allclose(doc["expression"]["mse"], np.mean((pd - od) ** 2), rtol=1e-6)
    np.testing.assert_allclose(doc["expression"]["no_change_mse"], np.mean(od**2), rtol=1e-6)
    key = "verification_perturbation"
    c.obs[key] = "control"
    p.obs[key] = o.obs[key] = target
    pair = PerturbationAnndataPair(
        ad.concat([c, o], index_unique="-"), ad.concat([c, p], index_unique="-"), key, "control"
    )
    official = {}
    for metric, ours in [
        ("mse_delta", "mse"),
        ("mae_delta", "mae"),
        ("pearson_delta", "signed_delta_pearson"),
    ]:
        raw = metrics_registry.compute(metric, pair)
        value = float(raw[target] if isinstance(raw, dict) else raw)
        np.testing.assert_allclose(value, doc["expression"][ours], rtol=1e-5, atol=1e-7)
        official[metric] = value
    return {
        "run_id": run_id,
        "cell_line": context,
        "perturbation": target,
        "official_package_version": version("cell-eval"),
        "official_metrics": official,
        "population_matching": population,
        "all_paired_gene_means_match": True,
        "original_output_hashes_match": True,
        "full_official_profile_executed": False,
    }


def main():
    store = RunStore(get_settings().database_url)
    registry = AssetRegistry(ROOT, ROOT / "data/registry")
    adapter = GeneIdentityAdapter.load(
        ROOT / "data/registry/gene_identity", ROOT / "data/registry/sccellfie/human"
    )
    results = []
    try:
        for run in store.list_runs(limit=100, offset=0)[0]:
            result = verify(run.run_id, registry, adapter)
            if result is not None:
                results.append(result)
                print(result["cell_line"], result["perturbation"], result["official_metrics"], flush=True)
    finally:
        store.engine.dispose()
    atomic_write_json(
        ROOT / "reports/measured-comparison-2026-10-15/official-verification.json", {"items": results}
    )


if __name__ == "__main__":
    main()
