"""Freeze PANTHER protein classes using explicit HGNC IDs, never symbol heuristics."""

import argparse
import csv
import gzip
import hashlib
import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from backend.app.core.run_manifest import file_sha256
from backend.app.services.gene_education import CLASS_TEXT

SOURCES = {
    "panther-human.tsv": (
        "https://data.pantherdb.org/ftp/sequence_classifications/current_release/PANTHER_"
        "Sequence_Classification_files/PTHR19.0_human"
    ),
    "panther-classes.tsv": "https://data.pantherdb.org/PANTHER19.0/ontology/Protein_Class_19.0",
    "hgnc.tsv": "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt",
}


def build_snapshot(source: Path) -> dict:
    terms = {}
    for line in (source / "panther-classes.tsv").read_text().splitlines():
        row = line.split("\t")
        if len(row) >= 3 and row[0].startswith("PC"):
            terms[row[0]] = {"path": row[1], "name_en": row[2]}
    roots = {
        value["path"].split(".")[1]: key
        for key, value in terms.items()
        if value["path"].endswith(".00.00.00") and key in CLASS_TEXT
    }
    roots["17"] = "PC00009"  # DNA metabolism has no separate 1.17 root entry.
    enzymes = {
        value["path"].split(".")[2]: key
        for key, value in terms.items()
        if value["path"].startswith("1.19.")
        and value["path"].endswith(".00.00")
        and key in CLASS_TEXT
        and key != "PC00262"
    }
    genes = {}
    lookups = defaultdict(set)
    approved = {}
    with (source / "hgnc.tsv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if row["status"] != "Approved":
                continue
            identifier, symbol = row["hgnc_id"], row["symbol"].upper()
            genes[identifier] = {
                "symbol": symbol,
                "name_en": row["name"],
                "category_ids": [],
                "protein_classes": [],
                "uniprot_ids": [],
            }
            approved[symbol] = identifier
            for name in [symbol, *row["prev_symbol"].split("|"), *row["alias_symbol"].split("|")]:
                if name:
                    lookups[name.upper()].add(identifier)
    with (source / "panther-human.tsv").open(encoding="utf-8", newline="") as stream:
        for row in csv.reader(stream, delimiter="\t"):
            match = re.search(r"(?:\||^)HGNC=(\d+)(?:\||$)", row[0])
            identifier = "HGNC:" + match[1] if match else None
            if identifier not in genes:
                continue  # Unmapped sequences are not guessed from similar symbols.
            gene = genes[identifier]
            if row[1] not in gene["uniprot_ids"]:
                gene["uniprot_ids"].append(row[1])
            leaf_ids = re.findall(r"#(PC\d+)", row[9])
            categories = set()
            for key in leaf_ids:
                if key not in terms:
                    raise ValueError(f"Unknown protein class {key}")
                branch = terms[key]["path"].split(".")
                category = roots.get(branch[1])
                if branch[1] == "19" and branch[2] in enzymes:
                    category = enzymes[branch[2]]
                if category is None:
                    raise ValueError(f"Unmapped class hierarchy {key}")
                categories.add(category)
                if not any(item["id"] == key for item in gene["protein_classes"]):
                    gene["protein_classes"].append({"id": key, "name_en": terms[key]["name_en"]})
            if categories & set(enzymes.values()):
                categories.discard("PC00262")
            combined = set(gene["category_ids"]) | categories
            if combined & set(enzymes.values()):
                combined.discard("PC00262")
            gene["category_ids"] = sorted(combined)
    symbols = {name: next(iter(ids)) for name, ids in lookups.items() if len(ids) == 1}
    symbols.update(approved)  # Official approved names take precedence over aliases.
    return {
        "schema_version": 1,
        "classes": {key: terms[key] for key in CLASS_TEXT},
        "genes": genes,
        "symbol_lookup": symbols,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path("data/registry/gene_annotations"))
    args = parser.parse_args()
    if args.destination.exists():
        raise SystemExit("Snapshot already exists; choose a new destination instead of overwriting it")
    document = build_snapshot(args.source_dir)
    args.destination.mkdir(parents=True)
    path = args.destination / "human.json.gz"
    path.write_bytes(
        gzip.compress(
            json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0
        )
    )
    manifest = {
        "schema_version": 1,
        "annotation_version": "PANTHER 19.0 / Protein Class 17.0",
        "created_at": datetime.now(UTC).isoformat(),
        "source_url": SOURCES["panther-human.tsv"],
        "sources": [
            {"url": url, "sha256": file_sha256(args.source_dir / name)} for name, url in SOURCES.items()
        ],
        "files": {"human.json.gz": file_sha256(path)},
        "policy": (
            "Explicit HGNC ID; approved symbol before unique previous/alias; PANTHER "
            "hierarchy; enzyme subclasses; multi-label; no name-based functional inference"
        ),
    }
    (args.destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "genes_with_classes": sum(bool(gene["category_ids"]) for gene in document["genes"].values()),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
