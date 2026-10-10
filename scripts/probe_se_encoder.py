"""Re-encode source cells with pinned SE epoch16 and compare original latents."""

import json
from pathlib import Path

import anndata as ad
import numpy as np
import torch
from omegaconf import OmegaConf
from safetensors import safe_open

from backend.app.core.run_manifest import atomic_write_json, file_sha256

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "reports/metabolic-full-coverage-2026-10-09"


def main():
    from state.emb.data.loader import FilteredGenesCounts, VCIDatasetSentenceCollator
    from state.emb.nn.model import StateEmbeddingModel

    model_root = ROOT / "models/se600m-epoch16"
    source = json.loads((model_root / "source_manifest.json").read_text())
    for filename in ("config.yaml", "model.safetensors", "protein_embeddings.pt"):
        if file_sha256(model_root / filename) != source["files"][filename]:
            raise ValueError(f"SE probe asset hash mismatch: {filename}")
    cfg = OmegaConf.load(model_root / "config.yaml")
    with torch.device("meta"):
        model = StateEmbeddingModel(
            token_dim=5120,
            d_model=2048,
            nhead=16,
            d_hid=2048,
            nlayers=16,
            output_dim=2048,
            dropout=0.0,
            cfg=cfg,
        )
    with safe_open(model_root / "model.safetensors", framework="pt", device="cpu") as handle:
        state = {key: handle.get_tensor(key) for key in handle.keys()}
        # The constructor leaves a None placeholder; register the checkpoint's
        # actual embedding module before strict state loading.
        del model.pe_embedding
        model.add_module("pe_embedding", torch.nn.Embedding.from_pretrained(state["pe_embedding.weight"]))
        model.load_state_dict(state, strict=True, assign=True)
    del state
    protein = torch.load(model_root / "protein_embeddings.pt", weights_only=True, mmap=True)
    protein_values = list(protein.values())
    protein_layer = model.get_submodule("pe_embedding")
    if not isinstance(protein_layer, torch.nn.Embedding):
        raise ValueError("Checkpoint protein table was not registered as an embedding")
    if protein_layer.weight.shape != (len(protein_values), 5120):
        raise ValueError("Published checkpoint protein table dimensions differ from protein dictionary")
    for i in range(0, len(protein_values), 128):
        expected = torch.stack(protein_values[i : i + 128])
        if not torch.equal(protein_layer.weight[i : i + len(expected)], expected):
            raise ValueError("Checkpoint protein table order differs from published protein dictionary")
    del expected, protein_values
    # These two heads are unused during encoding. Remove them after strict weight
    # validation to fit the encoder alongside the user's existing GPU workload.
    model.binary_decoder = torch.nn.Identity()
    model.add_module("dataset_encoder", torch.nn.Identity())
    model = model.to("cuda", dtype=torch.bfloat16).eval()
    frame = ad.read_h5ad(PROOF / "se-controls/k562.h5ad")[:4].copy()
    dataset = FilteredGenesCounts(
        cfg, adata=frame, adata_name="probe", protein_embeds=protein, gene_column=None
    )
    collator = VCIDatasetSentenceCollator(
        cfg,
        valid_gene_mask=dataset.valid_gene_index,
        ds_emb_mapping_inference=dataset.ds_emb_map,
        is_train=False,
        precision=torch.bfloat16,
    )
    reports = []
    embeddings = {}
    for seed in (42, 43, 44):
        torch.manual_seed(seed)
        np.random.seed(seed)
        encoded = []
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            for i in range(len(frame)):
                batch = collator([dataset[i]])
                _, _, _, latent, ds = model._compute_embedding_for_batch(batch)
                value = torch.cat((latent, model.dataset_embedder(ds)), dim=1)
                encoded.append(value.cpu().float().numpy())
        values = np.concatenate(encoded)
        embeddings[str(seed)] = values
        original = np.asarray(frame.obsm["X_state"])
        cosine = (values[:, :2048] * original[:, :2048]).sum(axis=1) / (
            np.linalg.norm(values[:, :2048], axis=1) * np.linalg.norm(original[:, :2048], axis=1)
        )
        reports.append(
            {
                "seed": seed,
                "cell_cosines": cosine.tolist(),
                "dataset_coordinate_rmse": float(
                    np.sqrt(np.mean((values[:, 2048:] - original[:, 2048:]) ** 2))
                ),
                "full_coordinate_rmse": float(np.sqrt(np.mean((values - original) ** 2))),
            }
        )
        print(json.dumps(reports[-1]), flush=True)
    np.savez_compressed(
        PROOF / "se-compatibility/encoder-probe-latents.npz",
        **embeddings,
        original=np.asarray(frame.obsm["X_state"]),
    )
    atomic_write_json(
        PROOF / "se-compatibility/encoder-probe.json",
        {
            "source": source,
            "cells": 4,
            "context": "K562",
            "precision": "bfloat16",
            "read_scope": "real re-encoding of measured source cells",
            "experiments": reports,
            "exact_training_encoder_provenance_verified": False,
            "note": "Sampling/preprocessing affect embeddings; high similarity alone is not identity proof",
        },
    )


if __name__ == "__main__":
    main()
