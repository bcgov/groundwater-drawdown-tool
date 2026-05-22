---
title: Development setup
parent: Developer Guide
nav_order: 2
---

# Development setup

## Tooling

- **Python 3.13**, pinned via `.python-version`.
- **[uv](https://docs.astral.sh/uv/)** for environment, dependency, and
  Python interpreter management.
- **pytest** for tests.

## First-time setup (Windows)

Open PowerShell:

```powershell
# Install uv (skip if already installed)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Open a NEW PowerShell window so PATH picks up uv, then, in the
# project directory:
uv sync
```

No `.env` file is needed. BCGW credentials are entered at runtime through
the login UI. Optional override variables (logging level, output
directory, and so on) are documented in `config.py`; create a `.env`
only to change a default.

## Running the app

```powershell
uv run python -m gwdrawdown.app
```

Or double-click `run.bat`. The app serves at `http://localhost:8050`.

## Running the tests

```powershell
uv run pytest
```

Tests live in `tests/`, mirroring the package structure. Every function
in `core/` has tests; the math is validated against analytical reference
cases and against the legacy Excel example.

## Verifying the BCGW SQL

`scripts/smoke_test_db.py` prompts for BCGW credentials (via `getpass`),
opens the connection pool, runs each query against a known test point,
and prints the results. It never reads credentials from `.env` — the same
posture as the UI.

```powershell
uv run python scripts/smoke_test_db.py
```

Running an analysis (or the smoke test) requires a connection to the BC
government network or VPN, since both reach BCGW at `bcgw.bcgov:1521`.

## Coordinate reference systems

- User-facing coordinates: WGS84 (EPSG:4326).
- All processing and Oracle queries: BC Albers (EPSG:3005).
- Conversions live only in `core/crs_utils.py`, using
  `pyproj.Transformer` with `always_xy=True`.

## Previewing the documentation site

This site is built by GitHub Pages from the `docs/` folder using the
`just-the-docs` remote theme — no build step is required to publish. To
preview locally you can install Ruby and run `jekyll serve` from `docs/`,
but for most changes, editing the Markdown and pushing is enough.
