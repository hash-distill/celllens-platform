"""Generate a frozen, self-consistent precomputed demo bundle for the no-GPU path.

WHAT THIS IS
------------
A *synthetic* demonstration bundle. Expression effects are produced by a fixed-seed
model over a curated human gene panel, and metabolic task deltas are computed from
those same gene effects through explicit pathway membership, so every number in the
bundle is internally consistent and reproducible.

WHAT THIS IS NOT
----------------
It is **not** STATE model inference and **not** real scCellFie output. It exists so the
`precomputed` run mode, the frontend, and the no-GPU demo path can be developed and
demonstrated before real assets are registered. `provenance.json` and the summary
warnings state this explicitly, and the bundle must be replaced by a real frozen run
before any scientific claim is made.

Usage:
    uv run python scripts/build_demo_bundle.py
    uv run python scripts/build_demo_bundle.py --perturbation MYC --cell-line K562
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from datetime import UTC, datetime
from pathlib import Path

from backend.app.services.demo_projection import write_demo_projection

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SEED = 20260920

# Curated, real human gene panel. Housekeeping genes carry ~no effect; signalling /
# cell-cycle / metabolic genes carry graded effects driven by the perturbation.
HOUSEKEEPING = [
    "ACTB", "GAPDH", "TUBB", "PPIA", "RPL13A", "RPLP0", "B2M", "TBP", "SDHA",
    "UBC", "YWHAZ", "HPRT1", "TFRC", "EEF1A1", "PSMB4", "RPS18", "RPL32", "PGK1",
    "LDHA", "ENO1", "TPI1", "ALDOA", "PKM", "VIM", "ACTG1", "MYH9", "FLNA",
    "TLN1", "CLTC", "HSP90AB1", "HSPA8", "CCT5", "PSMD2", "UBB", "RAN", "NPM1",
]

# Perturbation -> genes whose expression the perturbation directly drives, with effect size.
PERTURBATION_TARGETS: dict[str, dict[str, float]] = {
    "MYC": {
        # MYC drives proliferation and anabolic metabolism; it represses OXPHOS.
        "CDK4": 0.95, "CCND2": 0.88, "NCL": 0.82, "ODC1": 0.79, "LDHA": 0.71,
        "CAD": 0.68, "RRM2": 0.66, "TYMS": 0.63, "GOT1": 0.55, "SHMT2": 0.58,
        "GLS": 0.52, "MTHFD2": 0.49, "PRPS2": 0.47, "IMPDH2": 0.45, "NME1": 0.43,
        "EIF4E": 0.41, "CDK6": 0.38, "MCM2": 0.36, "PCNA": 0.34, "TXN": 0.31,
        # repressed arm
        "SDHB": -0.61, "SDHC": -0.58, "SDHD": -0.55, "COX5A": -0.52, "COX6B1": -0.49,
        "ATP5F1A": -0.47, "ATP5F1B": -0.44, "NDUFA9": -0.41, "UQCRC1": -0.38,
        "CYC1": -0.35, "FH": -0.33, "MDH2": -0.30, "OGDH": -0.28, "IDH3A": -0.26,
    },
    "PCNA": {"PCNA": 0.9, "MCM2": 0.8, "RRM2": 0.7, "TYMS": 0.6, "CDK4": 0.5, "RAD51": 0.4},
    "TP53": {"CDKN1A": 1.1, "MDM2": 0.8, "BAX": 0.7, "GADD45A": 0.6, "BBC3": 0.5, "PCNA": -0.5},
}

# Real KEGG-style metabolic tasks with real gene membership. Task delta is computed from
# the gene effects above, so task scores are derived rather than invented.
METABOLIC_TASKS: dict[str, dict[str, list[str]]] = {
    "Oxidative phosphorylation": {
        "genes": ["SDHB", "SDHC", "SDHD", "COX5A", "COX6B1", "ATP5F1A", "ATP5F1B",
                  "NDUFA9", "UQCRC1", "CYC1", "FH", "MDH2", "OGDH", "IDH3A"],
    },
    "TCA cycle": {
        "genes": ["FH", "MDH2", "OGDH", "IDH3A", "SDHB", "SDHC", "SDHD", "CS", "ACO2"],
    },
    "De novo pyrimidine biosynthesis": {
        "genes": ["CAD", "RRM2", "TYMS", "NME1", "UMPS", "DHODH", "CTPS1"],
    },
    "De novo purine biosynthesis": {
        "genes": ["PRPS2", "IMPDH2", "GART", "ATIC", "PAICS", "ADSL"],
    },
    "Glutamine metabolism": {
        "genes": ["GLS", "GOT1", "GLUD1", "GOT2", "ASNS"],
    },
    "One-carbon / folate metabolism": {
        "genes": ["SHMT2", "MTHFD2", "MTHFR", "TYMS", "DHFR"],
    },
    "Glycolysis": {
        "genes": ["LDHA", "PKM", "ENO1", "TPI1", "ALDOA", "PGK1", "GAPDH", "HK2", "PFKL"],
    },
    "Pentose phosphate pathway": {
        "genes": ["G6PD", "PGD", "TKT", "RPIA", "RPE"],
    },
}


def canonical_gene_panel() -> list[str]:
    """MVL-style metabolism panel plus housekeeping genes: a realistic HVG-sized set."""
    genes: set[str] = set(HOUSEKEEPING)
    for task in METABOLIC_TASKS.values():
        genes.update(task["genes"])
    for targets in PERTURBATION_TARGETS.values():
        genes.update(targets)
    # Deterministic filler to reach a realistic HVG panel size.
    for index in range(1600):
        genes.add(f"GENE{index + 1:04d}")
    return sorted(genes)


def compute_gene_effects(genes: list[str], perturbation: str, rng: random.Random) -> dict[str, float]:
    """Fixed-seed effect model: graded direct targets + small stochastic background."""
    direct = PERTURBATION_TARGETS.get(perturbation, PERTURBATION_TARGETS["MYC"])
    effects: dict[str, float] = {}
    for gene in genes:
        if gene in HOUSEKEEPING:
            value = rng.gauss(0.0, 0.015)
        elif gene in direct:
            value = direct[gene] + rng.gauss(0.0, 0.04)
        else:
            # Weak, homeostatic decay away from the perturbation's own module.
            value = rng.gauss(0.0, 0.06) * math.exp(-len(gene) / 40.0)
        effects[gene] = round(value, 6)
    if perturbation in effects:
        effects[perturbation] = round(direct.get(perturbation, 1.0), 6)
    return effects


def compute_task_scores(
    tasks: dict[str, dict[str, list[str]]], effects: dict[str, float], genes: list[str]
) -> tuple[list[dict], list[dict]]:
    """Derive task deltas and coverage from gene effects and real pathway membership."""
    present = set(genes)
    task_rows: list[dict] = []
    coverage_rows: list[dict] = []
    for task, spec in tasks.items():
        required = spec["genes"]
        observed = [gene for gene in required if gene in effects]
        fraction = len(observed) / len(required) if required else 0.0
        if fraction >= 0.8:
            level = "supported"
        elif fraction >= 0.6:
            level = "exploratory"
        else:
            level = "insufficient"
        delta = sum(effects[gene] for gene in observed) / len(observed) if observed else 0.0
        task_rows.append(
            {
                "id": task.replace(" ", "_"),
                "label": task,
                "predicted_delta": round(delta, 6),
                "observed_delta": round(delta * 0.82 + 0.01, 6),
                "coverage": round(fraction, 6),
                "evidence_level": level,
                "determinant_genes": [gene for gene in observed if abs(effects[gene]) > 0.3][:6],
            }
        )
        coverage_rows.append(
            {
                "task": task,
                "gene_fraction": round(fraction, 6),
                "evidence_level": level,
                "missing_genes": ";".join(gene for gene in required if gene not in present),
            }
        )
    task_rows.sort(key=lambda row: abs(row["predicted_delta"]), reverse=True)
    return task_rows, coverage_rows


def build(cell_line: str, perturbation: str, top_k: int) -> Path:
    rng = random.Random(SEED)
    genes = canonical_gene_panel()
    effects = compute_gene_effects(genes, perturbation, rng)

    ranked = sorted(effects.items(), key=lambda item: abs(item[1]), reverse=True)[:top_k]
    top_genes = [
        {
            "id": gene,
            "label": gene,
            "predicted_delta": value,
            "observed_delta": round(value * 0.86 + rng.gauss(0.0, 0.02), 6),
            "coverage": 1.0,
            "evidence_level": "supported",
            "determinant_genes": [gene],
        }
        for gene, value in ranked
    ]

    tasks, coverage_rows = compute_task_scores(METABOLIC_TASKS, effects, genes)
    metabolic_tasks = [row for row in tasks if row["evidence_level"] != "insufficient"][:20]

    covered = sum(1 for row in coverage_rows if row["evidence_level"] != "insufficient")
    coverage = {
        "state_gene_fraction": 1.0,
        "metabolic_gene_fraction": round(len(set(genes)) / max(len(set(genes)), 1), 6),
        "reaction_fraction": round(covered / len(coverage_rows), 6),
        "supported_tasks": sum(1 for row in coverage_rows if row["evidence_level"] == "supported"),
        "exploratory_tasks": sum(1 for row in coverage_rows if row["evidence_level"] == "exploratory"),
        "insufficient_tasks": sum(1 for row in coverage_rows if row["evidence_level"] == "insufficient"),
    }

    run_id = f"demo_{cell_line.lower()}_{perturbation.lower()}"
    summary = {
        "run_id": run_id,
        "status": "completed",
        "stage_progress": 100,
        "cell_line": cell_line,
        "perturbation": perturbation,
        "coverage": coverage,
        "top_genes": top_genes,
        "metabolic_tasks": metabolic_tasks,
        "warnings": [
            "SYNTHETIC DEMO BUNDLE: not STATE model inference and not real scCellFie output.",
            "Generated by scripts/build_demo_bundle.py with a fixed seed for the no-GPU demo path.",
            "Replace with a real frozen run before any scientific claim.",
        ],
        "error_code": None,
    }

    target = PROJECT_ROOT / "data" / "demo" / cell_line / perturbation
    target.mkdir(parents=True, exist_ok=True)

    gene_csv = target / "gene_deltas.csv"
    with gene_csv.open("w", encoding="utf-8", newline="") as handle:
        handle.write("gene,control,predicted,predicted_delta,observed,observed_delta\n")
        for gene in genes:
            value = effects[gene]
            # control/predicted expressed on a log1p CPM-like scale for realism.
            # Use a stable digest, not hash(): PYTHONHASHSEED randomises str hashing.
            control = round(6.0 + (int(hashlib.md5(gene.encode()).hexdigest()[:8], 16) % 500) / 100.0, 6)
            handle.write(f"{gene},{control},{round(control + value, 6)},{value},,{round(value * 0.86, 6)}\n")

    coverage_csv = target / "metabolic_coverage.csv"
    with coverage_csv.open("w", encoding="utf-8", newline="") as handle:
        handle.write("task,gene_fraction,evidence_level,missing_genes\n")
        for row in coverage_rows:
            handle.write(
                f"{row['task']},{row['gene_fraction']},{row['evidence_level']},{row['missing_genes']}\n"
            )

    task_csv = target / "metabolic_task_scores.csv"
    with task_csv.open("w", encoding="utf-8", newline="") as handle:
        handle.write("task,source,score\n")
        for row in tasks:
            for source, scale in (("control", 0.0), ("predicted", 1.0), ("observed", 0.86)):
                handle.write(f"{row['id']},{source},{round(row['predicted_delta'] * scale, 6)}\n")

    (target / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    provenance = {
        "kind": "synthetic_demo_bundle",
        "generator": "scripts/build_demo_bundle.py",
        "seed": SEED,
        "generated_at": datetime.now(UTC).isoformat(),
        "cell_line": cell_line,
        "perturbation": perturbation,
        "gene_count": len(genes),
        "task_count": len(tasks),
        "disclaimer": (
            "Synthetic demonstration data. Not STATE inference, not scCellFie output. "
            "For UI development and the no-GPU demo path only."
        ),
    }
    provenance_path = target / "provenance.json"
    provenance_path.write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    write_demo_projection(target, seed=SEED)
    files = {}
    for item in sorted(target.iterdir()):
        if item.is_file() and item.name != "manifest.json":
            digest = hashlib.sha256(item.read_bytes()).hexdigest()
            files[item.name] = digest
    (target / "manifest.json").write_text(
        json.dumps(
            {
                "bundle": f"{cell_line}/{perturbation}",
                "files": files,
                "provenance": provenance,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cell-line", default="K562")
    parser.add_argument("--perturbation", default="MYC")
    parser.add_argument("--top-k", type=int, default=20)
    args = parser.parse_args()
    target = build(args.cell_line, args.perturbation, args.top_k)
    print(f"Wrote demo bundle: {target.relative_to(PROJECT_ROOT)}")
    for item in sorted(target.iterdir()):
        print(f"  {item.name:<28} {item.stat().st_size:>9,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
