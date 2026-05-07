# Changelog

All notable changes to the Groundwater Drawdown Tool are recorded here.
Each release moves items from `[Unreleased]` into a versioned section.

The wording in this file is shown to end users when the tool auto-updates,
so write entries in plain English. Avoid jargon. Lead with what changed
from the user's perspective, not how it was implemented.

Format inspired by [Keep a Changelog](https://keepachangelog.com/) — Added,
Changed, Fixed, Removed.

## [Unreleased]

### Added

- Initial project scaffolding.
- Phase 1 skeleton: `src/gwdrawdown/` package layout (`core/`,
  `data_access/`, `ui/{pages,components}/`), `config.py` with hardcoded
  `BCGW_DSN` and env-overridable defaults, and an `app.py` stub that
  launches an empty Dash app on `localhost:8050` and logs the tool
  version on startup.
- Committed `uv.lock` for reproducible installs.
- Phase 2 core math (no UI): `core/units.py` (BCGW field conversions
  plus the CSV-driven pumping-rate unit table), `core/crs_utils.py`
  (WGS84 <-> BC Albers via cached `pyproj.Transformer`), `core/drawdown.py`
  (Cooper-Jacob with r->0.1 m fallback, u<0.01 validity check, and a
  superposition-ready signature accepting a list of pumping sources),
  `core/aquifer_lookup.py` (T/S defaults from `data/ts_lookup.csv`),
  `core/well_classification.py` (legacy `Impact!R` reassigned-material
  rule), `core/sad.py` (legacy `Impact!U` SAD formula with three
  status branches). All ported from the legacy Excel; verified against
  the canonical case (`Q=3.97 L/s, T=250 m^2/d, S=0.005, t=180 d,
  r=100 m`). 66 pytest tests, all passing.
- Phase 3 data access: `data_access/db.py` (lazy `oracledb` thin-mode
  pool; `init_pool` called by the future login handler, `get_connection`
  context manager that raises `PoolNotInitialisedError` pre-login,
  `close_pool` on logout/shutdown), `data_access/queries.py`
  (parameterised SQL templates for the four BCGW queries from
  `DATA_REFERENCE.md` §6: nearby wells with optional same-aquifer
  filter, aquifers-at-point returning a list for stacked polygons,
  subtype-code lookup, well-by-tag), `scripts/smoke_test_db.py`
  (`getpass`-based developer smoke test). Verified live against BCGW
  using the Cowichan Bay test point (intersects aquifer 186 sand &
  gravel and 198 bedrock); all four queries return sensible results.
  Three new optional config keys: `DB_POOL_MIN`, `DB_POOL_MAX`,
  `DB_POOL_INCREMENT` (defaults 1/2/1).
- Phase 4a auth shell: multi-page Dash app (`use_pages=True`),
  server-side sessions via Flask-Session (filesystem backend at
  `config.SESSION_DIR`, lifetime `config.SESSION_TIMEOUT_HOURS`),
  `/login` page that runs `SELECT 1 FROM DUAL` to verify BCGW
  credentials before calling `data_access.init_pool` and redirecting
  to `/setup`, Flask `/logout` route that closes the pool and clears
  the session, root redirect `/` -> `/setup` if authenticated else
  `/login`, footer component on every page showing version + signed-in
  user + Logout link. Setup and results pages are 4a stubs
  (sub-stages 4b and 4c will fill them in). Verified end-to-end in
  the browser with valid and invalid BCGW credentials.
- Phase 4c.1 results dashboard (read-only). Replaces the 4b text dump
  with a real layout: run-summary block (timestamp, BCGW user, source
  aquifer, T/S used with override marker, Q in m³/day, duration,
  buffer, filter), seven colour-coded stat cards (Total / OK /
  At risk / Insufficient / Suspect / Outside / Max drawdown),
  at-risk summary table (`InputValues!B30:E32` parity, descending by
  Impact %), and a full per-well table with the 17 columns from
  PROJECT_PLAN.md §4.1. Both tables are sortable / filterable, paginate
  at 10 rows / page, have a sticky header row, and live inside their
  own scroll containers so the horizontal scrollbar stays in view.
  Each table has a custom Export CSV button (no built-in export to
  avoid dash_table's fixed-columns layout bug); CSV reflects the
  current sort + filter state via `derived_virtual_data`. Status
  cells are colour-coded per `WellStatus`. New `WellResult` fields
  for total depth, stickup, and the per-well top-of-fracture/screen
  override (populated as None today; 4c.2 turns the latter three
  into editable cells with per-row live recompute). Auto-loaded
  `assets/styles.css` standardises dash_table's filter-row
  placeholder visibility on hover. New ts_overridden flag on
  `AnalysisInputs` so the run-summary can mark T/S as "(override)"
  when the officer customised them.
- Phase 4b setup page + analysis pipeline. New `core/flagging.py`
  combines drawdown + SAD into a `WellStatus` (OK / AT_RISK /
  INSUFFICIENT_DATA / SUSPECT_DATA / OUTSIDE_VALIDITY); SUSPECT_DATA
  fires when GWELLS reports static water level deeper than the well
  bottom (e.g. WTN 96473), so the UI can flag the baseline record
  for review rather than the proposed pumping. New `analysis.py`
  orchestrates BCGW queries -> per-well SI conversion -> Cooper-Jacob
  -> SAD -> classification -> flagging, with a pure
  `_compute_well_result` function that's unit-tested without a
  database. The Cooper-Jacob u<0.01 validity check is bypassed at
  the pipeline level pending client confirmation (math still computes
  u_max for diagnostics; revert is a one-line change). Real setup
  page replaces the 4a stub with three input modes (map click /
  lat-lon / WTN with auto-aquifer), source-aquifer picker for stacked
  polygons, T/S override checkbox with full-precision float display,
  pumping-rate dropdown driven by `data/unit_conversions.csv`,
  duration presets (30 d / 100 d / 1 yr / 10 yr), buffer radius
  (default 1000 m), same-aquifer filter (default on per Q12). Run
  Analysis opens results in a new browser tab via clientside
  callback so the user can iterate on the setup page without losing
  earlier results. Results page in 4b is a textual dump of the
  pipeline output (sub-stage 4c builds the chart, tables, and map).
  Hardened the auth shell: `is_authenticated()` now also verifies
  the BCGW pool is open (clears stale sessions left over from a
  previous app run); `SESSION_USE_SIGNER=True` so cookies issued
  before a `SECRET_KEY` rotation are rejected. 96 pytest tests
  passing (16 new flagging + 14 analysis); ruff clean.

### Removed

- `.env.example`. The tool runs without a `.env`; BCGW credentials are
  entered through the login UI at runtime. Override variables are
  documented in `README.md`.

## [0.1.0] — TBD

First development version. Not yet released to users.
