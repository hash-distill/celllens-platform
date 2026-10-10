"""SE gene queries with explicit latent layout and no missing-embedding fallback.

This decoder does not establish ST/SE checkpoint compatibility. The experimental
runner records that status separately and cannot activate the production registry.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import torch

from backend.app.core.errors import ScientificContractError
from backend.app.core.run_manifest import file_sha256
from backend.app.services.gene_identity import GeneIdentityAdapter


def validate_query_keys(keys: list[str], available: set[str]) -> None:
    if len(set(keys)) != len(keys):
        raise ScientificContractError("Duplicate SE query keys")
    missing = set(keys) - available
    if missing:
        raise ScientificContractError(f"SE query embeddings missing: {sorted(missing)}")


def resolve_read_depths(value: float | np.ndarray, n_cells: int) -> np.ndarray:
    depths = np.asarray(value, dtype=np.float32)
    if depths.ndim == 0:
        depths = np.full(n_cells, float(depths), dtype=np.float32)
    if depths.shape != (n_cells,):
        raise ScientificContractError("SE per-cell depth shape must match latent rows")
    if not np.isfinite(depths).all():
        raise ScientificContractError("SE per-cell depth must be finite")
    return depths


def positive_log_expression_mean(expression: np.ndarray) -> np.ndarray:
    values = np.asarray(expression)
    if values.ndim != 2 or not np.isfinite(values).all() or np.any(values < 0):
        raise ScientificContractError("Depth estimation requires finite nonnegative source log expression")
    positive = np.sum(values > 0, axis=1)
    if np.any(positive == 0):
        raise ScientificContractError("Control has no positive measured target expression")
    # This is the installed SE training mu condition, estimated over measured
    # features rather than the randomly sampled training task. No genes filled.
    return (values.sum(axis=1) / positive).astype(np.float32)


def decoder_inputs(
    cells: torch.Tensor,
    genes: torch.Tensor,
    *,
    read_depth: float,
    cell_dim: int = 2048,
    dataset_dim: int = 10,
) -> torch.Tensor:
    if cells.ndim != 2 or cells.shape[1] != cell_dim + dataset_dim:
        raise ScientificContractError("Wrong SE latent width")
    if genes.ndim != 2 or genes.shape[1] != cell_dim:
        raise ScientificContractError("Wrong SE gene embedding width")
    if not torch.isfinite(cells).all() or not torch.isfinite(genes).all() or not np.isfinite(read_depth):
        raise ScientificContractError("SE decoder inputs must be finite")
    # The official resize helper concatenates the dataset coordinates; passing
    # all 2058 coordinates as the cell block would duplicate the final ten.
    from state.emb.nn.model import StateEmbeddingModel

    depth = torch.full((cells.shape[0],), read_depth, dtype=cells.dtype, device=cells.device)
    return StateEmbeddingModel.resize_batch(
        cells[:, :cell_dim], genes, task_counts=depth, ds_emb=cells[:, cell_dim:]
    )


def metabolic_query_keys(adapter: GeneIdentityAdapter, available: set[str]) -> tuple[list[str], list[str]]:
    by_id: dict[str, list[str]] = {}
    for key in available:
        row = adapter.document["symbol_lookup"].get(key.upper())
        if row and len(row["hgnc_ids"]) == 1:
            by_id.setdefault(row["hgnc_ids"][0], []).append(key)
    symbols = sorted(adapter.document["database_genes"])
    keys = []
    for symbol in symbols:
        identifier = adapter.document["database_genes"][symbol]["hgnc_id"]
        matches = by_id.get(identifier, [])
        if len(matches) != 1:
            raise ScientificContractError(f"SE query identity is missing or ambiguous: {symbol}: {matches}")
        keys.append(matches[0])
    validate_query_keys(keys, available)
    return symbols, keys


class SEGeneDecoder:
    def __init__(self, model_root: Path, *, device: str = "cpu"):
        from safetensors import safe_open
        from state.emb.nn.model import SkipBlock
        from torch import nn

        manifest = json.loads((model_root / "source_manifest.json").read_text(encoding="utf-8"))
        if (
            manifest["repo"] != "arcinstitute/SE-600M"
            or manifest["revision"] != "5a9a80f44f7ce32ce57059933ef0d735d7c10ce5"
        ):
            raise ScientificContractError("Unregistered SE checkpoint source")
        for filename in ("model.safetensors", "protein_embeddings.pt", "config.yaml"):
            if file_sha256(model_root / filename) != manifest["files"][filename]:
                raise ScientificContractError(f"SE asset hash mismatch: {filename}")
        with torch.device("meta"):
            self.gene_encoder = nn.Sequential(nn.Linear(5120, 2048), nn.LayerNorm(2048), nn.SiLU())
            self.decoder = nn.Sequential(SkipBlock(4107), SkipBlock(4107), nn.Linear(4107, 1))
        with safe_open(model_root / "model.safetensors", framework="pt", device="cpu") as tensors:
            for prefix, module in (
                ("gene_embedding_layer.", self.gene_encoder),
                ("binary_decoder.", self.decoder),
            ):
                weights = {
                    key[len(prefix) :]: tensors.get_tensor(key)
                    for key in tensors.keys()
                    if key.startswith(prefix)
                }
                module.load_state_dict(weights, strict=True, assign=True)
            self.checkpoint_metadata = tensors.metadata()
        self.gene_encoder = self.gene_encoder.to(device).eval()
        self.decoder = self.decoder.to(device).eval()
        self.protein: Any = torch.load(
            model_root / "protein_embeddings.pt", map_location="cpu", weights_only=True, mmap=True
        )
        self.device = device
        self.provenance = {
            "source": manifest,
            "checkpoint_metadata": self.checkpoint_metadata,
            "precision": "float32",
            "latent_layout": "cell2048 + dataset10",
            "raw_output_scale": "log1p expression regression target",
            "compatibility_verified": False,
        }

    @torch.inference_mode()
    def decode(
        self, latent: np.ndarray, keys: list[str], *, read_depth: float | np.ndarray = 4.0
    ) -> np.ndarray:
        validate_query_keys(keys, set(self.protein))
        depths = resolve_read_depths(read_depth, len(latent))
        cells = torch.as_tensor(latent, dtype=torch.float32, device=self.device)
        protein = torch.stack([self.protein[key] for key in keys]).to(self.device, dtype=torch.float32)
        genes = self.gene_encoder(protein)
        output = np.empty((len(latent), len(keys)), dtype=np.float32)
        for i in range(len(latent)):
            for j in range(0, len(keys), 64):
                joined = decoder_inputs(cells[i : i + 1], genes[j : j + 64], read_depth=float(depths[i]))
                values = self.decoder(joined).reshape(-1).cpu().numpy()
                output[i, j : j + len(values)] = values
        if not np.isfinite(output).all():
            raise ScientificContractError("SE decoder produced non-finite expression")
        return output
