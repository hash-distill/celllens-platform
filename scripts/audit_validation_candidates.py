"""Freeze observed perturbation availability before a wider prediction evaluation."""

import collections
import json
from pathlib import Path

import anndata as ad
import fsspec
import h5py
import numpy as np
import torch

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.gene_identity import GeneIdentityAdapter
from scripts.extract_replogle_k562 import decode_categorical, open_dataset, open_group
from scripts.prepare_se_controls import REVISION

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "reports/metabolic-full-coverage-2026-10-09"


def main():
    output = PROOF / "validation-candidate-inventory.json"
    if output.exists():
        raise ValueError(f"Preserve frozen validation candidates: {output}")
    adapter = GeneIdentityAdapter.load(
        ROOT / "data/registry/gene_identity", ROOT / "data/registry/sccellfie/human"
    )
    filesystem = fsspec.filesystem("hf")
    url = f"hf://datasets/arcinstitute/State-Replogle-Filtered@{REVISION}/replogle_concat.h5ad"
    contexts = {}
    common = None
    with filesystem.open(url, "rb", block_size=1 << 20, cache_type="blockcache") as stream:
        with h5py.File(stream, "r") as h5:
            obs = open_group(h5, "obs")
            lines = decode_categorical(open_group(obs, "cell_line"))
            perts = decode_categorical(open_group(obs, "gene"))
            batches = np.asarray(open_dataset(obs, "gem_group")[:])
            for context in ("K562", "RPE1", "Jurkat", "HepG2"):
                slug = context.lower()
                control_path = PROOF / f"se-controls/{slug}.h5ad"
                control = ad.read_h5ad(control_path)
                control_batches = np.asarray(control.obs["gem_group"])
                model_path = ROOT / f"models/st-se-full-{slug}/pert_onehot_map.pt"
                source = json.loads((model_path.parent / "source_manifest.json").read_text())
                if (
                    source["repo"] != "arcinstitute/st-se-replogle-full"
                    or source["revision"] != "d1441f5587ace12c46247b3703c7d25f24f8abb6"
                    or file_sha256(model_path) != source["files"]["pert_onehot_map.pt"]
                ):
                    raise ValueError("Perturbation map does not match the verified official source")
                # This published map contains NumPy scalar keys as well as tensors.
                # Load the original structure only after its pinned publisher hash
                # is verified; this does not relax loading for unknown checkpoints.
                model_genes = set(torch.load(model_path, map_location="cpu", weights_only=False))
                counts = collections.Counter(perts[lines == context.lower()].tolist())
                candidates = []
                for gene in sorted(model_genes & counts.keys() - {"non-targeting"}):
                    if counts[gene] < 64:
                        continue
                    rows = (lines == context.lower()) & (perts == gene)
                    observed_batches = set(batches[rows])
                    shared_controls = int(np.isin(control_batches, list(observed_batches)).sum())
                    if shared_controls < 32:
                        continue
                    identity = adapter.resolve(gene)
                    candidates.append(
                        {
                            "gene": gene,
                            "measured_cells": counts[gene],
                            "control_cells_in_shared_batches": shared_controls,
                            "metabolic_gene": identity["hgnc_id"] in adapter.by_id,
                            "hgnc_id": identity["hgnc_id"],
                        }
                    )
                candidates.sort(key=lambda row: (not row["metabolic_gene"], row["gene"]))
                candidate_genes = {row["gene"] for row in candidates}
                common = candidate_genes if common is None else common & candidate_genes
                contexts[context] = {
                    "model_perturbation_keys": len(model_genes),
                    "observed_perturbations": len(counts) - int("non-targeting" in counts),
                    "aamp_measured_cells": counts.get("AAMP", 0),
                    "eligible_candidates": len(candidates),
                    "selected_for_next_diagnostic": candidates[:5],
                    "candidates": candidates,
                    "source_control_sha256": file_sha256(control_path),
                    "model_perturbation_map_sha256": file_sha256(model_path),
                    "training_membership_verified": False,
                }
                print(
                    f"{context}: measured AAMP={counts.get('AAMP', 0)}, eligible={len(candidates)}, "
                    f"selected={[row['gene'] for row in candidates[:5]]}",
                    flush=True,
                )
    atomic_write_json(
        output,
        {
            "source_repo": "arcinstitute/State-Replogle-Filtered",
            "source_revision": REVISION,
            "read_scope": "observed identities and batch metadata; no expression or prediction values",
            "selection_rule": "at least 64 measured perturbed cells, 32 sampled controls in shared batches, "
            "registered model key; metabolic identity then gene-name order",
            "selection_uses_prediction_outcomes": False,
            "common_eligible_perturbations": sorted(common or []),
            "contexts": contexts,
            "held_out_validation": False,
            "limitations": "Observed data availability does not prove checkpoint training exclusion",
        },
    )


if __name__ == "__main__":
    main()
