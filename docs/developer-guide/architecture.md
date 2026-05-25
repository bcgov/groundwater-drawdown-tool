---
title: Architecture
parent: Developer Guide
nav_order: 1
---

# Architecture

## The layer model

The codebase has three layers with a strict one-way dependency:

```
ui  →  core, data_access  →  config
```

- **`ui/`** may import from `core/` and `data_access/`. No reverse
  imports.
- **`core/`** has zero dependencies on Dash, on `data_access/`, or on the
  database. It is pure functions over plain types (floats, dicts, pandas
  DataFrames).
- **`data_access/`** may import from `config/` only.
- **`config/`** reads environment variables. No hardcoded paths or
  credentials anywhere else in the codebase.

The point of the separation: `core/` is unit-testable without a database
and reusable from a future CLI or ArcGIS Pro toolbox without changes.

## Package layout

The tool is packaged as `src/gwdrawdown/`:

```
src/gwdrawdown/
├── app.py              Dash entry point (multi-page)
├── config.py           Single source of runtime configuration
├── analysis.py         Pipeline orchestration
├── usage_logger.py     Per-run usage logging
├── core/               Pure math — no Dash, no DB
│   ├── units.py                Unit conversions
│   ├── crs_utils.py            WGS84 ↔ BC Albers transforms
│   ├── drawdown.py             Cooper-Jacob distance-drawdown
│   ├── aquifer_lookup.py       Default T/S by aquifer subtype
│   ├── well_classification.py  Reassigned aquifer material rule
│   ├── sad.py                  Safe Available Drawdown
│   └── flagging.py             OK / AT_RISK / INSUFFICIENT_DATA / …
├── data_access/        BCGW Oracle access
│   ├── db.py                   Lazy oracledb connection pool
│   └── queries.py              Parameterised SQL templates
└── ui/                 Dash only
    ├── pages/                  login, setup, results
    └── components/             charts, tables, map, exports, footer
```

## Key modules

- **`config.py`** — the single source of truth for runtime configuration.
  The BCGW connection string is a hardcoded constant
  (`bcgw.bcgov:1521/idwprod1.bcgov`); it is not secret and never changes.
  Optional overrides are read from environment variables (and a `.env`
  file if present), but the tool runs with no `.env`.

- **`core/drawdown.py`** — the Cooper-Jacob (1946) distance-drawdown
  calculation. It accepts a list of pumping sources and sums their
  contributions linearly, so multi-well superposition is available in the
  math even though the v1 UI exposes a single well.

- **`core/sad.py`** — Safe Available Drawdown: 70% of available drawdown.
  Confined and bedrock wells are flagged for manual review and accept a
  per-well `top_of_fracture_or_aquifer_or_screen_m` override.

- **`data_access/db.py`** — the `oracledb` thin-mode connection pool. The
  pool is created lazily by the login handler once a user has entered
  valid BCGW credentials, not at app startup.

- **`analysis.py`** — orchestrates the pipeline: queries → SI conversion
  → Cooper-Jacob → SAD → classification → flagging. `_compute_well_result`
  is a pure function, unit-tested without a database.

## Working agreements

- No Dash imports anywhere in `core/` or `data_access/`.
- No SQL strings outside `data_access/queries.py`.
- No hardcoded paths — anything filesystem-related goes through `config`.
- Use `logging`, never `print`. Use `pathlib.Path`, never raw strings.
- Type hints on all public signatures; `from __future__ import
  annotations` at the top of every module.
- Tests for every function in `core/`, mirroring the package structure.

The full specification — including the Cooper-Jacob equation, the SAD
formula, and the at-risk rules — is in `PROJECT_PLAN.md`; see
[Reference documents]({{ site.baseurl }}{% link developer-guide/reference.md %}).
