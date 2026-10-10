"""Add official completeness sidecars to real runs without changing existing results."""

import argparse
import copy
import json
from pathlib import Path

import pandas as pd

from backend.app.config import get_settings
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.core.storage import RunStore
from backend.app.schemas import CompletenessResponse
from backend.app.services.completeness import compute_official_completeness
from backend.app.services.scientific_analysis import _load_frozen_database


def supplement(root: Path, run_id: str, store: RunStore, database, database_version, cache) -> dict:
    source = root / "gene_deltas.csv"
    trace = root / "task_trace.json"
    if not source.is_file() or not trace.is_file():
        return {
            "run_id": run_id,
            "action": "skipped",
            "reason": "No frozen real gene panel and database trace",
        }
    registered = {item.kind: item for item in store.artifacts(run_id)}
    for kind, path in [("gene_deltas", source), ("task_trace", trace)]:
        if kind not in registered or registered[kind].sha256 != file_sha256(path):
            raise ValueError(f"Unregistered or changed source artifact: {run_id}/{path.name}")
    trace_document = json.loads(trace.read_text(encoding="utf-8"))
    if (
        trace_document["run_id"] != run_id
        or trace_document["database_provenance"]["manifest_sha256"]
        != database["_celllens_provenance"]["manifest_sha256"]
    ):
        raise ValueError(f"Run database differs from the frozen database: {run_id}")
    destination = root / "official_completeness.json"
    if destination.exists():
        doc = CompletenessResponse.model_validate_json(destination.read_bytes())
        if (
            "official_completeness" not in registered
            or registered["official_completeness"].sha256 != file_sha256(destination)
            or doc.source_gene_sha256 != file_sha256(source)
            or doc.run_id != run_id
        ):
            raise ValueError(f"Existing completeness sidecar differs or is unregistered: {run_id}")
        return {"run_id": run_id, "action": "already_present"}
    original = {path.name: file_sha256(path) for path in root.iterdir() if path.is_file()}
    genes = pd.read_csv(source, index_col=0).index.astype(str).tolist()
    key = tuple(sorted(g.upper() for g in genes))
    if key not in cache:
        cache[key] = compute_official_completeness(genes, database, database_version)
    document = copy.deepcopy(cache[key])
    document.update(run_id=run_id, source_gene_sha256=file_sha256(source))
    validated = CompletenessResponse.model_validate(document)
    atomic_write_json(destination, validated.model_dump(mode="json"))
    if any(file_sha256(root / name) != digest for name, digest in original.items()):
        raise ValueError(f"Original run artifacts changed during supplementation: {run_id}")
    store.register_artifact(
        run_id,
        "official_completeness",
        f"{run_id}/official_completeness.json",
        file_sha256(destination),
        destination.stat().st_size,
        "application/json",
    )
    return {
        "run_id": run_id,
        "action": "added",
        "original_files": original,
        "official_summary": document["overall_summary"],
        "sidecar_sha256": file_sha256(destination),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-id", action="append", help="Specific real run; default: all completed real runs"
    )
    args = parser.parse_args()
    settings = get_settings()
    store = RunStore(settings.database_url)
    try:
        database, database_version = _load_frozen_database(settings.sccellfie_database_root)
        records = []
        offset = 0
        while True:
            batch, total = store.list_runs(limit=100, offset=offset, status="completed")
            records.extend(
                record
                for record in batch
                if record.request.mode != "precomputed" and (not args.run_id or record.run_id in args.run_id)
            )
            offset += 100
            if offset >= total:
                break
        if args.run_id and {r.run_id for r in records} != set(args.run_id):
            raise ValueError("Requested runs must exist and be completed real predictions")
        cache = {}
        results = []
        with store.named_lock("celllens:official-completeness", timeout_seconds=30):
            for record in records:
                result = supplement(
                    settings.derived_root / record.run_id,
                    record.run_id,
                    store,
                    database,
                    database_version,
                    cache,
                )
                results.append(result)
                print(f"{record.run_id}: {result['action']}", flush=True)
        output = settings.project_root / "reports/official-completeness"
        output.mkdir(parents=True, exist_ok=True)
        atomic_write_json(output / "backfill.json", {"items": results})
        if cache:
            print(json.dumps(next(iter(cache.values()))["overall_summary"], indent=2), flush=True)
    finally:
        store.engine.dispose()


if __name__ == "__main__":
    main()
