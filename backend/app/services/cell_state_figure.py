"""Publication-style rendering of the same prepared data consumed by the UI."""

from io import BytesIO
from textwrap import fill
from threading import Lock
from typing import Any

import numpy as np

from backend.app.services.cell_state import COLORS, LABELS

_RENDER_LOCK = Lock()


def render_cell_state(document: dict[str, Any], file_format: str) -> bytes:
    import matplotlib as mpl
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize
    from matplotlib.figure import Figure
    from matplotlib.ticker import MaxNLocator

    # Matplotlib's font/rc caches are shared across request threads.
    with (
        _RENDER_LOCK,
        mpl.rc_context(
            {
                "font.family": "sans-serif",
                "font.sans-serif": ["Arial", "DejaVu Sans"],
                "font.size": 10,
                "axes.labelsize": 10,
                "axes.titlesize": 11,
                "axes.linewidth": 0.7,
                "svg.fonttype": "none",
                "pdf.fonttype": 42,
                "figure.facecolor": "white",
                "savefig.facecolor": "white",
            }
        ),
    ):
        fig = Figure(figsize=(14, 8.6))
        grid = fig.add_gridspec(2, 6, left=0.07, right=0.92, bottom=0.14, top=0.86, hspace=0.62, wspace=1.0)
        overlay = fig.add_subplot(grid[0, :3])
        ecdf = fig.add_subplot(grid[0, 3:])
        sources = list(document["distributions"])
        per_source = [
            fig.add_subplot(grid[1, i * 6 // len(sources) : (i + 1) * 6 // len(sources)])
            for i in range(len(sources))
        ]
        points = document["points"]
        units = document["feature"]["units"]
        feature = document["feature"]["id"]
        low, high = document["color_range"]
        norm = Normalize(vmin=low if high > low else low - 0.5, vmax=high if high > low else low + 0.5)
        markers = {"control": "o", "predicted": "X", "observed": "^"}
        for ax in [overlay, ecdf, *per_source]:
            ax.spines[["top", "right"]].set_visible(False)
            ax.tick_params(direction="out", width=0.7, length=3)
            ax.xaxis.set_major_locator(MaxNLocator(5))
            ax.yaxis.set_major_locator(MaxNLocator(4))
        for ax in [overlay, *per_source]:
            ax.set_xlim(document["bounds"][0])
            ax.set_ylim(document["bounds"][1])
            ax.set_aspect("equal", adjustable="box")
            variance = document["explained_variance_ratio"]
            ax.set_xlabel(f"PC1 ({variance[0] * 100:.1f}% control variance)")
            ax.set_ylabel(f"PC2 ({variance[1] * 100:.1f}% control variance)")
        overlay.set_title("A   Global expression distribution", loc="left", fontweight="bold", pad=13)
        ecdf.set_title("C   Per-cell feature distribution", loc="left", fontweight="bold", pad=13)
        for index, (source, ax) in enumerate(zip(sources, per_source, strict=True)):
            source_points = [p for p in points if p["source"] == source]
            xy = np.array([[p["x"], p["y"]] for p in source_points])
            summary = document["distributions"][source]
            label = f"{LABELS[source]} (n={summary['n']})"
            overlay.scatter(
                xy[:, 0],
                xy[:, 1],
                s=12 if source == "control" else 24,
                color=COLORS[source],
                alpha=0.35 if source == "control" else 0.7,
                marker=markers[source],
                linewidths=0,
                label=label,
            )
            valid = [p for p in source_points if p["value"] is not None]
            missing = [p for p in source_points if p["value"] is None]
            if missing:
                ax.scatter([p["x"] for p in missing], [p["y"] for p in missing], s=9, color="#c6c6c6")
            ax.scatter(
                [p["x"] for p in valid],
                [p["y"] for p in valid],
                c=[p["value"] for p in valid],
                s=14,
                cmap="cividis",
                norm=norm,
                alpha=0.85,
                linewidths=0,
            )
            ax.set_title(
                f"B{index + 1}   {LABELS[source]} / feature value", loc="left", fontweight="bold", pad=13
            )
            ax.text(
                0.98,
                0.98,
                f"n={summary['n']}; shown={summary['n_displayed']}",
                transform=ax.transAxes,
                ha="right",
                va="top",
                fontsize=8,
                color="#505050",
            )
            curve = np.asarray(summary["ecdf"])
            if len(curve):
                # Include the zero-probability left endpoint, preserving exact steps.
                margin = max((high - low) * 0.04, 0.01)
                x = np.r_[low - margin, curve[:, 0], high + margin]
                y = np.r_[0, curve[:, 1], 1]
                ecdf.step(
                    x,
                    y,
                    where="post",
                    color=COLORS[source],
                    linewidth=1.6,
                    linestyle={"control": "-", "predicted": "--", "observed": ":"}[source],
                    label=f"{LABELS[source]} (valid n={summary['n_valid']})",
                )
        overlay.legend(loc="upper left", bbox_to_anchor=(0, 1.04), frameon=False, fontsize=8, ncol=1)
        ecdf.legend(loc="lower right", frameon=False, fontsize=8)
        ecdf.set_xlabel(units)
        ecdf.set_ylabel("Fraction of cells at or below value")
        ecdf.set_ylim(-0.02, 1.04)
        ecdf.set_yticks([0, 0.25, 0.5, 0.75, 1])
        cax = fig.add_axes((0.944, 0.19, 0.013, 0.22))
        bar = fig.colorbar(ScalarMappable(norm=norm, cmap="cividis"), cax=cax)
        bar.set_label(units, fontsize=8)
        if high == low:
            bar.set_ticks([low])
            bar.set_label(f"{units} (constant)", fontsize=8)
        bar.ax.tick_params(labelsize=8)
        fig.text(
            0.07,
            0.966,
            f"{document['cell_line']} / {document['perturbation']} perturbation",
            fontsize=16,
            fontweight="bold",
            va="top",
        )
        fig.text(0.07, 0.928, fill(f"Feature: {feature}", 115), fontsize=10, va="top")
        provenance = document["provenance"]
        footer = (
            f"Control-reference PCA | {document['gene_count']} genes | centered log1p(CP10K), "
            "no gene-wise scaling | identical axes and feature color range\n"
            "ECDF uses all valid cells. Populations are unpaired; no significance claim. "
            "Expression space does not represent morphology or metabolic flux.\n"
            f"Run: {document['run_id']} | Source: {provenance['source_run_id']} | "
            f"Manifest SHA256: {provenance['manifest_sha256']}"
        )
        fig.text(0.07, 0.075, footer, fontsize=7.3, color="#4a4a4a", va="top", linespacing=1.7)
        buffer = BytesIO()
        fig.savefig(
            buffer,
            format=file_format,
            dpi=300,
            metadata={"Creator": "CellLens"} if file_format in {"svg", "pdf"} else None,
        )
        return buffer.getvalue()
