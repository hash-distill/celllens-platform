"""Freeze official HGNC identities against the unchanged scCellFie database."""

import hashlib
import io
import json
import urllib.request
from pathlib import Path

import pandas as pd

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.gene_identity import build_identity_document

ROOT = Path(__file__).resolve().parents[1]
HGNC_URL = "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt"
HGNC_SHA256 = "8bf6f686e640dbc864a346484626953621b0500d900d26cd085a35c2782d725d"


def main() -> None:
    database_root = ROOT / "data/registry/sccellfie/human"
    destination = ROOT / "data/registry/gene_identity"
    if destination.exists():
        raise SystemExit("Identity snapshot already exists; inspect it before creating a new version")
    with urllib.request.urlopen(HGNC_URL, timeout=60) as response:
        content = response.read()
    digest = hashlib.sha256(content).hexdigest()
    if digest != HGNC_SHA256:
        raise SystemExit(f"HGNC source changed; review new snapshot before use: {digest}")
    hgnc = pd.read_csv(io.BytesIO(content), sep="\t", dtype=str, keep_default_na=False)
    rxn = pd.DataFrame(json.loads((database_root / "Rxn-Info-Recon2-2.json").read_text()))
    document = build_identity_document(rxn, hgnc)
    destination.mkdir(parents=True)
    path = destination / "human.json"
    path.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    atomic_write_json(
        destination / "manifest.json",
        {
            "schema_version": 1,
            "source": HGNC_URL,
            "source_sha256": digest,
            "database_manifest_sha256": file_sha256(database_root / "manifest.json"),
            "database_gene_count": len(document["database_genes"]),
            "files": {"human.json": file_sha256(path)},
            "policy": "approved, unique previous, unique alias; explicit HGNC ID resolves ambiguity",
        },
    )
    print(
        json.dumps({"database_genes": len(document["database_genes"]), "mapping_sha256": file_sha256(path)})
    )


if __name__ == "__main__":
    main()
