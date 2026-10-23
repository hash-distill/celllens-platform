# Measured-first analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development for the independent catalog/audit tasks and integrate task by task. Shared working tree; never reset, stage or commit unrelated changes.

**Goal:** 实测优先的公开扰动数据分析入口、真实覆盖目录、明确泛化边界，保留模型预测与评估。

**Architecture:** 固定源元数据覆盖服务与独立 CPU 实测任务；旧 STATE 管线不改变结果语义。新 MySQL 表和独立不可变产物保存实测分析；Vue 新页面与已有工作台联动。

**Tech Stack:** existing Vue 3/TypeScript/FastAPI/SQLAlchemy/Alembic/AnnData/scCellFie; no new dependency.

## Task 1: Source coverage and official-model boundary

Files: create backend/app/services/perturbation_catalog.py, backend/app/api/data_catalog.py, scripts/build_perturbation_catalog.py, backend/tests/test_perturbation_catalog.py, data/registry/perturbation_catalog.json; create frontend/src/api/dataCatalog.ts and frontend/src/views/DataCatalogView.vue. Parent integrates routers/navigation.

- [x] Add failing fixture tests for count aggregation, missing vs unknown, lookup, query pagination and measured-first action. Run `.venv/Scripts/python.exe -m pytest backend/tests/test_perturbation_catalog.py -q`, confirm expected missing implementation failures.
- [x] Implement contract with fixed context/target lookup, no arbitrary URL. Use function signatures `catalog_document(root: Path) -> dict`, `pair_detail(container, cell_line: str, perturbation: str) -> dict`, `query_pairs(container, *, cell_line=None, query='', availability='all', limit=50, offset=0) -> dict`. Rows: cell_line,perturbation,source_cell_count (int|null),source_status (measured|not_in_source|unknown),local_verified,local_measured_cells,model_supported,official_split,generalization_verified=false,recommended_action (measured|predict_exploratory|unsupported|check_source).
- [x] API GET /data-catalog, /data-catalog/pair?cell_line=&perturbation=, /data-catalog/download.csv. GETs no downloads or STATE execution. Query response items,total,summary,source,source_verified; summary per context and model-supported unmeasured count.
- [x] Build static catalog by reading fixed upstream obs only; annotate declared official split provenance without claiming checkpoint training exclusion. Save full omitted-measurement lists to reports/measured-first-2026-10-22. Verify content hash and counts. All background/perturbation source totals match input obs.
- [x] Build real frontend directory search/filter/table with clear local/source distinction; measured link `/measured?cell_line=...&perturbation=...`, prediction link `/workbench?cell_line=...&perturbation=...`; no automatic model submissions. Test + typecheck; no build until parent coordinates.

## Task 2: Independent measured CPU computation

Files: create backend/app/services/measured_inputs.py, measured_analysis.py, measured_worker.py, backend/tests/test_measured_analysis.py.

- [x] Write failure tests from tiny real AnnData fixtures: full common genes retained, 2 source groups control/observed only, exact observed_delta, no predicted keys, bad labels/scales rejected. Monkeypatch STATE to fail if accessed; scientifically correct mocks only for expensive scCellFie.
- [x] `prepare_inputs(root, request, staging, report)` reuses hash-valid registered control/observations; otherwise range-read only requested source rows, fixed revision, seed and cap. Reject empty observation and unknown source rather than model fallback. Copy metadata/provenance unchanged and validate finite expression/background/target/unique records.
- [x] `analyse_measured(root, request, inputs, output, report) -> dict` reads frozen log1p CP10K, aligns full common genes, writes genes.csv(control,observed,observed_delta), projection.json(control-reference PCA, joint UMAP), task/reaction score CSV and source manifest. Use existing scale, gene identity, frozen DB, completeness and ScCellFieEngine; no re-normalizing panel, no prediction. Missing optional metabolism/UMAP clearly warns while retaining real expression analysis.
- [x] Worker CLI runs the computation in a child, reports safe JSON progress, monitors parent. Atomic final publication only after required artifacts verify. Run focused tests then real public-source ALDOA analysis without STATE/GPU.

## Task 3: Persistence, API and lifecycle

Files: backend/app/db/models.py, new Alembic migration, backend/app/services/measured_jobs.py, backend/app/api/measured.py, backend/app/main.py, backend/tests/test_measured_api.py.

- [x] Write failed tests for POST/list/poll/read/download, source changes 409, cancellation cleanup and restart visibility. SQLite uses Base.create_all; MySQL migration only adds measured_analyses, does not alter runs or legacy tables.
- [x] New schema stores id,request_json,cell_line,perturbation,status,progress,message,manifest_sha256,created_at,updated_at. Use strict fixed-source requests and no user-controlled file paths. Manager one live task, OS lease, subprocess cancellation, failed/interrupted retries with new ID.
- [x] Measured manager starts independently from CELLLENS_WORKER_ENABLED / GPU flag. GET verifies manifest and relevant source hashes; CSV includes IDs/kind/counts/units; download package includes machine-readable source manifest. All errors actionable, no secret output.
- [x] Register routes and SPA paths; test resource/old-run regression. Use migrations and actual MySQL round trip.

## Task 4: Measured-first interface

Files: create frontend/src/api/measured.ts, frontend/src/views/MeasuredAnalysisView.vue, modify router/index.ts, AppHeader.vue, WorkbenchView.vue, ParamPanel.vue, HomeView.vue, AboutView.vue, RecordsView.vue.

- [x] Build measured selector, source coverage indication, start/cancel/progress/retry, verified result counts, mean differences, PCA/UMAP, gene/task tables, CSV/ZIP and history. Any unavailable optional section shows a clear state. No model weights/GPU prerequisite.
- [x] Home primary action measured analysis/data directory; existing workbench is model prediction. Route query selects declared cell/target; when measured exists show primary direct-analysis link and explicit evaluate-prediction action. Preserve predictive result routes and evaluation.
- [x] Use existing restrained research light/dark desktop design. Browser check real ALDOA path, source labels, no STATE calls, history reload, CSV/ZIP content; 1280/1440/1920 widths and both themes. Preserve query/download controls and do not duplicate POSTs on page load.

## Task 5: Generalization answer, docs and final review

Files: docs/GENERALIZATION.md, docs/MEASURED_ANALYSIS.md, docs/API.md, docs/DEPLOYMENT.md, docs/MODEL_AND_DATA.md, docs/guide/USER_GUIDE.md, docs/README.md, README.md, docs/verification/2026-10-22-measured-first.md.

- [x] Record exact supported/model-unmeasured/source-observed counts and source-limited interpretation. Model-vocabulary support, source absence, upstream declared test split and independently verified generalization are separate fields. Evaluate actual checkpoint/config provenance; report any unverifiable exclusion explicitly.
- [x] Rewrite page/README flow to data query → measured analysis, explicit prediction when needed, optional measured comparison. Show actual new commands and required MySQL migration; no fabricated accuracy, physical cell motion or measured flux.
- [x] Full tests `.venv/Scripts/python.exe -m pytest backend/tests -q --junitxml=reports/measured-first-2026-10-22/backend-tests.xml`, Ruff, BasedPyright, frontend typecheck/build; independent spec and quality review. Check old asset hashes and original result preservation. Reload own main server 8001, verify real new/old endpoints, end browser acceptance and save evidence.
