"""Read-only audit of live run coverage against the hash-pinned local database."""

import hashlib
import json
import re
import urllib.request
from pathlib import Path

import pandas as pd

from backend.app.config import Settings
from backend.app.core.run_manifest import file_sha256
from backend.app.services.completeness import compute_official_completeness
from backend.app.services.scientific_analysis import _load_frozen_database


def get(path):
    with urllib.request.urlopen("http://127.0.0.1:8000/api/v1" + path, timeout=30) as response:
        return json.load(response)


def main():
    settings = Settings()
    database, version = _load_frozen_database(settings.sccellfie_database_root)
    db_genes = set()
    for rule in database["rxn_info"]["GPR-symbol"]:
        db_genes.update(
            token for token in re.findall(r"[^\s()]+", str(rule).upper()) if token not in {"AND", "OR"}
        )
    reports, recomputed = [], {}
    for item in get("/experiments?source=online&status=completed")["items"]:
        run_id = item["id"]
        folder = settings.derived_root / run_id
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        for filename in ("gene_deltas.csv", "official_completeness.json"):
            assert file_sha256(folder / filename) == manifest["outputs"][filename]["sha256"]
        genes = pd.read_csv(folder / "gene_deltas.csv")
        names = genes.iloc[:, 0].astype(str).str.upper().tolist()
        panel_hash = hashlib.sha256("\n".join(names).encode()).hexdigest()
        if panel_hash not in recomputed:
            recomputed[panel_hash] = compute_official_completeness(names, database, version)[
                "overall_summary"
            ]
        saved = get(f"/runs/{run_id}/completeness")
        assert saved["overall_summary"] == recomputed[panel_hash]
        assert len(set(names) & db_genes) == saved["overall_summary"]["n_genes_in_db_present_in_adata"]
        assert len(db_genes) == saved["overall_summary"]["n_genes_in_db_total"]
        reports.append(
            {
                "run_id": run_id,
                "request": manifest["request"],
                "model_id": manifest["assets"]["model_id"],
                "model_gene_list_sha256": manifest["assets"]["gene_list_sha256"],
                "canonical_panel_sha256": panel_hash,
                "gene_output_sha256": file_sha256(folder / "gene_deltas.csv"),
                "panel_gene_count": len(names),
                "genes_present": len(set(names) & db_genes),
                "database_genes": len(db_genes),
                "fully_covered_tasks": saved["overall_summary"]["n_tasks_fully_covered_all"],
                "database_tasks": saved["overall_summary"]["n_tasks_total"],
                "matches_fresh_computation": True,
            }
        )
    output = Path("reports/providers-2026-10-11/coverage-audit.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"database_version": version, "runs": reports}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
