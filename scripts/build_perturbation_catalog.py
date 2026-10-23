"""Build a complete fixed-revision obs-only catalog; never read expression X.

Run from repository root: python -m scripts.build_perturbation_catalog
Only the new catalog and reports/measured-first-2026-10-22 are written.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import tomllib
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, cast

from backend.app.core.registry import AssetRegistry
from backend.app.core.run_manifest import atomic_write_json
from backend.app.services.perturbation_catalog import (
    CONTEXTS,
    SOURCE,
    normalize_context,
    normalize_target,
    query_pairs,
    seal_document,
)

ROOT = Path(__file__).resolve().parents[1]


def read_labels(node: Any) -> list[str]:
    """Decode every source row, rejecting missing or corrupt categorical labels."""
    import h5py

    def decode(value: Any) -> str:
        return value.decode() if isinstance(value, bytes) else str(value)

    if isinstance(node, h5py.Group):
        categories = [decode(value) for value in cast(h5py.Dataset, node["categories"])[:]]
        codes = cast(h5py.Dataset, node["codes"])[:]
        if any(int(code) < 0 or int(code) >= len(categories) for code in codes):
            raise ValueError("Invalid or missing categorical source label")
        return [categories[int(code)] for code in codes]
    return [decode(value) for value in node[:]]


def parse_official_split(content: bytes, line: str) -> dict[str, Any]:
    filename = f"{line.lower()}.toml"
    url = f"https://huggingface.co/datasets/{SOURCE['repo']}/raw/{SOURCE['revision']}/{filename}"
    split = tomllib.loads(content.decode())["fewshot"][f"replogle.{line.lower()}"]
    return {
        "file": filename,
        "url": url,
        "revision": SOURCE["revision"],
        "sha256": hashlib.sha256(content).hexdigest(),
        "test": sorted(
            {normalize_target(gene) for gene in split.get("test", []) if str(gene).upper() != "NON-TARGETING"}
        ),
        "val": sorted(
            {normalize_target(gene) for gene in split.get("val", []) if str(gene).upper() != "NON-TARGETING"}
        ),
        "declared_test_entries_including_control": len(split.get("test", [])),
        "declared_val_entries_including_control": len(split.get("val", [])),
        "training_exclusion_verified": False,
        "generalization_verified": False,
    }


def aggregate_counts(cell_lines: Any, perturbations: Any) -> dict[str, Any]:
    if len(cell_lines) != len(perturbations) or len(cell_lines) == 0:
        raise ValueError("Complete obs columns must be nonempty and have the same length")
    counts = Counter(
        (normalize_context(str(line)), normalize_target(str(target), allow_control=True))
        for line, target in zip(cell_lines, perturbations, strict=True)
    )
    totals: Counter[str] = Counter()
    for (line, _), count in counts.items():
        totals[line] += count
    return {
        "context_totals": dict(sorted(totals.items())),
        "counts": [
            {"cell_line": line, "perturbation": target, "cell_count": count}
            for (line, target), count in sorted(counts.items())
        ],
    }


def build(root: Path) -> dict[str, Any]:
    import fsspec
    import h5py

    source_url = f"hf://datasets/{SOURCE['repo']}@{SOURCE['revision']}/{SOURCE['file']}"
    fs = fsspec.filesystem("hf")
    info = fs.info(source_url)
    print("Range-reading only obs.cell_line and obs.gene from the pinned H5AD", flush=True)
    with fs.open(source_url, "rb", block_size=1 << 20, cache_type="blockcache") as stream:
        with h5py.File(stream, "r") as handle:
            obs = cast(h5py.Group, handle["obs"])
            lines = read_labels(obs["cell_line"])
            targets = read_labels(obs["gene"])
            index_name = obs.attrs.get("_index", "_index")
            if len(lines) != cast(h5py.Dataset, obs[index_name]).shape[0]:
                raise ValueError("Source metadata does not cover the complete obs index")
            digest = hashlib.sha256()
            for line, target in zip(lines, targets, strict=True):
                digest.update(json.dumps([str(line), str(target)], separators=(",", ":")).encode() + b"\n")
            aggregated = aggregate_counts(lines, targets)
            if sum(aggregated["context_totals"].values()) != len(lines):
                raise ValueError("Aggregated rows do not match the full obs input")
        fetched = getattr(getattr(stream, "cache", None), "total_requested_bytes", None)
    report = root / "reports/measured-first-2026-10-22"
    report.mkdir(parents=True, exist_ok=True)
    official = {}
    for line in CONTEXTS:
        filename = f"{line.lower()}.toml"
        url = f"https://huggingface.co/datasets/{SOURCE['repo']}/raw/{SOURCE['revision']}/{filename}"
        with urllib.request.urlopen(url, timeout=60) as response:
            content = response.read()
        official[line] = parse_official_split(content, line)
        (report / f"official-{filename}").write_bytes(content)
    document = seal_document(
        {
            "schema_version": 1,
            "source": SOURCE,
            "metadata_complete": True,
            "metadata": {
                "columns": ["obs.cell_line", "obs.gene"],
                "n_obs": len(lines),
                "sha256": digest.hexdigest(),
                "row_digest_encoding": "source order JSON [cell_line,gene] + LF",
                "source_file_size": info["size"],
                "range_requested_bytes": fetched,
                "expression_read": False,
            },
            **aggregated,
            "official_splits": official,
        }
    )
    atomic_write_json(root / "data/registry/perturbation_catalog.json", document)
    from types import SimpleNamespace

    container = SimpleNamespace(
        settings=SimpleNamespace(project_root=root), registry=AssetRegistry(root, root / "data/registry")
    )
    result = query_pairs(container, availability="missing", model_supported=True, limit=100000)
    if not result["source_verified"]:
        raise ValueError("Generated catalog did not pass reader verification")
    atomic_write_json(
        report / "catalog-summary.json",
        {"source": result["source"], "metadata": document["metadata"], "summary": result["summary"]},
    )
    with (report / "model-supported-without-source.csv").open("w", encoding="utf-8-sig", newline="") as out:
        fields = [
            "cell_line",
            "perturbation",
            "source_cell_count",
            "source_status",
            "model_supported",
            "official_split",
            "training_exclusion_verified",
            "generalization_verified",
        ]
        writer = csv.DictWriter(out, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(result["items"])
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2), flush=True)
    return document


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    arguments = parser.parse_args()
    build(arguments.root.resolve())
