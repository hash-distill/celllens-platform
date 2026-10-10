"""Inspect pinned official metadata before allowing the SE + ST-SE decode route."""

import json
import urllib.request
from pathlib import Path

import fsspec
import h5py
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/metabolic-full-coverage-2026-10-09/se-compatibility"
SE_REVISION = "5a9a80f44f7ce32ce57059933ef0d735d7c10ce5"
ST_REVISION = "d1441f5587ace12c46247b3703c7d25f24f8abb6"
DATA_REVISION = "d790193bb2c93726541a75ca3fa873a92ed44da5"


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def describe(group):
    entries = {}
    for name, item in group.items():
        if isinstance(item, h5py.Dataset):
            entries[name] = {"shape": list(item.shape), "dtype": str(item.dtype)}
            if item.size is not None and item.size <= 30:
                value = item[()]
                if hasattr(value, "tolist"):
                    value = value.tolist()
                entries[name]["value"] = str(value)
        else:
            entries[name] = describe(item)
    return entries


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "se_revision": SE_REVISION,
        "st_revision": ST_REVISION,
        "data_revision": DATA_REVISION,
        "read_scope": "metadata only; no new predictions",
    }
    for context in ("k562", "rpe1", "jurkat", "hepg2"):
        url = f"https://huggingface.co/arcinstitute/st-se-replogle-full/resolve/{ST_REVISION}/{context}_0.99"
        config = fetch(f"{url}/config.yaml")
        hparams = fetch(f"{url}/version_0/hparams.yaml")
        (OUT / f"{context}-config.yaml").write_bytes(config)
        (OUT / f"{context}-hparams.yaml").write_bytes(hparams)
        hp = yaml.safe_load(hparams)
        report[context] = {
            "config": yaml.safe_load(config),
            "hparams_without_gene_names": {k: v for k, v in hp.items() if k != "gene_names"},
        }
    filesystem = fsspec.filesystem("hf")
    path = f"hf://datasets/arcinstitute/State-Replogle-Filtered@{DATA_REVISION}/replogle_concat.h5ad"
    with filesystem.open(path, "rb", block_size=1 << 20, cache_type="blockcache") as stream:
        with h5py.File(stream, "r") as h5:
            report["source_metadata"] = {
                "attrs": {k: str(v) for k, v in h5.attrs.items()},
                "obsm": describe(h5["obsm"]),
                "uns": describe(h5["uns"]),
            }
    report["compatible_encoder_provenance_verified"] = False
    report["status"] = "requires_checkpoint_provenance_or_numeric_equivalence_validation"
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"source_metadata": report["source_metadata"], "status": report["status"]}), flush=True)


if __name__ == "__main__":
    main()
