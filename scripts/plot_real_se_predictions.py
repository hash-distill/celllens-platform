"""Project real ST-SE predictions using PCA fitted only on real source controls."""

import argparse
from pathlib import Path

import anndata as ad
import matplotlib
import numpy as np
import pandas as pd

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.scientific_analysis import _select_prediction_population

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "reports/metabolic-full-coverage-2026-10-09"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measured-perturbation", help="Completed se-measured-{gene} experiment to project")
    args = parser.parse_args()
    perturbation = args.measured_perturbation or "AAMP"
    prefix = f"real-se-{perturbation.lower()}" if args.measured_perturbation else "real-se-signed"
    if (
        args.measured_perturbation
        and not (PROOF / f"se-measured-{perturbation.lower()}/manifest.json").is_file()
    ):
        raise ValueError("Complete the four-background measured diagnostic before plotting")
    plt.rcParams.update(
        {"font.sans-serif": ["Microsoft YaHei", "DejaVu Sans"], "axes.unicode_minus": False, "font.size": 11}
    )
    inputs = {}
    for context in ("K562", "RPE1", "Jurkat", "HepG2"):
        slug = context.lower()
        control_path = PROOF / f"se-controls/{slug}.h5ad"
        prediction_path = (
            PROOF / f"se-measured-{perturbation.lower()}/{slug}/native/predicted.h5ad"
            if args.measured_perturbation
            else PROOF / f"se-native-signed-{slug}/predicted.h5ad"
        )
        control = ad.read_h5ad(control_path)
        predicted, _ = _select_prediction_population(ad.read_h5ad(prediction_path), "gene", perturbation)
        inputs[context] = {
            "control": np.asarray(control.obsm["X_state"][:, :2048]),
            "predicted": np.asarray(predicted.obsm["X_state"][:, :2048]),
            "control_sha256": file_sha256(control_path),
            "prediction_sha256": file_sha256(prediction_path),
        }
    reference = np.concatenate([item["control"] for item in inputs.values()]).astype(np.float64)
    centre = reference.mean(axis=0)
    _, singular, directions = np.linalg.svd(reference - centre, full_matrices=False)
    basis = directions[:2].T
    ratio = singular[:2] ** 2 / np.sum(singular**2)
    coordinates = []
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    fig.suptitle(f"{perturbation} 扰动：四背景 ST-SE 真实预测", fontsize=18, fontweight="bold")
    for (context, values), axis in zip(inputs.items(), axes.flat, strict=True):
        means = []
        for source, label, colour, marker in (
            ("control", "真实对照的官方 SE 嵌入", "#28768A", "o"),
            ("predicted", "ST-SE 预测扰动嵌入", "#C7744A", "^"),
        ):
            points = (values[source] - centre) @ basis
            means.append(points.mean(axis=0))
            axis.scatter(
                points[:, 0], points[:, 1], color=colour, marker=marker, s=26, alpha=0.65, label=label
            )
            coordinates.extend(
                {
                    "cell_line": context,
                    "source": source,
                    "cell": i,
                    "pc1": float(point[0]),
                    "pc2": float(point[1]),
                }
                for i, point in enumerate(points)
            )
        axis.annotate(
            "", xy=means[1], xytext=means[0], arrowprops={"arrowstyle": "->", "color": "#303F48", "lw": 1.5}
        )
        axis.set_title(f"{context} · 对照 64 / 预测 64")
        axis.set_xlabel(f"SE PC1（{ratio[0]:.1%} 对照方差）")
        axis.set_ylabel(f"SE PC2（{ratio[1]:.1%} 对照方差）")
        axis.grid(alpha=0.16)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0, 0].legend(fontsize=9, frameon=False, loc="best")
    fig.supxlabel(
        "共享 PCA 仅拟合 256 个真实对照；各面板视窗不同。箭头连接群体中心，不表示单细胞配对。", fontsize=10
    )
    fig.savefig(PROOF / f"{prefix}-predictions.png", dpi=180, facecolor="white")
    fig.savefig(PROOF / f"{prefix}-predictions.svg", facecolor="white")
    plt.close(fig)
    pd.DataFrame(coordinates).to_csv(PROOF / f"{prefix}-projection-coordinates.csv", index=False)
    np.savez_compressed(
        PROOF / f"{prefix}-projection-transform.npz", centre=centre, basis=basis, variance_ratio=ratio
    )
    atomic_write_json(
        PROOF / f"{prefix}-projection-manifest.json",
        {
            "method": "PCA fit on original official source control embeddings only",
            "perturbation": perturbation,
            "input_dimensions": 2048,
            "dataset_coordinates_excluded": 10,
            "reference_cells": 256,
            "predicted_cells": 256,
            "explained_variance_ratio": ratio.tolist(),
            "sources": {
                context: {key: value for key, value in inputs[context].items() if key.endswith("sha256")}
                for context in inputs
            },
            "coordinates_sha256": file_sha256(PROOF / f"{prefix}-projection-coordinates.csv"),
            "transform_sha256": file_sha256(PROOF / f"{prefix}-projection-transform.npz"),
            "no_random_or_synthetic_coordinates": True,
            "scope": "genuine ST-SE projection; not metabolic or experimental validation",
        },
    )
    print(PROOF / f"{prefix}-predictions.png")


if __name__ == "__main__":
    main()
