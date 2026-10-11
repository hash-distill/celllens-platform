# User Data Analysis Implementation Plan

> For agentic workers: use executing-plans to implement the approved scope inline. User authorization already covers implementation; no new approval or delegation is required.

**Goal:** Add authenticated private H5AD datasets and CPU downstream analyses with usable frontend pages.

**Architecture:** Add users, sessions, datasets and analyses alongside existing run tables. Reuse frozen scientific contracts without changing public preset run records. Persist queue state in SQL and expose ownership-checked files through API routes.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, AnnData, NumPy/SciPy, scCellFie, Vue/TypeScript, ECharts.

## 1. Identity and persistence

Files: `backend/app/user_data/{models,store,auth}.py`, `backend/app/db/migrations/versions/0002_user_data.py`, `scripts/manage_users.py`.

- [x] Write and run failing tests in `backend/tests/test_user_data.py`: login with wrong password returns 401; valid login gives HttpOnly cookie; missing CSRF rejects writes; a second user gets 404 on another user's dataset and job.
- [x] Implement salted password hashing and expiring opaque sessions. Create four additive tables with foreign keys. Use random identifiers and owner predicates for every private read.
- [x] Verify with `.venv/Scripts/python.exe -m pytest backend/tests/test_user_data.py -q`.

```python
assert client.post('/api/v1/auth/login', json={'username': 'alice', 'password': 'wrong'}).status_code == 401
assert other.get(f'/api/v1/datasets/{dataset_id}').status_code == 404
```

## 2. Validated datasets

Files: `backend/app/user_data/{datasets,api,schemas}.py`, settings and multipart dependency.

- [x] Add failing tests for corrupted H5AD, duplicates, negative values, noninteger counts, absent library totals, external links and size limits; verify no rejected upload file remains.
- [x] Validate HDF5 dimensions before AnnData loads data. Accept explicitly declared X/layer and scale. Store immutable metadata, SHA-256, shape, grouping columns and STATE compatibility report. Implement list/details/download/archive with ownership checks.
- [x] Verify canonical CP10K normalization uses original full-library totals before any gene selection.

```python
assert np.allclose(prepared.X.toarray().sum(axis=1), 10000)
assert response.status_code == 422
```

## 3. Analysis worker

Files: `backend/app/user_data/{analysis,worker}.py`, container and lifespan integration.

- [x] Write failing numerical tests for QC, PCA provenance, descriptive reference-group differences and completed-result artifact hashes.
- [x] Implement exploration and metabolic analyses using all uploaded genes, original cell IDs and frozen official completeness. Publish full CSV/JSON artifacts only after success; record failures. Serialize CPU claims with a database advisory lock and recover running jobs only under that lock.
- [x] Verify actual scCellFie output on a small human panel, plus task restart and input-hash mismatch behavior.

```python
assert report['provenance']['source_sha256'] == dataset['sha256']
assert report['comparison']['method'] == 'difference_of_group_means'
```

## 4. Frontend

Files: login/data/analysis Vue pages, user-data API client and types, navigation/router.

- [x] Build login and administrator account creation forms; data upload declares units and matrix scope. Show private dataset list, validation summary, SHA, grouping and archive actions.
- [x] Build analysis creation and status polling with CPU prerequisites, PCA plot, gene/quality tables, metabolic summary, official completeness and authenticated artifact download links.
- [x] Run `npm --prefix frontend run typecheck` and `npm --prefix frontend run build`; exercise the full browser workflow against an isolated SQLite verification server and real scientific assets.

## 5. Documentation and integration

Files: `.env.example`, `.gitignore`, `README.md`, `docs/guide/USER_DATA.md`, deployment and MySQL verification script.

- [x] Preserve existing README changes. Document schema migration, account creation, resource limits, CPU enablement, human-only metabolic analysis and STATE boundary.
- [x] Run all backend tests, Ruff, basedpyright, frontend build and `git diff --check`. Verify additive migration on SQLite and current MySQL without altering existing frozen assets.
- [x] Commit the feature separately from unrelated changes and push the reviewable branch with the existing remote authorization.
