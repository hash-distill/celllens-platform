"""Prepare the pinned public Reactome v98 GMT knowledge resource (no study data)."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path

URL = "https://download.reactome.org/98/ReactomePathways.gmt.zip"
SHA256 = "6056fcd95dc8f09740c8bb64c2765bea1386ce91b9b19cd10bcd45d30451805c"
DEFAULT_DESTINATION = Path(__file__).resolve().parents[1] / "data/registry/pathways/reactome_v98"


def prepare(destination: Path, archive: Path | None = None) -> dict:
    if archive is None:
        with urllib.request.urlopen(URL, timeout=60) as response:
            payload = response.read(5_000_000)
    else:
        payload = archive.read_bytes()
    if hashlib.sha256(payload).hexdigest() != SHA256:
        raise ValueError("Reactome v98 archive SHA-256 mismatch; refusing changed upstream resource")
    with zipfile.ZipFile(io.BytesIO(payload)) as zipped:
        gmt = zipped.read("ReactomePathways.gmt")
    rows = [line.split("\t") for line in gmt.decode("utf-8").splitlines() if line.strip()]
    if not rows or any(len(row) < 3 or not row[1].startswith("R-HSA-") for row in rows):
        raise ValueError("Expected Reactome human-pathway GMT with gene-symbol members")
    if len({row[1] for row in rows}) != len(rows):
        raise ValueError("Duplicate Reactome pathway IDs")
    manifest = {
        "schema_version": 1,
        "resource_id": "reactome-human-gmt-v98",
        "name": "Reactome human pathways",
        "release": "98",
        "release_date": "2026-10-21",
        "retrieved_date": "2026-11-16",
        "species": "Homo sapiens",
        "identifier_type": "gene_symbol",
        "mapping_policy": "Exact case-sensitive GMT member symbol; no alias guessing or Ensembl conversion",
        "source_url": URL,
        "release_url": "https://reactome.org/about/news",
        "download_documentation_url": "https://reactome.org/download-data",
        "license": "CC0-1.0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "license_evidence_url": "https://reactome.org/license",
        "attribution": "Reactome Pathway Database, release 98; human pathway gene sets",
        "modifications": "None; original official archive and GMT bytes retained",
        "archive_file": "ReactomePathways.gmt.zip",
        "archive_sha256": SHA256,
        "gmt_member": "ReactomePathways.gmt",
        "gmt_sha256": hashlib.sha256(gmt).hexdigest(),
        "pathway_count": len(rows),
        "member_symbol_count": len({gene for row in rows for gene in row[2:]}),
        "scope_note": "Human pathway IDs; source GMT can include pathogen gene symbols "
        "in infection pathways. "
        "Only exact symbols measured in the declared human study can enter the analysis background.",
    }
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "ReactomePathways.gmt.zip").write_bytes(payload)
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument(
        "--archive", type=Path, help="Verify and reuse an already downloaded official archive"
    )
    args = parser.parse_args()
    print(json.dumps(prepare(args.destination, args.archive), ensure_ascii=False, indent=2))
