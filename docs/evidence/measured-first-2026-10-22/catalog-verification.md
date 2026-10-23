# Fixed-source coverage verification

2026-10-22. The catalog was generated from the complete `obs.cell_line` and `obs.gene` columns of `arcinstitute/State-Replogle-Filtered`, revision `d790193bb2c93726541a75ca3fa873a92ed44da5`, file `replogle_concat.h5ad`.

The HDF5 obs index length and both metadata columns contain 643,413 rows. The script requests metadata through seekable range reads and never accesses `/X`: 13,631,488 requested bytes, versus a 30,010,775,846-byte source file. The metadata digest is SHA256 `2acd0107047319ee4d79a289aea68db2cee91425f34d5ef6a2fb14d70d51a9ec`, computed over source-order JSON `[cell_line,gene]` records followed by LF. All group counts, including non-targeting controls, sum to the input row total.

| Context | Source cells including control | Observed perturbation targets | Model vocabulary targets | Supported targets absent from this source |
|---|---:|---:|---:|---:|
| HepG2 | 96,616 | 1,340 | 2,023 | 683 |
| Jurkat | 184,470 | 1,537 | 2,023 | 486 |
| K562 | 188,590 | 1,383 | 2,023 | 640 |
| RPE1 | 173,737 | 1,499 | 2,023 | 524 |
| Total | 643,413 | 5,759 | 8,092 pairs | 2,333 |

The complete candidate universe contains 2,023 unique perturbation targets across four contexts, excluding the sole non-targeting control token. It is computed from the union of model vocabularies and observed source target labels. Source absence is scoped only to this filtered revision; it does not imply no experiment exists elsewhere. A missing, corrupt, incomplete or changed source index produces `unknown` with null source count, never zero.

The four pinned upstream TOML files are saved as `official-*.toml`, with SHA256 in the catalog. Test entry counts before excluding controls are HepG2 946, Jurkat 1,085, K562 969 and RPE1 1,061. The catalog annotates their declared test/val candidates, and explicitly leaves checkpoint training exclusion and generalization unverified. The short legacy K562 local evaluation list is not used as the full official list.

The `model-supported-without-source.csv` report contains all 2,333 supported source-absent pairs. The router's complete filtered CSV independently returns exactly 2,333 data rows; pagination affects the JSON list only. Source-absent records all retain `generalization_verified=False` and the fixed source revision. See `catalog-api-evidence.json` for the isolated router check using the real local registry.

All four local ALDOA observations pass registered SHA256 and actual HDF5 metadata checks: HepG2 96, Jurkat 75, K562 77, RPE1 70 cells. These local counts are separate from complete source coverage. No source downloads, extraction, model initialization or inference occur in the GET endpoints.

Validation: 18 catalog tests passed (`catalog-tests.xml`), with only existing FastAPI/Starlette test-client deprecation warnings. Two new source reader/split tests first failed with missing helper imports, then passed after implementation; three corrupt-local-registry cases first failed, then passed after defensive handling. Targeted Ruff and BasedPyright checks pass. `npm run typecheck` passes. Parent integration owns main-router registration, SPA routing, build and browser acceptance.
