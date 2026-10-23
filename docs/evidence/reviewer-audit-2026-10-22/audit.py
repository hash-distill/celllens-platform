import csv
import hashlib
import json
import math
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[3]
DESTINATION = Path(__file__).with_name("audit.json")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def table(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def check_outputs(directory, manifest_key):
    manifest = read_json(directory / "manifest.json")
    checked = []
    for name, declared in manifest[manifest_key].items():
        expected = declared["sha256"] if isinstance(declared, dict) else declared
        path = directory / name
        checked.append({"file": name, "matches": path.is_file() and digest(path) == expected})
    return checked


def correlation(first, second):
    first_mean = sum(first) / len(first)
    second_mean = sum(second) / len(second)
    first_centered = [value - first_mean for value in first]
    second_centered = [value - second_mean for value in second]
    denominator = math.sqrt(sum(value**2 for value in first_centered) * sum(value**2 for value in second_centered))
    return sum(left * right for left, right in zip(first_centered, second_centered, strict=True)) / denominator


models = read_json(ROOT / "data/registry/models.json")["models"]
catalog = read_json(ROOT / "data/registry/perturbation_catalog.json")
result = {
    "audit_time": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
    "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "scope": "Read-only registry and saved-output audit; no new inference, no H5AD metric recomputation, no new biological validation, no database inventory.",
    "models": [],
    "comparisons": [],
    "measured_analyses": [],
}
for model in models:
    genes = set((ROOT / model["gene_list_path"]).read_text(encoding="utf-8").splitlines())
    targets = {value.upper() for value in model["supported_perturbations"] if value.lower() != "non-targeting"}
    measured_targets = {row["perturbation"].upper() for row in catalog["counts"] if row["cell_line"] == model["cell_line"] and row["cell_count"] > 0 and row["perturbation"].lower() != "non-targeting"}
    result["models"].append({
        "id": model["id"], "cell_line": model["cell_line"], "enabled": model.get("enabled"),
        "expression_slot": model.get("expression_key", model.get("embed_key")),
        "panel_size": len(genes), "target_count_without_control": len(targets),
        "source_measured_combinations": len(measured_targets),
        "supported_without_source": len(targets - measured_targets),
        "selected_targets_in_prediction_panel": {name: name in genes for name in ("ALDOA", "AAAS", "AHCY", "GAPDH", "TPI1")},
    })
result["catalog_context_totals"] = catalog["context_totals"]

run_ids = ["run_47d09620968f48cf", "run_aef55809479e4c21", "run_34737097754841fd", "run_41504106326f404d", "run_ed570bb58ec74739", "run_469edf3453324f66"]
for run_id in run_ids:
    directory = ROOT / "data/derived/comparisons" / run_id
    if not directory.is_dir():
        result["comparisons"].append({"run_id": run_id, "available": False})
        continue
    document = read_json(directory / "comparison.json")
    run_manifest = read_json(ROOT / "data/derived/runs" / run_id / "manifest.json")
    comparison_manifest = read_json(directory / "manifest.json")
    rows = table(directory / "gene_deltas.csv")
    predicted = [float(row["predicted_delta"]) for row in rows]
    observed = [float(row["observed_delta"]) for row in rows]
    mse = sum((left - right) ** 2 for left, right in zip(predicted, observed, strict=True)) / len(rows)
    baseline = sum(value**2 for value in observed) / len(rows)
    recalculated = {"signed_delta_pearson": correlation(predicted, observed), "mse_relative_to_no_change": mse / baseline}
    completeness = read_json(directory / "official_completeness.json")
    gene_set = {row["gene"].upper() for row in rows}
    with (ROOT / "data/registry/sccellfie/human/Rxn_by_Gene.csv").open(encoding="utf-8-sig", newline="") as stream:
        database_genes = set(next(csv.reader(stream))[1:])
    result["comparisons"].append({
        "run_id": run_id, "request": run_manifest["request"],
        "held_out_validation": document["held_out_validation"],
        "training_exclusion_verified": document["training_exclusion_verified"],
        "recalculated_from_saved_csv": recalculated,
        "matches_saved_metrics": all(math.isclose(value, document["expression"][key], abs_tol=1e-10) for key, value in recalculated.items()),
        "output_hash_checks": check_outputs(directory, "outputs"),
        "source_manifest_matches": digest(ROOT / "data/derived/runs" / run_id / "manifest.json") == comparison_manifest["source_manifest_sha256"],
        "completeness": completeness["overall_summary"],
        "independent_panel_database_intersection": len(gene_set & database_genes),
        "empty_essential_task_sets": sum(row["n_genes_essential"] == 0 for row in completeness["tasks"]),
    })

for summary_path in sorted((ROOT / "data/derived/measured").glob("*/summary.json")):
    document = read_json(summary_path)
    completeness_path = summary_path.with_name("official_completeness.json")
    result["measured_analyses"].append({
        "analysis_id": document["analysis_id"], "cell_line": document["cell_line"],
        "perturbation": document["perturbation"], "counts": document["counts"],
        "gene_count": document["gene_count"], "metabolic_coverage": document["metabolism"].get("coverage"),
        "completeness": read_json(completeness_path)["overall_summary"] if completeness_path.is_file() else None,
        "output_hash_checks": check_outputs(summary_path.parent, "files"),
    })

source_files = [
    "backend/app/engines/state_engine.py", "backend/app/services/scientific_analysis.py",
    "backend/app/services/measured_analysis.py", "backend/app/services/completeness.py",
    "backend/app/assistant.py", "backend/app/api/runs.py", "frontend/src/components/AppHeader.vue",
    "frontend/src/utils/predictionEvidence.ts", "frontend/src/router/index.ts",
    "docs/ARCHITECTURE.md", "docs/OPERATIONS.md", "docs/GENERALIZATION.md",
    "docs/MEASURED_ANALYSIS.md", "data/registry/models.json", "data/registry/perturbation_catalog.json",
]
result["source_sha256"] = {name: digest(ROOT / name) for name in source_files}
checks = [check for record in result["comparisons"] + result["measured_analyses"] for check in record.get("output_hash_checks", [])]
result["verification_summary"] = {
    "saved_output_files_checked": len(checks),
    "saved_output_hash_mismatches": sum(not check["matches"] for check in checks),
    "comparison_metric_matches": sum(record.get("matches_saved_metrics", False) for record in result["comparisons"]),
    "comparison_source_manifest_matches": sum(record.get("source_manifest_matches", False) for record in result["comparisons"]),
}
DESTINATION.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result["verification_summary"], ensure_ascii=False))
print(DESTINATION)
