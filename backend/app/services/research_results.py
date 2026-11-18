"""Read-only adapters for existing measured and prediction artifacts.

No inference, dimensional reduction, score computation or historical file writes.
"""

import csv
import hashlib
import io
import json
import re
from pathlib import Path

from backend.app.core.run_manifest import file_sha256, manifest_hash
from backend.app.services.measured_results import confined, verified_result
from backend.app.services.measured_store import MeasuredStore

VERSION = "research-result-v1"
EXPRESSION_UNITS = "mean(log1p(CP10K))"
FUNCTION_UNITS = "expression-derived scCellFie task/reaction support score"


def availability(available, reason=None):
    return {"available": bool(available), "reason": None if available else reason or "产物未生成或元数据未知"}


def sanitize(value, *, public=False, field=None):
    """Keep source hashes/relative paths, omit credentials and machine-local locations."""
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            key = str(key)
            if re.search(r"password|secret|token|authorization|database_url|worker_id", key, re.I):
                continue
            clean_key = key
            if re.match(r"^[A-Za-z]:[\\/]|^/|^\\\\", key) or (public and key.lower().endswith(".h5ad")):
                clean_key = "private-input-" + hashlib.sha256(key.encode()).hexdigest()[:12]
            cleaned[clean_key] = sanitize(item, public=public, field=key)
        return cleaned
    if isinstance(value, list):
        return [sanitize(item, public=public, field=field) for item in value]
    if isinstance(value, str):
        if public and field and (field == "path" or field.endswith("_path") or field == "source_filename"):
            return "[private input location omitted]"
        if re.match(r"^[A-Za-z]:[\\/]|^/(?!api/)|^\\\\", value):
            return "[private local path omitted]"
        if re.match(r"^[a-z]+://[^/]*@", value, re.I):
            return "[credential-bearing URL omitted]"
        # Scientific dependency errors can contain a filesystem location inside a sentence.
        value = re.sub(r"(?i)(?<!\w)[a-z]:[\\/][^'\"\r\n<>]*", "[private local path omitted]", value)
        value = re.sub(r"(?<![\w:/])/(?!api/)[^\s'\"<>]+", "[private local path omitted]", value)
    return value


class ResearchResults:
    def __init__(self, container):
        self.container = container
        self.root = container.settings.project_root.resolve()
        self.prefix = container.settings.api_prefix

    def read(self, kind, identifier):
        result, _, _, _ = self.source(kind, identifier)
        return sanitize(
            result, public=getattr(self.container.settings, "deployment_mode", "local") == "public"
        )

    def source(self, kind, identifier):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifier):
            raise KeyError(identifier)
        if kind == "measured":
            return self._measured(identifier)
        if kind == "prediction":
            return self._prediction(identifier)
        raise ValueError("未知研究记录类型")

    def _base(self, kind, identifier, state, cell, target):
        return {
            "schema_version": VERSION,
            "result_id": f"{kind}:{identifier}",
            "record_kind": kind,
            "record_id": identifier,
            "state": state,
            "source_kind": "measured" if kind == "measured" else "prediction",
            "background": {"cell_line": cell},
            "target": {"perturbation": target},
            "groups": [],
            "units": {"expression": None, "delta": None, "function": None},
            "coverage": {"gene_count": None, "metabolism": None},
            "availability": {
                key: availability(False, "研究尚未完成")
                for key in ("expression", "function", "projection", "comparison", "export")
            },
            "provenance": {"manifest_sha256": None, "fingerprint_basis": None},
            "references": {},
            "limitations": [],
            "warnings": [],
        }

    def _measured(self, identifier):
        row, digest = MeasuredStore(self.container.store.session_factory).get(identifier)
        result = self._base("measured", identifier, row["status"], row["cell_line"], row["perturbation"])
        url = f"{self.prefix}/measured/analyses/{identifier}"
        result["references"] = {
            "detail": url,
            "summary": url,
            "genes": url + "/table?kind=genes",
            "tasks": url + "/table?kind=tasks",
            "projection": f"{self.prefix}/research/results/measured/{identifier}/projection",
            "download": url + "/download",
            "export": f"{self.prefix}/research/results/measured/{identifier}/export",
        }
        if row["status"] != "completed":
            return result, None, {}, {}
        directory, summary, manifest = verified_result(self.root, identifier, digest)
        if (
            summary.get("analysis_id") != identifier
            or summary.get("source_kind") != "measured"
            or summary.get("cell_line") != row["cell_line"]
            or summary.get("perturbation") != row["perturbation"]
        ):
            raise ValueError("实测结果的身份、背景或目标与记录不符")
        if set(summary.get("counts", {})) - {"control", "observed"}:
            raise ValueError("实测结果包含非实测群体")
        metabolism = summary.get("metabolism", {})
        expression_units = summary.get("expression_units")
        result.update(
            groups=[
                {"id": group, "source_kind": "measured", "count": count}
                for group, count in summary.get("counts", {}).items()
            ],
            units={
                "expression": expression_units,
                "delta": f"difference in {expression_units}; observed − control"
                if expression_units
                else None,
                "function": metabolism.get("units") if metabolism.get("available") else None,
            },
            coverage={"gene_count": summary.get("gene_count"), "metabolism": metabolism.get("coverage")},
            availability={
                "expression": availability("genes.csv" in manifest["files"]),
                "function": availability(
                    metabolism.get("available") and "tasks.csv" in manifest["files"], metabolism.get("reason")
                ),
                "projection": availability(
                    any(
                        value.get("available") and f"projection-{name}.json" in manifest["files"]
                        for name, value in summary.get("projections", {}).items()
                    )
                ),
                "comparison": availability(False, "此结果仅包含实测群体描述性比较，未运行预测"),
                "export": availability(True),
            },
            provenance={
                "manifest_sha256": digest,
                "fingerprint_basis": "manifest-file",
                "analysis_version": summary.get("analysis_version"),
                "source": sanitize(summary.get("provenance", {})),
                "batch_matching": summary.get("batch_matching"),
                "files": manifest["files"],
            },
            limitations=summary.get("limitations", []),
            warnings=summary.get("warnings", []),
        )
        return result, directory, summary, manifest

    def _prediction(self, identifier):
        record = self.container.store.get(identifier)
        result = self._base(
            "prediction",
            identifier,
            record.status.value,
            record.request.cell_line,
            record.request.perturbation,
        )
        url = f"{self.prefix}/runs/{identifier}"
        result["references"] = {
            "detail": url,
            "summary": url + "/summary",
            "genes": url + "/genes",
            "tasks": url + "/metabolic-tasks",
            "projection": f"{self.prefix}/research/results/prediction/{identifier}/projection",
            "download": url + "/report",
            "provenance": url + "/provenance",
            "export": f"{self.prefix}/research/results/prediction/{identifier}/export",
        }
        result["warnings"] = record.warnings
        if record.status.value != "completed":
            return result, None, {}, {}
        directory = confined(self.container.settings.derived_root, identifier)
        artifacts = {
            Path(item.relative_path).name: item for item in self.container.store.artifacts(identifier)
        }
        consumed_hashes = {}

        def read_file(name, required=False):
            path = confined(directory, name)
            if not path.is_file():
                if required:
                    raise ValueError(f"结果缺少 {name}")
                return None
            if path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("结果元数据超过读取上限")
            data = path.read_bytes()
            consumed_hashes[name] = hashlib.sha256(data).hexdigest()
            expected = artifacts.get(name)
            if expected and consumed_hashes[name] != expected.sha256:
                raise ValueError(f"结果文件校验失败：{name}")
            return json.loads(data)

        summary = read_file("summary.json", True)
        if not isinstance(summary, dict):
            raise ValueError("结果摘要必须是 JSON 对象")
        if summary.get("run_id") != identifier:
            raise ValueError("结果标识不匹配")
        synthetic = summary.get("result_kind") == "synthetic_demo" or (
            record.request.mode == "precomputed" and summary.get("result_kind") != "frozen_model_result"
        )
        if synthetic and not self.container.settings.allow_synthetic_results:
            raise ValueError("此记录为合成演示，未作为科学研究结果开放")
        manifest = read_file("manifest.json") or {}
        contract = read_file("expression_contract.json") or {}
        for document in (summary, manifest.get("request", {}), contract):
            if (
                document.get("run_id", identifier) != identifier
                or document.get("cell_line", record.request.cell_line) != record.request.cell_line
                or document.get("perturbation", record.request.perturbation) != record.request.perturbation
            ):
                raise ValueError("预测结果的身份、背景或目标与记录不符")
        # Verify the small scientific artifacts actually exposed by this adapter.
        files = {}
        unregistered_files = []
        for name in (
            "summary.json",
            "expression_contract.json",
            "gene_deltas.csv",
            "metabolic_task_scores.csv",
            "projection.json",
            "task_trace.json",
            "validation.json",
            "validation_metrics.json",
            "metabolic_coverage.csv",
        ):
            path = confined(directory, name)
            expected = manifest.get("outputs", {}).get(name, {})
            if not path.is_file():
                if expected:
                    raise ValueError(f"结果清单登记的文件缺失：{name}")
                continue
            digest = file_sha256(path)
            if name in consumed_hashes and digest != consumed_hashes[name]:
                raise ValueError(f"读取期间结果文件改变：{name}")
            expected_hash = expected.get("sha256") if isinstance(expected, dict) else expected
            if expected_hash and digest != expected_hash:
                raise ValueError(f"结果文件与清单不符：{name}")
            if name in artifacts and digest != artifacts[name].sha256:
                raise ValueError(f"结果文件与数据库不符：{name}")
            if not expected_hash:
                unregistered_files.append(name)
            files[name] = digest
        manifest_path = directory / "manifest.json"
        source_manifest_sha256 = consumed_hashes.get("manifest.json")
        if source_manifest_sha256 and file_sha256(manifest_path) != source_manifest_sha256:
            raise ValueError("读取期间结果清单改变")
        projected = None
        projection_reason = "没有经来源校验的现成表达投影；不会在读取时计算"
        if not synthetic:
            from backend.app.services.research_projection import prediction_projection

            try:
                projected = prediction_projection(self.container, identifier, "pca")
            except (ValueError, KeyError, OSError, ImportError, AttributeError) as exc:
                projection_reason = str(exc)
            else:
                projection_source = projected["provenance"]
                files[projection_source["artifact"]] = projection_source["projection_sha256"]
                if projection_source.get("prepared_manifest_sha256"):
                    files["cell_state/prepared.json"] = projection_source["prepared_manifest_sha256"]
                    unregistered_files.append("cell_state/prepared.json")
        if source_manifest_sha256 and not unregistered_files:
            fingerprint, fingerprint_basis = source_manifest_sha256, "manifest-file"
        else:
            fingerprint = manifest_hash({"source_manifest_sha256": source_manifest_sha256, "files": files})
            fingerprint_basis = "manifest-and-artifacts" if source_manifest_sha256 else "artifact-index"
        scale_known = (
            contract.get("analysis_version") == "expression-cp10k-v2"
            and contract.get("gene_units") == EXPRESSION_UNITS
        )
        scales = contract.get("source_scales", {})
        groups = [
            {"id": name, "source_kind": "prediction" if name == "predicted" else "measured", "count": None}
            for name in ("control", "predicted")
        ]
        if scales.get("observed"):
            groups.append({"id": "observed", "source_kind": "measured", "count": None})
        if synthetic:
            for group in groups:
                group["source_kind"] = "synthetic_demo"
        # Only use explicit saved counts. Projection display counts may be sampled.
        selection = contract.get("population_selection", {})
        validation = contract.get("validation_population") or {}
        counts = validation.get("selected_cells", {})
        if validation.get("status") == "unstratified":
            counts = validation.get("input_cells", {})
        for group in groups:
            count = counts.get(group["id"])
            if count is None and group["id"] == "predicted" and not counts:
                count = selection.get("selected_prediction_cells")
            if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
                group["count"] = count
        # Frozen per-cell analysis rows describe the analysed population, unlike projection samples.
        scores_expected = manifest.get("outputs", {}).get("metabolic_task_scores.csv")
        if scores_expected and "metabolic_task_scores.csv" in files:
            with confined(directory, "metabolic_task_scores.csv").open(
                encoding="utf-8-sig", newline=""
            ) as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames and "source" in reader.fieldnames and "score" not in reader.fieldnames:
                    score_counts = {group["id"]: 0 for group in groups}
                    identities = set()
                    for row in reader:
                        source = row["source"]
                        identity = (source, row.get(reader.fieldnames[0]))
                        if source not in score_counts or identity in identities:
                            raise ValueError("冻结分析细胞行来源未知或重复")
                        identities.add(identity)
                        score_counts[source] += 1
                    for group in groups:
                        if group["count"] is not None and group["count"] != score_counts[group["id"]]:
                            raise ValueError("冻结分析细胞行与原群体计数不一致")
                        group["count"] = score_counts[group["id"]]
        result.update(
            source_kind="synthetic_demo" if synthetic else "prediction",
            groups=groups,
            units={
                "expression": contract.get("gene_units") if scale_known else None,
                "delta": "difference in mean(log1p(CP10K)); predicted/observed − control"
                if scale_known
                else None,
                "function": FUNCTION_UNITS if summary.get("metabolic_tasks") else None,
            },
            coverage={"gene_count": contract.get("gene_count"), "metabolism": summary.get("coverage")},
            availability={
                "expression": availability("gene_deltas.csv" in files or bool(summary.get("top_genes"))),
                "function": availability(
                    bool(summary.get("metabolic_tasks")) or "metabolic_task_scores.csv" in files
                ),
                "projection": availability(projected is not None, projection_reason),
                "comparison": availability(
                    bool(scales.get("observed")) and scale_known and not synthetic,
                    "缺少匹配观测或已确认的真实结果表达尺度",
                ),
                "export": availability(True),
            },
            provenance={
                "manifest_sha256": fingerprint,
                "fingerprint_basis": fingerprint_basis,
                "source_manifest_sha256": source_manifest_sha256,
                "integrity": "registered_manifest"
                if "manifest.json" in artifacts
                else "read_time_fingerprint",
                "files_outside_source_manifest": unregistered_files,
                "analysis_version": contract.get("analysis_version"),
                "source": sanitize(manifest),
                "files": files,
                "population_selection": sanitize(selection),
                "validation_population": sanitize(contract.get("validation_population")),
            },
            warnings=summary.get("warnings", []),
            limitations=[
                "模型输出不是实测表达。",
                "匹配观测诊断不自动构成独立留出验证；训练排除信息以原记录为准。",
                "RNA 派生功能分数不等于实测通量、细胞器活性或形态。",
                "群体样本量缺失时保留未知，不以请求数量或投影采样点数代替。",
            ],
        )
        if not scale_known:
            result["limitations"].append("历史产物未记录 expression-cp10k-v2 契约；表达单位保留未知。")
        result["populations"] = {
            "original": {
                "availability": availability(True),
                "groups": groups,
                "selection": {"population_selection": selection, "validation_population": validation},
                "provenance": {
                    "manifest_sha256": source_manifest_sha256,
                    "fingerprint": fingerprint,
                    "files": files,
                },
            },
            "matched_comparison": {"availability": availability(False, "尚无已验证的匹配比较")},
        }
        public = getattr(self.container.settings, "deployment_mode", "local") == "public"
        if public:
            # Public result access never opens local private comparison files or their inputs.
            comparison_availability = availability(False, "公开模式不读取私有匹配比较")
        elif synthetic:
            comparison_availability = availability(False, "合成演示不提供真实匹配比较")
        else:
            from backend.app.services.measured_comparison import load_comparison

            try:
                comparison = load_comparison(self.root, identifier)
            except (ValueError, KeyError, OSError) as exc:
                comparison = None
                comparison_availability = availability(False, f"匹配比较来源校验未通过：{exc}")
            else:
                comparison_availability = availability(comparison is not None, "尚无已验证的匹配比较")
            if comparison:
                result["populations"]["matched_comparison"] = {
                    "availability": comparison_availability,
                    "groups": [
                        {
                            "id": key,
                            "source_kind": "prediction" if key == "predicted" else "measured",
                            "count": value,
                        }
                        for key, value in comparison.get("parameters", {})
                        .get("population_counts", {})
                        .items()
                    ],
                    "selection": comparison.get("population_matching"),
                    "provenance": {
                        "comparison_sha256": comparison["comparison_sha256"],
                        "manifest_sha256": comparison["comparison_manifest_sha256"],
                        "source": comparison.get("source"),
                        "binding": comparison.get("binding"),
                        "diagnostics": comparison.get("diagnostics_provenance"),
                    },
                    "evaluation_protocol": comparison.get("evaluation_protocol"),
                    "batch_sensitivity": comparison.get("batch_sensitivity"),
                    "warnings": comparison.get("warnings_zh", []),
                }
                result["references"]["comparison"] = url + "/comparison"
                result["provenance"]["original_fingerprint"] = fingerprint
                result["provenance"]["manifest_sha256"] = manifest_hash(
                    {
                        "original_fingerprint": fingerprint,
                        "comparison_sha256": comparison["comparison_sha256"],
                        "comparison_manifest_sha256": comparison["comparison_manifest_sha256"],
                        "diagnostics_sha256": comparison.get("diagnostics_provenance", {}).get(
                            "diagnostics_sha256"
                        ),
                    }
                )
                result["provenance"]["fingerprint_basis"] = "original-and-matched-comparison"
        result["availability"]["comparison"] = comparison_availability
        result["populations"]["matched_comparison"]["availability"] = comparison_availability
        return result, directory, summary, manifest

    def projection(self, kind, identifier, embedding="pca"):
        from backend.app.services.research_projection import (
            prediction_projection,
            projection_payload,
            read_json,
        )

        result, directory, _, manifest = self.source(kind, identifier)
        if directory is None or result["state"] != "completed" or result["source_kind"] == "synthetic_demo":
            raise ValueError("只有已完成的真实研究结果可读取表达投影")
        if kind == "prediction":
            payload = prediction_projection(self.container, identifier, embedding)
        else:
            name = f"projection-{embedding}.json"
            digest = manifest["files"].get(name)
            document = read_json(confined(directory, name), digest)
            payload = projection_payload(
                document,
                kind,
                embedding,
                {
                    "manifest_sha256": result["provenance"]["manifest_sha256"],
                    "projection_sha256": digest,
                    "artifact": name,
                },
            )
        payload["result_id"] = result["result_id"]
        payload["provenance"]["research_fingerprint"] = result["provenance"]["manifest_sha256"]
        return sanitize(
            payload, public=getattr(self.container.settings, "deployment_mode", "local") == "public"
        )

    def validate_selection(self, kind, identifier, selection):
        result, directory, summary, _ = self.source(kind, identifier)
        if directory is None or result["state"] != "completed" or not result["provenance"]["manifest_sha256"]:
            raise ValueError("仅完成且来源可校验的研究可以保存发现")
        allowed_groups = {x["id"] for x in result["groups"]}
        if not selection.get("projection_id"):
            matched = result.get("populations", {}).get("matched_comparison", {})
            if matched.get("availability", {}).get("available"):
                allowed_groups.update(x["id"] for x in matched.get("groups", []))
        if selection.get("group_id") and selection["group_id"] not in allowed_groups:
            raise ValueError("所选群体不属于此结果")
        if selection.get("projection_id"):
            allowed = {
                name for name, value in summary.get("projections", {}).items() if value.get("available")
            }
            if kind == "prediction":
                from backend.app.services.research_projection import prediction_projection

                prediction_projection(self.container, identifier, selection["projection_id"])
                allowed = {selection["projection_id"]}
            if selection["projection_id"] not in allowed:
                raise ValueError("所选投影不属于此结果")
        for key, names, column, fallback in (
            ("gene_id", ("genes.csv",) if kind == "measured" else ("gene_deltas.csv",), "gene", "top_genes"),
            (
                "task_id",
                ("tasks.csv",) if kind == "measured" else ("metabolic_coverage.csv",),
                "task",
                "metabolic_tasks",
            ),
        ):
            selected = selection.get(key)
            if not selected:
                continue
            known = {str(item.get("id", item.get(column))) for item in summary.get(fallback, [])}
            for name in names:
                path = directory / name
                if path.is_file():
                    with path.open(encoding="utf-8-sig", newline="") as handle:
                        for row in csv.DictReader(handle):
                            known.add(str(row.get(column, row.get("", ""))))
            if selected not in known:
                raise ValueError(f"所选 {key} 不属于此结果")
        return result

    def export(self, kind, identifier, findings):
        result, directory, summary, manifest = self.source(kind, identifier)
        if directory is None or not result["availability"]["export"]["available"]:
            raise ValueError("尚无可导出的完成结果")
        fingerprint = result["provenance"]["manifest_sha256"]
        public = getattr(self.container.settings, "deployment_mode", "local") == "public"
        if public:
            findings = []
        tables = {}
        names = (
            ("genes.csv", "tasks.csv", "reactions.csv")
            if kind == "measured"
            else (
                "gene_deltas.csv",
                "metabolic_coverage.csv",
            )
        )
        for name in names:
            path = confined(directory, name)
            if path.is_file():
                if path.stat().st_size > 16 * 1024 * 1024:
                    raise ValueError("结果表超过研究 JSON 导出上限，请使用原始结果下载")
                data = path.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                tables[name] = {
                    "population": "original",
                    "sha256": digest,
                    "rows": list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")))),
                }
                expected = result["provenance"]["files"].get(name)
                if expected and digest != expected:
                    raise ValueError("导出期间结果数值表改变，请重试")
        populations = result.get("populations", {})
        population_exports = {
            "original": {
                "availability": availability(True),
                "groups": result["groups"],
                "units": result["units"],
                "table_keys": list(tables),
                "selection": populations.get("original", {}).get("selection"),
                "provenance": populations.get("original", {}).get("provenance") or result["provenance"],
            },
            "matched_comparison": {
                "availability": populations.get("matched_comparison", {}).get("availability")
                or availability(False, "此研究没有已验证的匹配预测比较")
            },
        }
        matched = populations.get("matched_comparison", {})
        if kind == "prediction" and not public and matched.get("availability", {}).get("available"):
            from backend.app.services.measured_comparison import load_comparison

            comparison = load_comparison(self.root, identifier)
            expected = matched["provenance"]
            if not comparison or (
                comparison["comparison_sha256"] != expected["comparison_sha256"]
                or comparison["comparison_manifest_sha256"] != expected["manifest_sha256"]
                or comparison.get("diagnostics_provenance", {}).get("diagnostics_sha256")
                != (expected.get("diagnostics") or {}).get("diagnostics_sha256")
            ):
                raise ValueError("导出期间匹配比较或诊断改变，请重试")
            population_exports["matched_comparison"] = {
                **matched,
                "units": comparison.get("units"),
                "tables": {
                    name: {
                        "population": "matched_comparison",
                        "source_artifact": "comparison.json",
                        "source_sha256": comparison["comparison_sha256"],
                        "rows": comparison.get(name, []),
                    }
                    for name in ("genes", "tasks")
                },
                "metrics": {
                    key: comparison.get(key)
                    for key in ("expression", "differential_expression", "metabolic", "task_coverage")
                },
                "table_representation": "frozen comparison rows; coverage/diagnostics separately hash-bound",
            }
        return sanitize(
            {
                "schema_version": "research-export-v1",
                "result": result,
                "summary": summary,
                "summary_population": "original",
                "source_manifest": manifest,
                "source_manifest_population": "original",
                "source_manifest_representation": "sanitized_view; hash refers to original frozen bytes",
                "tables": tables,
                "tables_population": "original",
                "population_exports": population_exports,
                "findings": [
                    dict(item, matches_current_result=item["manifest_sha256"] == fingerprint)
                    for item in findings
                ],
                "reproducibility": "冻结数值表、来源哈希与选择注释；不包含原始细胞矩阵或模型权重。",
            },
            public=public,
        )
