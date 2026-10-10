"""Verify scientific view preparation against four frozen real-result backgrounds."""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from backend.app.main import create_app
from backend.app.services.cell_state import cell_state_document
from backend.app.services.cell_state_figure import render_cell_state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--figures", action="store_true", help="Export gene and task examples in all three formats"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / "reports/scientific-cell-state-2026-10-09"
    output.mkdir(parents=True, exist_ok=True)
    container = create_app().state.container
    runs = {
        "K562": "run_2d7de9d129904b63",
        "RPE1": "run_2151b0c415484f8e",
        "Jurkat": "run_4a24afcd5b084acf",
        "HepG2": "run_0895eccf20f8405d",
        "HepG2-ACD": "run_c76a0442621c4e0d",
    }
    results = {}
    for name, run in runs.items():
        started = time.perf_counter()
        gene = cell_state_document(container, run, "gene", "ENO1" if name == "HepG2-ACD" else "")
        task = cell_state_document(container, run, "task", "")
        assert gene["method"] == "control-reference-pca"
        assert gene["bounds"] == task["bounds"]
        np.testing.assert_allclose(
            [[p["x"], p["y"]] for p in gene["points"]], [[p["x"], p["y"]] for p in task["points"]]
        )
        scores = pd.read_csv(container.settings.derived_root / run / "metabolic_task_scores.csv", index_col=0)
        means = scores.groupby("source")[task["feature"]["id"]].mean()
        for source, stats in task["distributions"].items():
            assert stats["n"] == sum(scores.source == source)
            assert np.isclose(stats["mean"], means[source])
        for kind, document in (("gene", gene), ("task", task)):
            (output / f"{name}-{kind}.json").write_text(
                json.dumps(document, allow_nan=False), encoding="utf-8"
            )
            if args.figures:
                for format in ("svg", "pdf", "png"):
                    (output / f"{name}-{kind}.{format}").write_bytes(render_cell_state(document, format))
        results[name] = {
            "counts": {s: v["n"] for s, v in gene["distributions"].items()},
            "gene": gene["feature"]["id"],
            "task": task["feature"]["id"],
            "variance": gene["explained_variance_ratio"],
            "seconds": time.perf_counter() - started,
            "means_and_cell_ids_verified": True,
        }
        print(name, results[name], flush=True)
    (output / "live-data-check.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
