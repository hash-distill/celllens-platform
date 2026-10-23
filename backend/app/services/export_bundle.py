"""Read-only scientific exchange packages from hash-bound, completed analyses."""

import hashlib
import io
import json
import re
import tempfile
import zipfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.app.core.run_manifest import file_sha256, manifest_hash
from backend.app.services.cell_state import SOURCES, CellStateUnavailable, frozen_inputs
from backend.app.services.measured_comparison import load_comparison


class ExportBundleUnavailable(ValueError):
    """A scientific package cannot be exported without verified frozen sources."""


SCIENTIFIC_FILES = (
    "gene_deltas.csv",
    "metabolic_task_scores.csv",
    "reaction_scores.csv",
    "metabolic_coverage.csv",
    "gene_identity.json",
    "expression_contract.json",
    "summary.json",
    "task_trace.json",
    "official_completeness.json",
    "validation_metrics.json",
    "differential_expression.csv",
    "projection.json",
)
COMPARISON_FILES = (*SCIENTIFIC_FILES, "comparison.json")
OBS_FIELDS = (
    "gene",
    "perturbation",
    "condition",
    "gem_group",
    "batch",
    "batch_id",
    "donor",
    "donor_id",
    "cell_type",
    "cell_line",
    "library",
    "sample_id",
)
FIGURE_NAME = re.compile(r"(?:expression|metabolic)_(?:pca|umap)\.(?:json|svg)")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")


def _csv(frame: pd.DataFrame, *, index: bool = True) -> bytes:
    return frame.to_csv(index=index).encode("utf-8-sig")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _verified(path: Path, expected: Any, snapshots: dict[Path, str]) -> bytes:
    if not expected or not path.is_file():
        raise ExportBundleUnavailable(f"Frozen file unavailable: {path.name}")
    content = path.read_bytes()
    if _digest(content) != str(expected).lower():
        raise ExportBundleUnavailable(f"Frozen file hash changed: {path.name}")
    snapshots[path] = str(expected).lower()
    return content


def _source_manifest(
    container: Any, run_id: str, snapshots: dict[Path, str]
) -> tuple[Path, dict[str, Any], str]:
    if not re.fullmatch(r"run_[A-Za-z0-9_]+", run_id):
        raise ExportBundleUnavailable("Invalid run identity")
    record = container.store.get(run_id)
    if record is None or str(record.status) != "completed":
        raise ExportBundleUnavailable("Only completed scientific analyses can be exported")
    root = container.settings.derived_root / run_id
    if not root.resolve().is_relative_to(container.settings.derived_root.resolve()):
        raise ExportBundleUnavailable("Frozen source directory is outside the analysis root")
    matches = [a for a in container.store.artifacts(run_id) if Path(a.relative_path).name == "manifest.json"]
    if len(matches) != 1:
        raise ExportBundleUnavailable("No uniquely registered frozen manifest")
    expected = matches[0].sha256
    manifest = json.loads(_verified(root / "manifest.json", expected, snapshots))
    if (
        manifest.get("request", {}).get("cell_line") != record.request.cell_line
        or manifest.get("request", {}).get("perturbation") != record.request.perturbation
    ):
        raise ExportBundleUnavailable("Frozen manifest request does not match the run")
    return root, manifest, expected


def _original_files(root: Path, manifest: dict[str, Any], snapshots: dict[Path, str]) -> dict[str, bytes]:
    files = {}
    for name in SCIENTIFIC_FILES:
        if name in manifest.get("outputs", {}):
            files[name] = _verified(root / name, manifest["outputs"][name].get("sha256"), snapshots)
    if not {"gene_deltas.csv", "expression_contract.json"} <= files.keys():
        raise ExportBundleUnavailable("Historical run lacks verified scientific exchange sources")
    return files


def _score_table(files: dict[str, bytes], name: str) -> pd.DataFrame | None:
    return pd.read_csv(io.BytesIO(files[name]), index_col=0) if name in files else None


def _population(inputs: dict[str, Any], files: dict[str, bytes]) -> dict[str, Any]:
    contract = inputs["contract"]
    scores = _score_table(files, "metabolic_task_scores.csv")
    counts = (
        {str(k): int(v) for k, v in scores["source"].value_counts().items()} if scores is not None else {}
    )
    selected = contract.get("validation_population")
    if not counts and selected and selected.get("selected_cells"):
        counts = selected["selected_cells"]
    if not counts:
        # This reads observation metadata only; it never computes a projection or expression.
        import anndata as ad

        for name, key in (("control", "control_path"), ("observed", "observed_path")):
            if key in inputs["files"]:
                source = ad.read_h5ad(inputs["files"][key], backed="r")
                try:
                    if name == "observed":
                        column = contract["population_selection"]["perturbation_column"]
                        if column not in source.obs:
                            raise ExportBundleUnavailable("Observed source lacks perturbation labels")
                        counts[name] = int(
                            (
                                source.obs[column].astype(str).str.strip().str.upper()
                                == inputs["perturbation"]
                            ).sum()
                        )
                    else:
                        counts[name] = int(source.n_obs)
                finally:
                    source.file.close()
        counts["predicted"] = contract["population_selection"]["selected_prediction_cells"]
    if any(name not in SOURCES for name in counts) or min(counts.values()) < 1:
        raise ExportBundleUnavailable("Invalid original source population counts")
    expected_predicted = (
        (selected or {})
        .get("selected_cells", {})
        .get("predicted", contract["population_selection"]["selected_prediction_cells"])
    )
    if counts.get("predicted") != expected_predicted:
        raise ExportBundleUnavailable("Frozen source population counts do not match the contract")
    selection = {"population_selection": contract["population_selection"], "validation_population": selected}
    return {
        "label": "原在线分析群体"
        if not contract["source_scales"].get("observed")
        else "原分析群体（含原运行实测）",
        "counts": counts,
        "selection": selection,
        "selection_id": manifest_hash({"run_id": inputs["run_id"], "population": "original", **selection}),
        "includes_measured_observations": bool(contract["source_scales"].get("observed")),
    }


def _comparison(
    container: Any, run_id: str, source_sha: str, payloads: dict[str, bytes], snapshots: dict[Path, str]
) -> dict[str, Any] | None:
    report = load_comparison(container.settings.project_root, run_id)
    if report is None:
        return None
    root = container.settings.project_root / "data/derived/comparisons" / run_id
    # load_comparison checks all input/output hashes and the original prediction binding.
    # Check the same manifest again and retain only the explicit scientific allowlist.
    manifest_path = root / "manifest.json"
    manifest = json.loads(_verified(manifest_path, file_sha256(manifest_path), snapshots))
    if manifest.get("source_manifest_sha256") != source_sha:
        raise ExportBundleUnavailable("Comparison is not bound to this original population")
    for path_name, digest in manifest["inputs"].items():
        path = (container.settings.project_root / path_name).resolve()
        if not path.is_relative_to(container.settings.project_root.resolve()):
            raise ExportBundleUnavailable("Comparison input path is outside the project")
        _verified(path, digest, snapshots)
    for name in COMPARISON_FILES:
        if name in manifest["outputs"]:
            payloads[f"comparison/{name}"] = _verified(root / name, manifest["outputs"][name], snapshots)
    payloads["comparison/source_manifest.json"] = _json_bytes(
        {
            "run_id": run_id,
            "source_manifest_sha256": source_sha,
            "outputs": {name: sha for name, sha in manifest["outputs"].items() if name in COMPARISON_FILES},
        }
    )
    for name in ("genes", "tasks"):
        payloads[f"comparison/{name}.csv"] = _csv(pd.DataFrame(report.get(name, [])), index=False)
    matching = report.get("population_matching")
    return {
        "label": "共同批次实测诊断群体",
        "counts": report.get("parameters", {}).get("population_counts", {}),
        "selection": matching,
        "selection_id": manifest_hash({"run_id": run_id, "population": "comparison", "matching": matching}),
        "held_out_validation": report.get("held_out_validation", False),
        "training_exclusion_verified": report.get("training_exclusion_verified", False),
        "protocol_status": report.get("protocol_status", "matched_observation_diagnostic"),
        "source_manifest_sha256": source_sha,
        "comparison_manifest_sha256": snapshots[manifest_path],
        "h5ad_included": False,
    }


def _prepared(
    container: Any, inputs: dict[str, Any], payloads: dict[str, bytes], snapshots: dict[Path, str]
) -> dict[str, Any] | None:
    from backend.app.services.cell_state_preparation import load_prepared_data, prepared_manifest

    bundle = prepared_manifest(container, inputs)
    if bundle is None:
        return None
    root, manifest = bundle
    for name, digest in manifest["outputs"].items():
        if name == "plot_data.npz" or FIGURE_NAME.fullmatch(name):
            content = _verified(root / name, digest, snapshots)
            if FIGURE_NAME.fullmatch(name):
                payloads[f"original/figures/{name}"] = content
    data = load_prepared_data(container, inputs)
    snapshots[root / "prepared.json"] = file_sha256(root / "prepared.json")
    return data


def _expression_data(inputs: dict[str, Any], files: dict[str, bytes]) -> tuple[Any, dict[str, str]]:
    """Reconstruct the frozen expression only. No fitting, inference or live annotation."""
    import anndata as ad

    from backend.app.services.expression_scale import prepare_log_expression
    from backend.app.services.scientific_analysis import (
        _align_sources,
        _dense_matrix,
        _expression_view,
        _select_prediction_population,
    )

    paths, contract = inputs["files"], inputs["contract"]
    selection = contract["population_selection"]
    if selection.get("status") != "matched" or selection.get("perturbation") != inputs["perturbation"]:
        raise ExportBundleUnavailable("Frozen target-cell selection is unavailable")
    column = selection["perturbation_column"]
    predicted, actual = _select_prediction_population(
        ad.read_h5ad(paths["predicted.h5ad"]), column, inputs["perturbation"]
    )
    if actual != selection:
        raise ExportBundleUnavailable("Reconstructed prediction population differs from the frozen contract")
    sources = {"control": ad.read_h5ad(paths["control_path"]), "predicted": predicted}
    if "observed_path" in paths:
        observed = ad.read_h5ad(paths["observed_path"])
        if column not in observed.obs:
            raise ExportBundleUnavailable("Observed source lacks perturbation labels")
        sources["observed"] = observed[
            observed.obs[column].astype(str).str.strip().str.upper() == inputs["perturbation"]
        ].copy()
    key = inputs["assets"].get("expression_key") or inputs["assets"].get("input_embed_key")
    slots = {}
    identity = json.loads(files["gene_identity.json"])["sources"] if "gene_identity.json" in files else {}
    for name, source in sources.items():
        slots[name] = f"obsm[{key}]" if key and key != "X" and key in source.obsm else "X"
        strict = (
            bool(key)
            if name == "predicted"
            else bool(inputs["assets"].get("expression_key")) and name == "control"
        )
        source = _expression_view(
            prepare_log_expression(source, "log1p_cp10k"), key, paths["gene_list_path"], strict=strict
        )
        if source is None:
            raise ExportBundleUnavailable("Frozen expression source is unavailable")
        batch = contract.get("validation_population")
        if batch and batch.get("status") == "common_batches_only":
            if source.n_obs != batch["input_cells"][name]:
                raise ExportBundleUnavailable("Validation input population changed")
            source = source[source.obs[batch["batch_key"]].astype(str).isin(batch["common_batches"])].copy()
            if source.n_obs != batch["selected_cells"][name]:
                raise ExportBundleUnavailable("Validation batch population changed")
        if identity:
            columns = identity[name]["columns"]
            symbols = source.var.get("gene_symbol", source.var_names).astype(str).tolist()
            if [s.upper() for s in symbols] != [str(c["source_symbol"]).upper() for c in columns]:
                raise ExportBundleUnavailable("Frozen gene identity does not match source matrix")
            source.var["gene_symbol"] = [c["analysis_symbol"] for c in columns]
            source.var_names = pd.Index(source.var["gene_symbol"])
        sources[name] = source
    aligned, genes, _ = _align_sources(sources["control"], sources["predicted"], sources.get("observed"))
    saved = pd.read_csv(io.BytesIO(files["gene_deltas.csv"]), index_col=0)
    if genes != saved.index.tolist() or len(genes) != contract["gene_count"]:
        raise ExportBundleUnavailable("Frozen gene panel and expression matrix differ")
    frames = []
    var = pd.DataFrame(index=pd.Index(genes, name="gene"))
    var["gene_symbol"] = genes
    lookup = {row["analysis_symbol"]: row for row in identity.get("control", {}).get("columns", [])}
    for field in ("hgnc_id", "approved_symbol", "source_symbol"):
        var[field] = [lookup.get(g, {}).get(field) or "" for g in genes]
    for index, (name, source) in enumerate(zip(SOURCES, aligned, strict=True)):
        if source is None:
            continue
        values = np.asarray(_dense_matrix(source.X), dtype=float)
        if not np.isfinite(values).all() or np.any(values < 0):
            raise ExportBundleUnavailable("Expression matrix contains invalid log expression values")
        expected = saved[name] if name in saved else saved["control"] + saved["observed_delta"]
        if not np.allclose(values.mean(0), expected, rtol=1e-5, atol=3e-6):
            raise ExportBundleUnavailable(f"{name} means differ from frozen gene means")
        obs = source.obs[[field for field in OBS_FIELDS if field in source.obs]].copy()
        for field in obs:
            obs[field] = obs[field].astype(str)
        obs["source_cell_id"] = source.obs_names.astype(str)
        obs["celllens_source"] = name
        obs.index = pd.Index([f"{identifier}-{index}" for identifier in source.obs_names])
        frames.append(ad.AnnData(X=values, obs=obs, var=var.copy()))
    result = ad.concat(frames, join="outer", merge="same")
    if not result.obs_names.is_unique:
        raise ExportBundleUnavailable("Source cell IDs are not unique")
    return result, slots


def _single_cell(
    inputs: dict[str, Any],
    files: dict[str, bytes],
    prepared: dict[str, Any] | None,
    payloads: dict[str, bytes],
    manifest: dict[str, Any],
) -> None:
    from backend.app.services.cell_state import aligned_task_scores

    matrix, slots = _expression_data(inputs, files)
    ids = matrix.obs_names.astype(str).tolist()
    sources = matrix.obs["celllens_source"].astype(str).tolist()
    for name in ("metabolic_task_scores.csv", "reaction_scores.csv"):
        scores = _score_table(files, name)
        if scores is not None:
            aligned = aligned_task_scores(scores, ids, sources)
            payloads[f"original/{name}"] = _csv(aligned)
    if prepared is not None:
        if (
            prepared["ids"] != ids
            or prepared["sources"] != sources
            or prepared["genes"] != matrix.var_names.tolist()
        ):
            raise ExportBundleUnavailable("Prepared coordinates do not match exported cell identities")
        if not np.allclose(
            np.concatenate(list(prepared["matrices"].values())), matrix.X, rtol=1e-7, atol=1e-7
        ):
            raise ExportBundleUnavailable("Prepared expression differs from frozen source reconstruction")
        for space, projection in (("expression", prepared), ("metabolic", prepared.get("metabolic"))):
            if projection is None:
                continue
            for embedding, coordinate_key in (("pca", "coordinates"), ("umap", "umap")):
                if coordinate_key not in projection:
                    continue
                coordinates = (
                    projection[coordinate_key][0] if embedding == "umap" else projection[coordinate_key]
                )
                joined = np.concatenate([coordinates[source] for source in SOURCES if source in coordinates])
                if joined.shape != (matrix.n_obs, 2) or not np.isfinite(joined).all():
                    raise ExportBundleUnavailable("Frozen coordinates have invalid size or values")
                matrix.obsm[f"X_{space}_{embedding}"] = joined
    manifest["populations"]["original"]["expression_slots"] = slots
    actual_counts = {str(k): int(v) for k, v in matrix.obs.celllens_source.value_counts().items()}
    if actual_counts != manifest["populations"]["original"]["counts"]:
        raise ExportBundleUnavailable("Exported cell counts differ from original population metadata")
    matrix.uns["celllens_export"] = {
        "schema_version": 1,
        "run_id": inputs["run_id"],
        "expression_scale": "log1p_cp10k",
        "expression_units": "log1p(CP10K)",
        "predicted_values_are_measured_counts": False,
        "source_manifest_sha256": inputs["manifest_sha256"],
        "population": "original",
        "provenance_json": _json_bytes(
            {
                "source_hashes": manifest["source_sha256"],
                "selection": manifest["populations"]["original"],
                "expression_slots": slots,
            }
        ).decode("utf-8"),
        "embedding_note": "Only existing frozen coordinates are included; no fitting during export.",
    }
    if prepared is not None:
        metadata = {}
        for space, projection in (("expression", prepared), ("metabolic", prepared.get("metabolic"))):
            if projection is not None:
                metadata[space] = {"variance": projection["variance"]}
                if "umap" in projection:
                    metadata[space]["umap_parameters"] = projection["umap"][1]
                if "preprocessing" in projection:
                    metadata[space]["preprocessing"] = projection["preprocessing"]
        matrix.uns["celllens_export"]["embedding_metadata_json"] = _json_bytes(metadata).decode("utf-8")
    with tempfile.TemporaryDirectory(prefix="celllens-export-") as temporary:
        path = Path(temporary) / "expression_log1p_cp10k.h5ad"
        matrix.write_h5ad(path, compression="gzip")
        payloads["original/expression_log1p_cp10k.h5ad"] = path.read_bytes()
    payloads["original/cell_annotations.csv"] = _csv(matrix.obs)
    payloads["original/gene_annotations.csv"] = _csv(matrix.var)


def _network(
    files: dict[str, bytes], run_id: str, task_id: str, payloads: dict[str, bytes], manifest: dict[str, Any]
) -> None:
    if "task_trace.json" not in files:
        raise ExportBundleUnavailable("Frozen full task trace is unavailable")
    trace = json.loads(files["task_trace.json"])
    if trace.get("run_id") != run_id or trace.get("relationship_kind") != "knowledge_association":
        raise ExportBundleUnavailable("Frozen task trace identity or relation kind is invalid")
    tasks, reactions, genes = (trace[key] for key in ("tasks", "reactions", "genes"))
    # Validate closure of the full scientific source before selecting any subnetwork.
    if any(r not in reactions for t in tasks.values() for r in t["reaction_ids"]) or any(
        g not in genes for r in reactions.values() for g in r["gene_ids"]
    ):
        raise ExportBundleUnavailable("Frozen full trace has missing node references; network closure failed")
    if task_id and task_id not in tasks:
        raise ExportBundleUnavailable("Requested task is absent from the frozen full trace")
    chosen_tasks = {task_id: tasks[task_id]} if task_id else tasks
    reaction_ids = (
        set(r for task in chosen_tasks.values() for r in task["reaction_ids"]) if task_id else set(reactions)
    )
    gene_ids = set(g for r in reaction_ids for g in reactions[r]["gene_ids"]) if task_id else set(genes)
    rows, edges = [], []
    for kind, table in (
        ("task", chosen_tasks),
        ("reaction", {k: reactions[k] for k in sorted(reaction_ids)}),
        ("gene", {k: genes[k] for k in sorted(gene_ids)}),
    ):
        for identifier, record in table.items():
            rows.append(
                {
                    "id": f"{kind}:{identifier}",
                    "entity_id": identifier,
                    "kind": kind,
                    "units": trace["score_units"][kind],
                    **{
                        key: record.get(key)
                        for key in (
                            "label",
                            "category",
                            "subcategory",
                            "control",
                            "predicted",
                            "predicted_delta",
                            "observed_delta",
                            "coverage",
                            "evidence_level",
                            "gene_rule",
                        )
                    },
                }
            )
            targets = (
                record.get("reaction_ids", [])
                if kind == "task"
                else record.get("gene_ids", [])
                if kind == "reaction"
                else []
            )
            target_kind = "reaction" if kind == "task" else "gene"
            for target in targets:
                edges.append(
                    {
                        "source": f"{kind}:{identifier}",
                        "target": f"{target_kind}:{target}",
                        "interaction": "knowledge_association",
                        "kind": f"{kind}_to_{target_kind}",
                        "units": "relationship; no quantitative edge weight",
                        "directed": False,
                    }
                )
    payloads["network/nodes.csv"] = _csv(pd.DataFrame(rows), index=False)
    payloads["network/edges.csv"] = _csv(
        pd.DataFrame(
            edges, columns=pd.Index(["source", "target", "interaction", "kind", "units", "directed"])
        ),
        index=False,
    )
    payloads["network/task_trace.json"] = files["task_trace.json"]
    manifest["selection"] = {
        "scope": "task_subnetwork" if task_id else "all",
        "task_id": task_id or None,
        "source_counts": {"tasks": len(tasks), "reactions": len(reactions), "genes": len(genes)},
        "export_counts": {
            "tasks": len(chosen_tasks),
            "reactions": len(reaction_ids),
            "genes": len(gene_ids),
            "nodes": len(rows),
            "edges": len(edges),
        },
        "full_trace_included": True,
    }
    manifest["network"] = {
        "relationship_kind": "knowledge_association",
        "is_causal": False,
        "is_flux": False,
        "gene_rule_preserved": True,
    }


def _ranking(files: dict[str, bytes], payloads: dict[str, bytes], manifest: dict[str, Any]) -> None:
    table = pd.read_csv(io.BytesIO(files["gene_deltas.csv"]), index_col=0)
    values = np.asarray(pd.to_numeric(table["predicted_delta"], errors="coerce"), dtype=float)
    if not table.index.is_unique or not np.isfinite(values).all():
        raise ExportBundleUnavailable("Ranking requires unique genes and finite signed changes")
    identity = json.loads(files["gene_identity.json"]) if "gene_identity.json" in files else {}
    mapping = {
        c["analysis_symbol"]: c for c in identity.get("sources", {}).get("control", {}).get("columns", [])
    }
    symbols = [mapping.get(str(g), {}).get("approved_symbol") or str(g) for g in table.index]
    if len(set(symbols)) != len(symbols) or any(re.search(r"\s", g) for g in symbols):
        raise ExportBundleUnavailable("Ranking standard gene symbols are not unique portable identifiers")
    ranked = pd.DataFrame({"gene": symbols, "score": values}).sort_values(
        "score", ascending=False, kind="stable"
    )
    payloads["ranking/predicted_delta.rnk"] = ranked.to_csv(sep="\t", index=False, header=False).encode(
        "utf-8"
    )
    payloads["ranking/panel_background.txt"] = ("\n".join(symbols) + "\n").encode("utf-8")
    payloads["ranking/gene_identity.csv"] = _csv(
        pd.DataFrame(
            {
                "analysis_symbol": table.index,
                "gene_symbol": symbols,
                "hgnc_id": [mapping.get(str(g), {}).get("hgnc_id") for g in table.index],
            }
        ),
        index=False,
    )
    manifest["ranking"] = {
        "score": "signed predicted_delta",
        "units": "difference of mean(log1p(CP10K))",
        "is_log2_fold_change": False,
        "is_p_value": False,
        "gene_count": len(ranked),
        "background": "model gene panel only",
        "interpretation": "有限约2000基因面板的探索性排序；未执行富集或显著性检验。",
    }


def _optional_pdf(
    container: Any, run_id: str, files: dict[str, bytes], payloads: dict[str, bytes], manifest: dict[str, Any]
) -> None:
    from pydantic import ValidationError

    from backend.app.schemas import RunSummary
    from backend.app.services.pdf_report import build_report_pdf

    reason = None
    if "summary.json" not in files:
        reason = "未提供已冻结的报告摘要，PDF不可用。"
    else:
        try:
            RunSummary.model_validate_json(files["summary.json"])
        except ValidationError:
            reason = "历史摘要不满足当前报告schema，PDF不可用。"
    if reason is None:
        try:
            payloads["report.pdf"] = build_report_pdf(container, run_id)
        except ImportError:
            reason = "PDF渲染依赖不可用；原科学表与元数据仍随包提供。"
    if reason:
        manifest["optional_omissions"].append({"item": "pdf_report", "reason": reason})


def build_export_bundle(container: Any, run_id: str, package: str, *, task_id: str = "") -> tuple[bytes, str]:
    """Build a ZIP in memory; H5AD serialization uses an isolated system temporary folder."""
    if package not in {"analysis", "single-cell", "network", "ranking"}:
        raise ExportBundleUnavailable("Unknown scientific exchange package")
    if task_id and package != "network":
        raise ExportBundleUnavailable("Task selection applies only to the network package")
    snapshots: dict[Path, str] = {}
    try:
        root, source, source_sha = _source_manifest(container, run_id, snapshots)
        inputs = frozen_inputs(container, run_id)
        files = _original_files(root, source, snapshots)
        for path in inputs["files"].values():
            # frozen_inputs checks registered asset digests; track them through ZIP completion.
            snapshots[Path(path)] = file_sha256(Path(path))
        trace = json.loads(files["task_trace.json"]) if "task_trace.json" in files else {}
        panel = pd.read_csv(io.BytesIO(files["gene_deltas.csv"]), index_col=0).index.astype(str).tolist()
        identity = json.loads(files["gene_identity.json"]) if "gene_identity.json" in files else {}
        identities = {
            row["analysis_symbol"]: row
            for row in identity.get("sources", {}).get("control", {}).get("columns", [])
        }
        unresolved_hgnc = [gene for gene in panel if not identities.get(gene, {}).get("hgnc_id")]
        versions = {
            "analysis": inputs["contract"].get("analysis_version"),
            "code_sha256": source.get("code_sha256"),
            "model_id": inputs["assets"].get("model_id"),
            "database_version": trace.get("database_version"),
        }
        for library in ("anndata", "numpy", "pandas"):
            try:
                versions[library] = version(library)
            except PackageNotFoundError:
                versions[library] = "unavailable"
        manifest: dict[str, Any] = {
            "schema": "celllens-scientific-exchange-v1",
            "schema_version": 1,
            "run_id": run_id,
            "package": package,
            "cell_line": inputs["cell_line"],
            "perturbation": inputs["perturbation"],
            "source_run_id": inputs["source_run_id"],
            "source_manifest_sha256": source_sha,
            "source_sha256": {name: file_sha256(path) for name, path in inputs["files"].items()},
            "model_assets_sha256": {
                key: value for key, value in inputs["assets"].items() if key.endswith("_sha256")
            },
            "gene_identity": {
                "hgnc_resolved_count": len(panel) - len(unresolved_hgnc),
                "unresolved_hgnc_symbols": unresolved_hgnc,
                "unverified_approved_symbols": [
                    gene for gene in panel if not identities.get(gene, {}).get("approved_symbol")
                ],
                "unresolved_policy": "保留原冻结分析符号与空HGNC ID，不补造标识；RNK包含完整面板。",
            },
            "units": {
                "expression": "log1p_cp10k",
                "gene_means": "mean(log1p(CP10K))",
                "predicted_delta": "difference of mean(log1p(CP10K))",
                "task": "scCellFie task activity score",
                "reaction": "scCellFie reaction activity score",
            },
            "versions": versions,
            "populations": {"original": _population(inputs, files)},
            "selection": {"scope": "all", "task_id": None},
            "optional_omissions": [],
            "limitations": [
                "预测表达不是实测UMI counts；没有伪造raw/counts层。",
                "scCellFie分数不等于代谢通量；知识关联边不构成因果证据。",
                "原分析群体与共同批次实测诊断群体分别存放，不应混用。",
                "匹配实测诊断未核实训练排除，不能当作独立留出评测。",
                "未实际验证Seurat、Cytoscape、Prism等外部软件GUI导入。",
            ],
        }
        payloads: dict[str, bytes] = {}
        from backend.app.services.export_tables import table_metadata

        original_metadata = table_metadata(container, run_id, "original")
        original_metadata["counts"] = {
            name: manifest["populations"]["original"]["counts"].get(name, 0) for name in SOURCES
        }
        for name in SOURCES:
            original_metadata[f"n_{name}"] = original_metadata["counts"][name]
        manifest["populations"]["original"]["selection_id"] = original_metadata["selection_id"]
        manifest["seed"] = original_metadata["seed"]
        payloads["original/table_metadata.json"] = _json_bytes(original_metadata)
        if package in {"analysis", "single-cell"}:
            payloads.update({f"original/{name}": content for name, content in files.items()})
            comparison = _comparison(container, run_id, source_sha, payloads, snapshots)
            if comparison:
                manifest["populations"]["comparison"] = comparison
                comparison_metadata = table_metadata(container, run_id, "comparison")
                manifest["populations"]["comparison"]["selection_id"] = comparison_metadata["selection_id"]
                payloads["comparison/table_metadata.json"] = _json_bytes(comparison_metadata)
            else:
                manifest["optional_omissions"].append(
                    {"item": "comparison", "reason": "没有可核验的已冻结匹配实测诊断；本包不新增实测数据。"}
                )
            prepared = _prepared(container, inputs, payloads, snapshots)
            if prepared is None:
                manifest["optional_omissions"].append(
                    {
                        "item": "frozen_coordinates_and_figures",
                        "reason": "未提供已注册的冻结降维包；导出时不新算PCA/UMAP。",
                    }
                )
            if package == "analysis":
                _optional_pdf(container, run_id, files, payloads, manifest)
            if package == "single-cell":
                _single_cell(inputs, files, prepared, payloads, manifest)
        elif package == "network":
            _network(files, run_id, task_id, payloads, manifest)
        else:
            _ranking(files, payloads, manifest)
        manifest["counts"] = {
            "genes": inputs["contract"]["gene_count"],
            "original_cells": sum(manifest["populations"]["original"]["counts"].values()),
        }
        for name in SCIENTIFIC_FILES:
            if name not in files and package in {"analysis", "single-cell"}:
                manifest["optional_omissions"].append(
                    {"item": f"original/{name}", "reason": "原冻结manifest未登记此科学文件。"}
                )
        readme = (
            f"# CellLens 科研交换包\n\n运行：{run_id}\n包类型：{package}\n\n"
            "所有科学来源由已完成运行的manifest与SHA-256核验。\n\n"
            "original/ 是原分析群体；comparison/ 是独立共同批次实测诊断群体（如有），"
            "人数与筛选见manifest.json。H5AD仅包含original群体，comparison中的实测不会自动进入此矩阵。\n\n"
            "表达X为log1p(CP10K)，群体均值为mean(log1p(CP10K))；差值不是log2FC、p值或显著DEG。"
            "没有原始UMI counts、raw或counts层。网络仅表示知识关联，反应GPR作为属性保留；分数不是通量。"
            "RNK是完整模型面板有符号预测差值的探索性排序，应使用随附面板背景。\n\n"
            "匹配实测诊断未核实训练排除，不能当独立留出评测。细胞级统计不能代替生物学重复推断。"
            "prepared图与坐标仅来自已冻结文件，导出过程不运行模型、不拟合新PCA或UMAP。"
            "缺失选件见optional_omissions；未实测外部GUI导入。\n\n"
            "manifest.json记录单位、人数、版本、筛选、来源hash及所有载荷hash。\n"
        )
        payloads["README.md"] = readme.encode("utf-8")
        # Detect mutation during parsing/serialization, including after a prepared cache hit.
        if frozen_inputs(container, run_id)["manifest_sha256"] != source_sha:
            raise ExportBundleUnavailable("Frozen manifest changed during export")
        if str(container.store.get(run_id).status) != "completed":
            raise ExportBundleUnavailable("Run completion state changed during export")
        for path, digest in snapshots.items():
            if not path.is_file() or file_sha256(path) != digest:
                raise ExportBundleUnavailable(f"Frozen file hash changed during export: {path.name}")
        manifest["payload_sha256"] = {name: _digest(content) for name, content in sorted(payloads.items())}
        payloads["manifest.json"] = _json_bytes(manifest)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(payloads.items()):
                archive.writestr(name, content)
        return stream.getvalue(), f"CellLens_{run_id}_{package}.zip"
    except ExportBundleUnavailable:
        raise
    except (CellStateUnavailable, OSError, KeyError, TypeError, ValueError) as exc:
        raise ExportBundleUnavailable(str(exc)) from exc
