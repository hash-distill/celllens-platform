"""Frozen, local Reactome ORA of expression-change candidates.

This is exploratory gene-set enrichment, not a test of treatment effects.
The caller must supply ALL QC-detectable genes for the actual comparison,
not a display subset, selected DE genes, or a whole-genome default.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
from scipy.stats import hypergeom

DEFAULT_MANIFEST = Path(__file__).resolve().parents[3] / "data/registry/pathways/reactome_v98/manifest.json"
METHOD_VERSION = "reactome-ora-1.0"
TABLE_COLUMNS = [
    "pathway_id",
    "pathway_name",
    "direction",
    "background_size",
    "pathway_size",
    "candidate_size",
    "hit_count",
    "expected_hits",
    "fold_enrichment",
    "p_value",
    "fdr",
    "hit_genes",
    "background_members",
]
INTERPRETATION = (
    "表达变化候选的通路富集；FDR 是给定候选选集与实际可检测背景下的富集多重检验结果，"
    "不表示处理效应显著，也不证明因果机制或独立实验验证。5% 是探索选集配置，不是显著性阈值。"
)


class PathwayResourceError(ValueError):
    """Missing or modified frozen public knowledge resource."""


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _hash_json(value: Any) -> str:
    return _hash_bytes(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    )


def load_reactome_resource(manifest_path: Path | str | None = None) -> tuple[dict, list[dict]]:
    """Verify archive/GMT hashes on EVERY read; no mutable-resource cache."""
    path = Path(manifest_path) if manifest_path is not None else DEFAULT_MANIFEST
    try:
        manifest_bytes = path.read_bytes()
        manifest = json.loads(manifest_bytes)
        filename = manifest["archive_file"]
        if Path(filename).name != filename:
            raise ValueError("Archive must be a sibling file")
        archive = path.with_name(filename).read_bytes()
        if _hash_bytes(archive) != manifest["archive_sha256"]:
            raise ValueError("Archive SHA-256 mismatch")
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            gmt = zipped.read(manifest["gmt_member"])
        if _hash_bytes(gmt) != manifest["gmt_sha256"]:
            raise ValueError("GMT SHA-256 mismatch")
        if manifest["species"] != "Homo sapiens" or manifest["identifier_type"] != "gene_symbol":
            raise ValueError("Unsupported resource species or identifiers")
        pathways = []
        for line in gmt.decode("utf-8").splitlines():
            if not line.strip():
                continue
            name, identifier, *members = line.split("\t")
            if not identifier.startswith("R-HSA-") or not members or any(not member for member in members):
                raise ValueError("Invalid human pathway record")
            pathways.append({"pathway_id": identifier, "pathway_name": name, "members": sorted(set(members))})
        if len({item["pathway_id"] for item in pathways}) != len(pathways):
            raise ValueError("Duplicate pathway identifiers")
        if len(pathways) != manifest["pathway_count"]:
            raise ValueError("Pathway count mismatch")
        manifest["manifest_sha256"] = _hash_bytes(manifest_bytes)
        return manifest, sorted(pathways, key=lambda item: item["pathway_id"])
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        raise PathwayResourceError(f"Frozen Reactome resource rejected: {exc}") from exc


def benjamini_hochberg(p_values: Iterable[float]) -> list[float]:
    """BH across the entire supplied test family, retaining zeros and ties."""
    values = np.asarray(list(p_values), dtype=float)
    if not len(values):
        return []
    if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
        raise ValueError("p values must be finite probabilities")
    order = np.argsort(values, kind="stable")
    adjusted = values[order] * len(values) / np.arange(1, len(values) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1].clip(0, 1)
    result = np.empty(len(values))
    result[order] = adjusted
    return result.tolist()


def analyze_pathways(
    expression_table: pd.DataFrame,
    detectable_genes: Iterable[str],
    *,
    species: str = "Homo sapiens",
    manifest_path: Path | str | None = None,
    candidate_fraction: float = 0.05,
    min_pathway_size: int = 5,
    max_pathway_size: int = 500,
    low_coverage_threshold: float = 0.20,
) -> tuple[dict, pd.DataFrame]:
    """Return a JSON-safe frozen document and an ALL-tests export table.

    Index must contain exact gene symbols; columns control/observed/observed_delta
    are means and their difference on the same declared expression scale.
    Duplicate symbols and non-finite comparisons are excluded, never aggregated.
    U = QC-detectable intersect valid-comparable intersect exact Reactome symbols.
    Each direction selects at most floor(fraction * len(U)); deterministic ties
    use gene-symbol ascending order. Zero-effect genes never become candidates.
    Empty directions have no tests; BH includes all eligible pathways (zero hits
    included) across every nonempty direction. Low coverage is a warning, not an
    invented significance test. The complete gene lists permit audit/reanalysis.
    """
    if not 0 < candidate_fraction <= 1:
        raise ValueError("candidate_fraction must be in (0, 1]")
    if min_pathway_size < 1 or max_pathway_size < min_pathway_size:
        raise ValueError("Invalid pathway size interval")
    if not 0 <= low_coverage_threshold <= 1:
        raise ValueError("low_coverage_threshold must be in [0, 1]")
    missing = {"control", "observed", "observed_delta"} - set(expression_table.columns)
    if missing:
        raise ValueError(f"Missing expression columns: {sorted(missing)}")
    if detectable_genes is None:
        raise ValueError("Explicit actual QC-detectable genes are required")
    manifest, pathways = load_reactome_resource(manifest_path)
    detectable = {g for g in detectable_genes if isinstance(g, str) and g}
    valid_labels = [isinstance(g, str) and bool(g) for g in expression_table.index]
    frame = expression_table.loc[valid_labels, ["control", "observed", "observed_delta"]].copy()
    duplicates = sorted(set(frame.index[frame.index.duplicated(keep=False)]))
    frame = frame.loc[~frame.index.duplicated(keep=False)]
    for col in frame.columns:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    finite_mask = np.isfinite(frame.to_numpy(dtype=float)).all(axis=1)
    invalid_values = sorted(frame.index[~finite_mask])
    frame = frame.loc[finite_mask]
    consistent = np.isclose(
        frame["observed"] - frame["control"], frame["observed_delta"], rtol=1e-5, atol=1e-7
    )
    inconsistent = sorted(frame.index[~consistent])
    frame = frame.loc[consistent]
    comparable = set(frame.index)
    detected_comparable = comparable & detectable
    resource_genes = {gene for pathway in pathways for gene in pathway["members"]}
    universe = sorted(detected_comparable & resource_genes) if species == "Homo sapiens" else []
    universe_set = set(universe)
    n_background = len(universe)
    coverage_fraction = n_background / len(detected_comparable) if detected_comparable else None
    cap = math.floor(candidate_fraction * n_background)
    candidates: dict[str, list[str]] = {"up": [], "down": []}
    for direction, sign in (("up", 1), ("down", -1)):
        signed = [gene for gene in universe if sign * float(frame.at[gene, "observed_delta"]) > 0]
        candidates[direction] = sorted(
            signed, key=lambda g: (-sign * float(frame.at[g, "observed_delta"]), g)
        )[:cap]
    records = []
    eligible = []
    excluded = []
    for pathway in pathways:
        members = sorted(set(pathway["members"]) & universe_set)
        item = {
            "pathway_id": pathway["pathway_id"],
            "pathway_name": pathway["pathway_name"],
            "background_members": members,
            "pathway_size": len(members),
        }
        if min_pathway_size <= len(members) <= max_pathway_size:
            eligible.append(item)
        else:
            excluded.append(
                {
                    "pathway_id": pathway["pathway_id"],
                    "pathway_size": len(members),
                    "reason": "below_min_size" if len(members) < min_pathway_size else "above_max_size",
                }
            )
    for direction, selected in candidates.items():
        if not selected:
            continue
        selected_set = set(selected)
        for pathway in eligible:
            hits = sorted(selected_set & set(pathway["background_members"]))
            expected = len(selected) * pathway["pathway_size"] / n_background
            records.append(
                {
                    **pathway,
                    "direction": direction,
                    "background_size": n_background,
                    "candidate_size": len(selected),
                    "hit_count": len(hits),
                    "expected_hits": expected,
                    "fold_enrichment": len(hits) / expected,
                    "p_value": float(
                        hypergeom.sf(len(hits) - 1, n_background, pathway["pathway_size"], len(selected))
                    ),
                    "hit_genes": hits,
                }
            )
    for row, fdr in zip(records, benjamini_hochberg(row["p_value"] for row in records), strict=True):
        row["fdr"] = fdr
    warnings = []
    if coverage_fraction is not None and coverage_fraction < low_coverage_threshold:
        warnings.append("low_mapping_coverage")
    if duplicates:
        warnings.append("duplicate_symbols_excluded")
    if invalid_values or inconsistent:
        warnings.append("invalid_comparisons_excluded")
    status = "complete"
    if species != "Homo sapiens":
        status = "unsupported_species"
    elif not n_background:
        status = "no_mapped_background"
    elif not any(candidates.values()):
        status = "no_candidates"
    elif not eligible:
        status = "no_eligible_pathways"
    elif "low_mapping_coverage" in warnings:
        status = "low_coverage"
    comparisons = [
        {"gene": gene, **{col: float(frame.at[gene, col]) for col in frame.columns}} for gene in universe
    ]
    document = {
        "schema_version": 1,
        "method": "Reactome ORA",
        "method_version": METHOD_VERSION,
        "title": "表达变化候选的通路富集",
        "status": status,
        "warnings": warnings,
        "interpretation": INTERPRETATION,
        "species": species,
        "resource": manifest,
        "parameters": {
            "candidate_fraction": candidate_fraction,
            "candidate_rounding": "floor",
            "candidate_cap_per_direction": cap,
            "tie_breaker": "gene_symbol_ascending",
            "candidate_rule": "strict positive/negative observed_delta; never fill with other direction",
            "min_pathway_size": min_pathway_size,
            "max_pathway_size": max_pathway_size,
            "pathway_size_scope": "members intersect U",
            "test": "hypergeometric_right_tail",
            "multiple_testing": "Benjamini-Hochberg over all tested pathways in both nonempty directions",
            "low_coverage_threshold": low_coverage_threshold,
        },
        "coverage": {
            "input_row_count": len(expression_table),
            "qc_detectable_count": len(detectable),
            "valid_comparable_count": len(comparable),
            "detectable_comparable_count": len(detected_comparable),
            "mapped_background_count": n_background,
            "mapping_fraction": coverage_fraction,
            "eligible_pathway_count": len(eligible),
            "tested_count": len(records),
        },
        "background_genes": universe,
        "detectable_genes": sorted(detectable),
        "unmapped_genes": sorted(detected_comparable - resource_genes),
        "excluded_duplicate_symbols": duplicates,
        "excluded_nonfinite_symbols": invalid_values,
        "excluded_inconsistent_delta_symbols": inconsistent,
        "candidates": candidates,
        "comparisons": comparisons,
        "direction_status": {
            direction: "tested"
            if selected and eligible
            else "no_candidates"
            if not selected
            else "no_eligible_pathways"
            for direction, selected in candidates.items()
        },
        "eligible_pathways": eligible,
        "excluded_pathways": excluded,
        "results": records,
        "hashes": {
            "background_sha256": _hash_json(universe),
            "candidates_sha256": _hash_json(candidates),
            "comparisons_sha256": _hash_json(comparisons),
            "detectable_sha256": _hash_json(sorted(detectable)),
        },
    }
    document["hashes"]["analysis_sha256"] = _hash_json(document)
    table = pd.DataFrame(records, columns=cast(Any, TABLE_COLUMNS))
    # CSV member fields are literal symbols, not Python-list representations.
    for column in ("hit_genes", "background_members"):
        table[column] = table[column].map(lambda genes: ";".join(genes))
    return document, table


def measured_pathway_species(request: dict, inputs: dict) -> tuple[str, str]:
    """Resolve only frozen species metadata or the known fixed human source."""
    if request.get("dataset_id"):
        version_species = str(inputs.get("dataset_version", {}).get("species", "unknown")).strip()
        contrast_species = str(inputs.get("contrast", {}).get("species", "unknown")).strip()

        def normalize(value: str) -> str:
            return "Homo sapiens" if value.casefold() in {"human", "homo sapiens", "9606"} else value

        if normalize(version_species) != normalize(contrast_species):
            return "unknown", "conflicting_dataset_species"
        return normalize(version_species), "frozen_dataset_version_and_contrast"
    if request.get("import_id") or inputs.get("source", {}).get("kind") == "controlled_private_h5ad":
        value = str(inputs.get("input_contract", {}).get("species", "unknown")).strip()
        species = "Homo sapiens" if value.casefold() in {"human", "homo sapiens", "9606"} else value
        return species, "frozen_private_import_contract"
    from backend.app.services.perturbation_catalog import CONTEXTS, SOURCE

    source = inputs.get("source", {})
    if all(source.get(key) == SOURCE[key] for key in ("repo", "revision", "file")) and str(
        request.get("cell_line", "")
    ).casefold() in {cell.casefold() for cell in CONTEXTS}:
        return "Homo sapiens", "fixed_human_source_revision"
    return "unknown", "no_verified_species_metadata"


def analyse_measured_pathways(
    root: Path,
    request: dict,
    inputs: dict,
    matrices: dict,
    genes: list[str],
    expression_table: pd.DataFrame,
    output: Path,
) -> tuple[dict, dict[str, str]]:
    """Write new measured-run artifacts; no recomputation in read/download paths."""
    from backend.app.core.run_manifest import atomic_write_json, file_sha256

    species, species_basis = measured_pathway_species(request, inputs)
    # Detection is computed AFTER alignment/batch selection from all actual cells
    # in the comparison. No display/DE/prediction panel or genome default is used.
    detectable_mask = np.zeros(len(genes), dtype=bool)
    for group in ("control", "observed"):
        matrix = matrices[group]
        if matrix.shape[1] != len(genes):
            raise ValueError("Pathway matrix and aligned genes differ")
        detectable_mask |= np.asarray((matrix != 0).sum(axis=0)).reshape(-1) > 0
    detectable = [gene for gene, detected in zip(genes, detectable_mask, strict=True) if detected]
    manifest_path = root / "data/registry/pathways/reactome_v98/manifest.json"
    assets: dict[str, str] = {}
    reason = None
    if species != "Homo sapiens":
        status = "species_unknown" if species.casefold() in {"", "unknown", "none"} else "unsupported_species"
        reason = "缺少可核验的人类物种契约" if status == "species_unknown" else "冻结资源仅支持人类物种"
    elif not manifest_path.is_file():
        status, reason = "resource_unavailable", "本地未安装冻结 Reactome v98 资源"
    else:
        try:
            document, table = analyze_pathways(
                expression_table, detectable, species=species, manifest_path=manifest_path
            )
        except PathwayResourceError as exc:
            if isinstance(exc.__cause__, FileNotFoundError):
                status, reason = "resource_unavailable", "本地冻结 Reactome v98 资源文件缺失"
            else:
                raise  # A present but altered knowledge resource must never silently degrade.
        else:
            resource = document["resource"]
            for path, expected in (
                (manifest_path, resource["manifest_sha256"]),
                (manifest_path.with_name(resource["archive_file"]), resource["archive_sha256"]),
            ):
                if file_sha256(path) != expected:
                    raise PathwayResourceError("Reactome resource changed during analysis")
                assets[path.resolve().relative_to(root.resolve()).as_posix()] = expected
    if reason is not None:
        document = {
            "schema_version": 1,
            "method": "Reactome ORA",
            "method_version": METHOD_VERSION,
            "title": "表达变化候选的通路富集",
            "status": status,
            "reason": reason,
            "interpretation": INTERPRETATION,
            "species": species,
            "warnings": [],
            "coverage": {
                "input_row_count": len(expression_table),
                "qc_detectable_count": len(detectable),
                "mapped_background_count": None,
                "mapping_fraction": None,
                "tested_count": 0,
            },
            "parameters": {},
            "resource": {},
            "hashes": {},
            "background_genes": [],
            "detectable_genes": detectable,
            "candidates": {"up": [], "down": []},
            "results": [],
        }
        table = pd.DataFrame(columns=cast(Any, TABLE_COLUMNS))
    document["species_basis"] = species_basis
    document["detection_rule"] = (
        "nonzero in at least one actual aligned control or observed cell after batch selection"
    )
    document["input_units"] = "mean(log1p(CP10K)) difference, not log2FC"
    document["available"] = bool(document["results"])
    document["hashes"].pop("analysis_sha256", None)
    document["hashes"]["analysis_sha256"] = _hash_json(document)
    atomic_write_json(output / "pathways.json", document)
    table.to_csv(output / "pathways.csv", index=False)
    summary = {
        key: document[key]
        for key in (
            "title",
            "available",
            "status",
            "method",
            "method_version",
            "species",
            "species_basis",
            "interpretation",
            "coverage",
            "parameters",
            "resource",
            "hashes",
            "warnings",
            "detection_rule",
        )
    }
    if reason is not None:
        summary["reason"] = reason
    return summary, assets
