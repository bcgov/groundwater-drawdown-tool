# Groundwater Drawdown Tool — Developer README

A screening tool for BC Water Authorizations staff to estimate drawdown
impacts on nearby wells from a proposed groundwater withdrawal. Uses the
Cooper-Jacob (1946) distance-drawdown solution against well and aquifer data
in BC's Geographic Warehouse (BCGW).

This is the developer-facing README. For end-user installation, see
`CLIENT_INSTALL.md`.

The specifications are largely derived from the client’s previous solution, which relied on IMAP and Excel-based tools.

## Documents to read first

| File | Purpose |
|---|---|
| `PROJECT_PLAN.md` | The spec. Architecture, phase plan, working agreements. |
| `DATA_REFERENCE.md` | BCGW column names, units, T/S lookup, SQL templates. |

## Tooling

- Python 3.13, pinned via `.python-version`.
- `uv` for environment, dependency, and Python interpreter management.
- `pytest` for tests, run via `uv run pytest`.

## First-time developer setup (Windows)

Open PowerShell:

```powershell
# Install uv (skip if already installed)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Open a NEW PowerShell window so PATH picks up uv

# In the project directory:
uv sync
```

No `.env` file is needed. BCGW credentials are entered at runtime through
the login UI. Optional override variables (logging level, output dir, etc.)
are listed below — create a `.env` only if you need to change a default.

Run the app:

```powershell
uv run python -m gwdrawdown.app
```

Or just double-click `run.bat`.

Run tests:

```powershell
uv run pytest
```

## Project layout

```
groundwater-drawdown-tool/
├── pyproject.toml              # uv-managed deps + project metadata
├── uv.lock                     # locked versions, committed
├── .python-version             # pins Python 3.13
├── version.txt                 # current tool version (single line, e.g. 0.1.0)
├── CHANGELOG.md                # human-readable release notes
├── README.md                   # this file (developer setup)
├── CLIENT_INSTALL.md           # end-user install steps
├── PROJECT_PLAN.md             # full spec
├── DATA_REFERENCE.md           # BCGW columns, T/S lookup, SQL, SAD logic
├── DESIGN_NOTES.md             # Stage-1 design rationale
├── setup.bat                   # installer / updater (bootstrap or local mode)
├── run.bat                     # daily-use launcher
├── data/
│   ├── ts_lookup.csv           # T/S by aquifer subtype (Wei et al. 2009)
│   └── unit_conversions.csv    # Pumping rate unit table
├── references/
│   └── excel_chart_layout.md   # Phase 4 chart spec (matches legacy Excel)
├── scripts/
│   ├── publish_release.ps1     # developer: cut a GitHub Release (see below)
│   └── smoke_test_db.py        # developer: verify BCGW SQL with getpass prompt
├── src/
│   └── gwdrawdown/
│       ├── __init__.py
│       ├── app.py              # Dash entry point
│       ├── config.py           # env-driven config
│       ├── core/               # pure math, no Dash, no DB
│       │   ├── __init__.py
│       │   ├── crs_utils.py
│       │   ├── units.py
│       │   ├── drawdown.py
│       │   ├── aquifer_lookup.py
│       │   ├── well_classification.py  # reassigned aquifer material
│       │   ├── sad.py                  # Safe Available Drawdown
│       │   └── flagging.py             # OK / AT_RISK / INSUFFICIENT_DATA / OUTSIDE_VALIDITY
│       ├── data_access/        # BCGW Oracle access
│       │   ├── __init__.py
│       │   ├── db.py
│       │   └── queries.py
│       └── ui/                 # Dash only
│           ├── __init__.py
│           ├── pages/
│           │   ├── setup_page.py
│           │   └── results_page.py
│           └── components/
└── tests/
    ├── test_drawdown.py
    ├── test_units.py
    ├── test_crs_utils.py
    └── test_aquifer_lookup.py
```

## Layer rules (enforced by review, not by import linting yet)

```
ui  →  core, data_access  →  config
```

- `ui/` may import from `core/` and `data_access/`.
- `core/` imports neither Dash nor `data_access/` nor the database.
- `data_access/` imports `config/` only.
- `config/` reads environment variables.

Why: see `DESIGN_NOTES.md`.

## Optional environment overrides

The tool ships with sensible defaults for every tunable. Create a `.env`
file at the project root only if you need to override one. BCGW credentials
are **not** in here — they are entered at runtime through the login UI.

| Key | Default | Purpose |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `OUTPUT_DIR` | `./outputs` | Where CSV / GeoJSON / PDF exports are written |
| `DASH_DEBUG` | `false` | Enable Dash hot-reload during development |
| `DEFAULT_PUMPING_DURATION_DAYS` | `100` | Legacy Excel default. CLIENT_TBD: Q4, Q10. |
| `AT_RISK_DRAWDOWN_FRACTION` | `0.30` | Drawdown / SAD ratio that flags a well at-risk. CLIENT_TBD: Q3. |
| `COOPER_JACOB_U_THRESHOLD` | `0.01` | Validity threshold for `u = r²S / (4Tt)` |
| `SESSION_TIMEOUT_HOURS` | `8` | Inactive session expiry before re-login |


## Coordinate reference systems

- User-facing coordinates: WGS84 (EPSG:4326).
- All processing and Oracle queries: BC Albers (EPSG:3005).
- Conversions only in `core/crs_utils.py`, using `pyproj.Transformer` with
  `always_xy=True`.

## Publishing a release

End users install and update the tool by downloading a single `setup.bat`
from the latest GitHub release. The publish workflow lives in
`scripts/publish_release.ps1`. See `PROJECT_PLAN.md` §6 for the full design.

One-time prerequisites on the developer's machine:

```powershell
winget install GitHub.cli
gh auth login    # authenticate against github.com/bcgov/groundwater-drawdown-tool
```

To cut a release:

1. Bump `version.txt` (e.g. `0.4.0` → `0.5.0`).
2. Move the relevant entries in `CHANGELOG.md` from `[Unreleased]` into a
   new versioned section `## [0.5.0] — YYYY-MM-DD`. The script extracts
   this section as the GitHub release notes.
3. Commit those two changes on `main` and push.
4. From the repo root, run:

   ```powershell
   .\scripts\publish_release.ps1
   ```

   The script verifies a clean tree, runs `uv run pytest`, builds
   `groundwater-drawdown-tool.zip`, tags `v<version>`, pushes the tag, and
   creates the GitHub release with `setup.bat` and the zip as assets.

5. Verify the release page:
   <https://github.com/bcgov/groundwater-drawdown-tool/releases>

End users (existing installs) pick up the new version on next re-run of
their downloaded `setup.bat`. New users grab `setup.bat` from
<https://github.com/bcgov/groundwater-drawdown-tool/releases/latest/download/setup.bat>.

Add `-Draft` to publish a draft release for pre-release review:

```powershell
.\scripts\publish_release.ps1 -Draft
```

## License

To be determined.
