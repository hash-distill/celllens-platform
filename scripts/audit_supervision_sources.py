"""Inspect original assay slots for hidden full-gene supervision, without reading expression."""

import collections
import json
from pathlib import Path

import fsspec
import h5py
import numpy as np

from backend.app.core.errors import ScientificContractError
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.gene_identity import GeneIdentityAdapter
from scripts.extract_replogle_k562 import decode_categorical, decode_strings, open_group

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "reports/metabolic-full-coverage-2026-10-09"


def gene_values(var):
    for name in (
        "gene_name",
        "gene_symbol",
        "gene_symbols",
        "feature_name",
        str(var.attrs.get("_index", "_index")),
    ):
        if name not in var:
            continue
        item = var[name]
        if isinstance(item, h5py.Dataset):
            yield name, decode_strings(item[:])
        elif isinstance(item, h5py.Group) and "codes" in item and "categories" in item:
            yield name, decode_categorical(item)


def inspect_panel(adapter, var):
    panels = []
    for field, symbols in gene_values(var):
        identifiers = collections.Counter()
        rejected = []
        for symbol in symbols:
            try:
                identity = adapter.resolve(symbol)
            except ScientificContractError:
                rejected.append(symbol)
                continue
            if identity["hgnc_id"] in adapter.by_id:
                identifiers[identity["hgnc_id"]] += 1
        panels.append(
            {
                "field": field,
                "features": len(symbols),
                "metabolic_identities_present": len(identifiers),
                "duplicate_metabolic_identities": [i for i, n in identifiers.items() if n > 1],
                "ambiguous_metabolic_symbols": rejected,
                "missing_metabolic_genes": sorted(
                    adapter.by_id[i] for i in adapter.by_id if i not in identifiers
                ),
                "hgnc_ids_present": sorted(identifiers),
            }
        )
    return sorted(panels, key=lambda panel: -panel["metabolic_identities_present"])


def main():
    output = PROOF / "supervision-source-slots.json"
    if output.exists():
        raise ValueError(f"Preserve supervision inventory: {output}")
    source_inventory = PROOF / "original-source-inventory.json"
    sources = json.loads(source_inventory.read_text())
    adapter = GeneIdentityAdapter.load(
        ROOT / "data/registry/gene_identity", ROOT / "data/registry/sccellfie/human"
    )
    filesystem = fsspec.filesystem("hf")
    records = []
    union = set()
    for source in sources:
        url = f"hf://datasets/{source['repo']}@{source['revision']}/{source['filename']}"
        with filesystem.open(url, "rb", block_size=1 << 20, cache_type="blockcache") as stream:
            with h5py.File(stream, "r") as h5:
                slots = []
                for parent_path, matrix_name in (("", "X"), ("raw", "X")):
                    if parent_path and parent_path not in h5:
                        continue
                    parent = open_group(h5, parent_path) if parent_path else h5
                    if "var" not in parent or matrix_name not in parent:
                        continue
                    matrix = parent[matrix_name]
                    shape = (
                        list(matrix.shape)
                        if isinstance(matrix, h5py.Dataset)
                        else np.asarray(matrix.attrs["shape"], dtype=np.int64).tolist()
                    )
                    panels = inspect_panel(adapter, open_group(parent, "var"))
                    slots.append(
                        {
                            "matrix_slot": f"{parent_path}/{matrix_name}".lstrip("/"),
                            "shape": shape,
                            "feature_panels": panels,
                        }
                    )
                layers = []
                if "layers" in h5:
                    for name, matrix in open_group(h5, "layers").items():
                        shape = (
                            list(matrix.shape)
                            if isinstance(matrix, h5py.Dataset)
                            else np.asarray(matrix.attrs["shape"], dtype=np.int64).tolist()
                        )
                        layers.append({"name": name, "shape": shape, "same_feature_axis_as_X": True})
                present = set()
                for slot in slots:
                    if slot["feature_panels"]:
                        present |= set(slot["feature_panels"][0]["hgnc_ids_present"])
                union |= present
                record = {
                    "cell_line": source["cell_line"],
                    "source": source,
                    "root_keys": list(h5.keys()),
                    "matrix_slots": slots,
                    "layers": layers,
                    "metabolic_identities_available_in_any_slot": len(present),
                    "fully_supervised_feature_axis_available": len(present) == 931,
                    "expression_values_read": False,
                    "missing_metabolic_genes": sorted(
                        adapter.by_id[i] for i in adapter.by_id if i not in present
                    ),
                }
                records.append(record)
                print(
                    f"{source['cell_line']}: slots={[s['matrix_slot'] for s in slots]}, "
                    f"metabolic identities={len(present)}/931, layers={[s['name'] for s in layers]}",
                    flush=True,
                )
    atomic_write_json(
        output,
        {
            "source_inventory_sha256": file_sha256(source_inventory),
            "gene_identity": adapter.provenance,
            "sources": records,
            "union_metabolic_identities": len(union),
            "union_missing_genes": sorted(adapter.by_id[i] for i in adapter.by_id if i not in union),
            "scope": "feature identity and matrix layout; no expression supervision extracted",
            "missing_genes_treated_as_zero": False,
        },
    )


if __name__ == "__main__":
    main()
