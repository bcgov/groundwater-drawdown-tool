# Groundwater Drawdown Tool — Developer README

A screening tool for BC Water Authorizations staff to estimate drawdown
impacts on nearby wells from a proposed groundwater withdrawal. Uses the
Cooper-Jacob (1946) distance-drawdown solution against well and aquifer data
in BC's Geographic Warehouse (BCGW).

This is the developer-facing README. For end-user installation, see
`CLIENT_INSTALL.md`.

## Documents to read first

| File | Purpose |
|---|---|
| `PROJECT_PLAN.md` | The spec. Architecture, phase plan, working agreements. |
| `DATA_REFERENCE.md` | BCGW column names, units, T/S lookup, SQL templates. |
| `DESIGN_NOTES.md` | Why Stage-1 choices look the way they do. |
| `CLAUDE_CODE_PROMPT.md` | Kickoff prompt for the Claude Code session. |

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
copy .env.example .env
# Edit .env with your BCGW credentials
```

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
├── .env.example                # optional override template; real .env is gitignored
├── version.txt                 # current tool version (single line, e.g. 0.1.0)
├── CHANGELOG.md                # human-readable release notes
├── README.md                   # this file (developer setup)
├── CLIENT_INSTALL.md           # end-user install steps
├── PROJECT_PLAN.md             # full spec
├── DATA_REFERENCE.md           # BCGW columns, T/S lookup, SQL, SAD logic
├── DESIGN_NOTES.md             # Stage-1 design rationale
├── CLAUDE_CODE_PROMPT.md       # Claude Code kickoff
├── setup.bat                   # first-run installer for end users
├── run.bat                     # daily-use launcher (calls update.bat in Phase 6+)
├── update.bat                  # auto-update from share (Phase 6+)
├── data/
│   ├── ts_lookup.csv           # T/S by aquifer subtype (Wei et al. 2009)
│   └── unit_conversions.csv    # Pumping rate unit table
├── references/
│   └── excel_chart_layout.md   # Phase 4 chart spec (matches legacy Excel)
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

## Environment variables (`.env`)

| Key | Required | Purpose |
|---|---|---|
| `BCGW_USER` | yes | Oracle username for BCGW |
| `BCGW_PASSWORD` | yes | Oracle password |
| `BCGW_DSN` | yes | Connection string (host:port/service) |
| `LOG_LEVEL` | no | Default: `INFO` |
| `OUTPUT_DIR` | no | Default: `./outputs` |
| `DASH_DEBUG` | no | Default: `false` |
| `DEFAULT_PUMPING_DURATION_DAYS` | no | Default: `100`. Placeholder, Q4/Q10. |
| `AT_RISK_DRAWDOWN_FRACTION` | no | Default: `0.30`. Placeholder, Q3. |
| `UPDATE_CHECK_SHARE` | no | Network share path for auto-update (Phase 6+). Empty disables the check. |

Missing required keys cause startup to fail loudly. Don't paper over this
with defaults.

## Known placeholders

These are tagged in code as `# CLIENT_TBD: Q<n>`. Grep for them when client
answers come in.

- **Q1** — T/S lookup by aquifer subtype. Now matches the legacy Excel
  `AquiferProperty_DB` (Wei et al. 2009 medians); effectively closed.
- **Q3** — at-risk drawdown threshold; default 30% of SAD (matches legacy
  Excel).
- **Q4 / Q10** — default pumping duration; default 100 days (matches legacy
  Excel for east-coast Vancouver Island; confirm for other regions).
- **Q5** — multi-well superposition not exposed in UI (single-well Stage 1).
  `core/drawdown.py` is already superposition-ready.
- **Q7** — legacy Excel received as `iMapBCDistDrawdown_20241108.xlsx`;
  now used as the validation harness for `core/drawdown.py`.
- **Q11** — SAD calculation for confined / bedrock wells. v1 uses the
  unconfined-style formula and flags these wells with a "manual review"
  note plus a per-well override field.
- **Q12** — single-aquifer filter default behaviour. v1 default-on.
- **Q13** — `> 5 ft` bedrock-depth threshold in the reassigned-material
  rule. v1 ports the legacy Excel verbatim.

Full list in `PROJECT_PLAN.md` section 7.

## Coordinate reference systems

- User-facing coordinates: WGS84 (EPSG:4326).
- All processing and Oracle queries: BC Albers (EPSG:3005).
- Conversions only in `core/crs_utils.py`, using `pyproj.Transformer` with
  `always_xy=True`.

## License

To be determined. For internal client delivery initially.
