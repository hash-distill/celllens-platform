"""Generate ready-to-paste registry JSON blocks with real SHA-256 values.

Usage (run after you have downloaded the assets):

    uv run python scripts/register_assets.py                 # audit + print blocks
    uv run python scripts/register_assets.py --write         # also patch the JSON files

Files it looks for (relative to the project root):

    data/registry/state_k562_genes.txt                 <- from var_dims.pkl
    configs/models/state-replogle-k562.yaml            (already present)
    data/raw/replogle-k562/control.h5ad
    data/raw/replogle-k562/heldout.h5ad
    models/state-replogle-k562/checkpoints/final.ckpt
    models/state-replogle-k562/{config.yaml,var_dims.pkl,pert_onehot_map.pt,
                               batch_onehot_map.pkl,cell_type_onehot_map.pkl}
    data/registry/sccellfie/human/*                    (+ manifest.json)
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = PROJECT_ROOT / "data" / "registry"

# name -> path relative to project root
ASSET_PATHS = {
    "checkpoint_sha256": "models/state-replogle-k562/checkpoints/final.ckpt",
    "gene_list_sha256": "data/registry/state_k562_genes.txt",
    "config_sha256": "configs/models/state-replogle-k562.yaml",
    "control_sha256": "data/raw/replogle-k562/control.h5ad",
    "observed_sha256": "data/raw/replogle-k562/heldout.h5ad",
    "split_sha256": "configs/splits/replogle-v1.json",
}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_supported_perturbations() -> list[str]:
    """Read the perturbations the model can actually simulate from its one-hot map."""
    map_path = PROJECT_ROOT / "models" / "state-replogle-k562" / "pert_onehot_map.pt"
    if not map_path.is_file():
        return []
    import torch

    mapping = torch.load(map_path, map_location="cpu", weights_only=False)
    return sorted({str(key).strip().upper() for key in mapping if str(key).strip()})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Patch models.json / datasets.json in place")
    args = parser.parse_args()

    supported = _load_supported_perturbations()
    print(f"model supported perturbations: {len(supported)}")

    hashes: dict[str, str] = {}
    print("=== asset audit ===")
    for field, relative in ASSET_PATHS.items():
        path = PROJECT_ROOT / relative
        if not path.is_file():
            print(f"MISSING  {field:<20} {relative}")
            continue
        digest = sha256_of(path)
        hashes[field] = digest
        print(f"OK       {field:<20} {relative}")
        print(f"         sha256={digest}  size={path.stat().st_size}")

    print("\n=== model manifest files (state tx infer needs these in model_dir) ===")
    model_dir = PROJECT_ROOT / "models" / "state-replogle-k562"
    for name in (
        "config.yaml",
        "var_dims.pkl",
        "pert_onehot_map.pt",
        "batch_onehot_map.pkl",
        "batch_onehot_map.torch",
        "cell_type_onehot_map.pkl",
        "cell_type_onehot_map.torch",
    ):
        candidate = model_dir / name
        print(f"{'OK     ' if candidate.is_file() else 'MISSING'}  {name}")

    model_block = {
        "id": "state-replogle-k562-fewshot-v1",
        "cell_line": "K562",
        "code_version": "0.11.1",
        "model_dir": "models/state-replogle-k562",
        "checkpoint_path": "models/state-replogle-k562/checkpoints/final.ckpt",
        "checkpoint_sha256": hashes.get("checkpoint_sha256"),
        "config_path": "configs/models/state-replogle-k562.yaml",
        "config_sha256": hashes.get("config_sha256"),
        "gene_list_path": "data/registry/state_k562_genes.txt",
        "gene_list_sha256": hashes.get("gene_list_sha256"),
        "embed_key": "X_hvg",
        "perturbation_column": "gene",
        "cell_type_column": "cell_line",
        "control_perturbation": "non-targeting",
        "supported_perturbations": supported,
        "license": "Arc State Model Non-Commercial License",
        "enabled": True,
        "expression_scale": "log1p_cp10k",
    }
    dataset_block = {
        "id": "replogle-k562-control-v1",
        "cell_line": "K562",
        "control_path": "data/raw/replogle-k562/control.h5ad",
        "control_sha256": hashes.get("control_sha256"),
        "observed_path": "data/raw/replogle-k562/heldout.h5ad",
        "observed_sha256": hashes.get("observed_sha256"),
        "split_path": "configs/splits/replogle-v1.json",
        "split_sha256": hashes.get("split_sha256"),
        "license": "Replogle et al. 2022 (CC-BY-4.0)",
        "enabled": True,
        "expression_scale": "log1p_cp10k",
    }

    print("\n=== paste into data/registry/models.json -> models[0] ===")
    print(json.dumps(model_block, indent=2, ensure_ascii=False))
    print("\n=== paste into data/registry/datasets.json -> datasets[0] ===")
    print(json.dumps(dataset_block, indent=2, ensure_ascii=False))

    if args.write:
        _patch(REGISTRY / "models.json", "models", model_block)
        _patch(REGISTRY / "datasets.json", "datasets", dataset_block)
        print("\nPatched models.json and datasets.json")
    return 0


def _patch(path: Path, key: str, block: dict) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    rows = document[key]
    for index, row in enumerate(rows):
        if row.get("cell_line") == block["cell_line"]:
            rows[index] = block
            break
    else:
        rows.append(block)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
