# Measured perturbation comparison implementation plan

**Goal:** Attach genuine measured perturbation RNA to existing and future eligible model runs, with visible, reproducible comparisons.

**Architecture:** A pinned observation catalog identifies per-context/per-perturbation measured H5AD subsets. Independent comparison bundles bind original prediction manifests and inputs by hash, reuse the existing expression/scCellFie analysis contract, and never rewrite original run artifacts. A read-only API serves verified bundles; a new tab shows availability, source, populations, expression/DE metrics, baseline, full paired scatter and downloadable tables. Online runs prepare an optional bundle when matching observations exist. No missing measurement is synthesized.

**Tech stack:** Existing Python/AnnData/Scanpy/scCellFie, FastAPI, Vue/ECharts.

- [x] Write failing tests for catalog identity, no-observation behavior, complete paired data and tamper rejection.
- [x] Implement catalog and independent comparison builder/reader/API, retaining diagnostic and training-exclusion limits.
- [x] Extract pinned official observations for existing run contexts/perturbations; preserve row IDs and metadata, record genuine zero availability.
- [x] Build real comparison bundles without changing original predictions; cross-check selected expression metrics with installed official CellEval.
- [x] Add online preparation and visible comparison tab, honest unavailable state, examples, scatter, metrics, three-population values, source and export.
- [x] Run targeted then complete tests, type/build/static checks and real browser checks at desktop/mobile; document actual results and deployed service.

Acceptance: matching real observations produce comparison; unmatched context/target shows no fabricated values; zero changes remain in evaluation; population sizes and batch filtering are visible; worse-than-baseline results remain visible; original files retain hashes; all comparison downloads come from the same verified bundle.
