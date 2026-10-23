"""Register a reproducible 1,024-cell K562 subset without changing historical inputs."""

import argparse
import json
from pathlib import Path

import numpy as np

from backend.app.core.registry import AssetRegistry, RegistryEntry
from backend.app.core.run_manifest import atomic_write_json, file_sha256

SOURCE_ID = "replogle-k562-control-v1"
DATASET_ID = "replogle-k562-control-1024-v2"
CONTROL_PATH = "data/raw/replogle-k562/control-1024-v2.h5ad"
CONTROL_CELLS = 1024
SEED = 42


def prepare_subset(root: Path) -> dict:
    import anndata as ad

    root = root.resolve()
    registry_path = root / "data/registry/datasets.json"
    before = registry_path.read_bytes()
    document = json.loads(before)
    registry = AssetRegistry(root, registry_path.parent)
    existing = [row for row in document["datasets"] if row["id"] == DATASET_ID]
    if existing:
        active = registry.dataset_for("K562")
        if len(existing) != 1 or active.payload["id"] != DATASET_ID:
            raise ValueError("The versioned K562 subset is not the active dataset")
        registry.verify_entry(active, "control_path", "control_sha256")
        frame = ad.read_h5ad(active.path("control_path"), backed="r")
        try:
            if frame.n_obs != CONTROL_CELLS:
                raise ValueError("The registered K562 subset does not contain 1,024 cells")
        finally:
            frame.file.close()
        return {"changed": False, "dataset_id": DATASET_ID, "control_cells": CONTROL_CELLS}

    parents = [row for row in document["datasets"] if row["id"] == SOURCE_ID]
    if len(parents) != 1:
        raise ValueError("Expected one registered historical K562 control dataset for initial preparation")
    parent = RegistryEntry(parents[0], root)
    parent_hash = registry.verify_entry(parent, "control_path", "control_sha256")
    source = ad.read_h5ad(parent.path("control_path"))
    if source.n_obs < CONTROL_CELLS or not source.n_vars or not source.obs_names.is_unique:
        raise ValueError("K562 source needs at least 1,024 unique cells and a nonempty gene panel")
    for column, expected in (("cell_line", "k562"), ("gene", "non-targeting")):
        if column not in source.obs or set(source.obs[column].astype(str).str.lower()) != {expected}:
            raise ValueError(f"K562 control has invalid {column} labels")
    selected = np.sort(np.random.default_rng(SEED).choice(source.n_obs, size=CONTROL_CELLS, replace=False))
    subset = source[selected].copy()
    subset.obs["celllens_parent_row"] = selected
    subset.uns["celllens_control_subset"] = {
        "parent_dataset_id": SOURCE_ID,
        "parent_path": parent.payload["control_path"],
        "parent_sha256": parent_hash,
        "parent_cells": source.n_obs,
        "sampling_seed": SEED,
        "sampling_limit": CONTROL_CELLS,
        "selection": "sorted random parent rows without replacement; unchanged expression and gene order",
        "source_revision_verified": False,
    }
    output = root / CONTROL_PATH
    if output.exists():
        raise ValueError("Unregistered subset already exists; refusing to overwrite it")
    output.parent.mkdir(parents=True, exist_ok=True)
    subset.write_h5ad(output, compression="gzip")
    if file_sha256(parent.path("control_path")) != parent_hash or registry_path.read_bytes() != before:
        raise ValueError("The source or dataset registry changed during preparation; registration stopped")
    subset_hash = file_sha256(output)
    active = {
        **parents[0],
        "id": DATASET_ID,
        "control_path": CONTROL_PATH,
        "control_sha256": subset_hash,
        "enabled": True,
    }
    active.pop("disabled_reason", None)
    archived = {
        **parents[0],
        "enabled": False,
        "disabled_reason": "Historical 3,000-cell input retained; new tasks use the 1,024-cell v2 subset",
    }
    document["datasets"] = [active] + [
        archived if row["id"] == SOURCE_ID else row for row in document["datasets"]
    ]
    audit = root / "reports/k562-control-1024-2026-10-23"
    audit.mkdir(parents=True, exist_ok=True)
    with (audit / "datasets-before.json").open("xb") as stream:
        stream.write(before)
    result = {
        "changed": True,
        "dataset_id": DATASET_ID,
        "control_path": CONTROL_PATH,
        "control_sha256": subset_hash,
        "control_cells": CONTROL_CELLS,
        "gene_count": subset.n_vars,
        "parent": subset.uns["celllens_control_subset"],
    }
    atomic_write_json(output.with_suffix(".manifest.json"), result)
    atomic_write_json(registry_path, document)
    atomic_write_json(audit / "prepared.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    print(json.dumps(prepare_subset(arguments.root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
