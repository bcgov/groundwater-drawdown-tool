# Groundwater Drawdown Tool — Project Plan

## 1. Purpose

A screening / decision-support tool for BC Water Authorizations staff (Groundwater
Allocation Team) to estimate drawdown impacts at nearby wells from a proposed
groundwater withdrawal, supporting licence application reviews under the Water
Sustainability Act.

The tool predicts how much groundwater levels in nearby registered wells (from BC's
GWELLS database) may decline due to a proposed pumping well at a chosen location,
using the Cooper-Jacob (1946) distance-drawdown solution.

Results are screening-level estimates, intended to be reviewed by qualified
hydrogeologists. The tool is **not** a replacement for professional assessment.

## 2. Goals for Stage 1

- Local execution on user's Windows machine. No deployment, no central server.
- Open-source Python stack: Dash, oracledb (thin), pyproj, pandas, plotly, dash-leaflet.
- `uv` + `pyproject.toml` + `uv.lock` for environment management.
- Python 3.13 pinned via `.python-version`.
- One-time setup via `setup.bat`; daily use via `run.bat`.
- Architecture clean enough that Stage 2 (deployment to Posit Connect or similar)
  is mostly packaging work, not a rewrite.

## 3. Non-goals for Stage 1

- No web deployment, no containerisation, no Dockerfile.
- No authentication system (single-user, local).
- No database other than BCGW Oracle (read-only).
- No persistent storage of past analyses (each run is independent).
- No automated tests beyond the core math modules (Cooper-Jacob, units, CRS).

## 4. Architecture

Three layers with strict one-way dependency:

```
ui  →  core, data_access  →  config
```

- `ui/` may import from `core/` and `data_access/`. No reverse imports.
- `core/` has zero dependencies on Dash, on `data_access/`, or on the database.
  Pure functions over plain types (floats, dicts, pandas DataFrames).
- `data_access/` may import from `config/` only.
- `config/` reads environment variables. No hardcoded paths or credentials anywhere
  else in the codebase.

The point of this separation: `core/` is unit-testable without a database, and
re-usable from a future ArcGIS Pro Python Toolbox (`.pyt`) or CLI without changes.

### 4.1 Module responsibilities

**`config.py`** — single source of truth for all runtime configuration. Holds
non-secret constants (BCGW DSN, threshold defaults, etc.) and reads any
optional overrides from environment variables (loaded from `.env` if present).
No defaults that hide misconfiguration: if a required value is missing, fail
loud at startup, don't silently use a placeholder.

The BCGW connection string is hardcoded as a constant:

```python
BCGW_DSN: Final[str] = "bcgw.bcgov:1521/idwprod1.bcgov"
```

It is not user-specific, not secret, and never changes. Putting it in
`.env` would only create an opportunity for users to mistype it. If BC ever
changes the host, that's a code release, not a config edit.

User credentials are **not** stored anywhere. Each user enters their BCGW
username and password through the login UI on every session. See
`DESIGN_NOTES.md` for the rationale.

**`core/units.py`** — every unit conversion needed by the tool, in one place,
with tests. BCGW gives us feet (depths, water levels) and US gallons per minute
(yield); the T/S lookup is in m²/day and dimensionless; Cooper-Jacob expects
SI throughout. This is where unit bugs hide if they're scattered. See
`DATA_REFERENCE.md` for the full list of source units.

In addition to BCGW field conversions, this module provides the **pumping-rate
unit table** that drives the Q-input dropdown on the setup page. The legacy
Excel tool (`Lookup_DB!B3:I10`) supported: Imp GPM, L/min, L/s, m³/d, m³/min,
m³/s, US GPM. The current tool uses a curated subset of that list: L/min,
L/s, m³/d, m³/min, m³/s, m³/yr, with a default of m³/d. All inputs are converted
to m³/day before reaching `core/drawdown.py`. The conversion factors are
sourced from `data/unit_conversions.csv` so they can be reviewed without
touching code.

**`core/crs_utils.py`** — WGS84 (EPSG:4326) ↔ BC Albers (EPSG:3005) using `pyproj`
with `always_xy=True`. Used both for inbound user coordinates (lon/lat from the
map click) and for outbound results display.

**`core/drawdown.py`** — Cooper-Jacob distance-drawdown calculation:
 
```
s(r, t) = (Q / (4πT)) * ln(2.25 * T * t / (r² * S))
```

(equivalently, `s = 2.303*Q / (4πT) * log10(2.25*T*t / (S*r²))` — the form
used in the legacy Excel tool. Implementations are mathematically identical.)

Inputs (all SI): Q in m³/day, T in m²/day, S dimensionless, r in m, t in days.
Output: drawdown s in metres.

**`r → 0` fallback.** When the observation well is the same point as the
pumping well (`r = 0`), the equation is undefined. Match the legacy Excel
behaviour: substitute `r = 0.1 m` so the pumping well itself returns a
finite, large drawdown rather than an error or NaN. This is documented in
the legacy tool at `Impact!Q2` and is the convention the Water Officer team
already uses.

**Superposition-ready signature.** Although the UI in v1 only exposes
single-well input (Q5 deferred), the function should accept a list of
pumping sources (each with its own Q, T, S, location, start time) and
sum their drawdown contributions linearly at each observation point.
This is mathematically free — Cooper-Jacob is linear in Q — and avoids a
later refactor when Q5 is confirmed.

Must include a validity check:

```
u = r²S / (4Tt)
```

Cooper-Jacob is only valid when `u < 0.01` (some sources allow `u < 0.05`). If `u`
exceeds the threshold for a given (r, t), the function should not return a number
silently — it should return a result object that flags the well as "outside
validity range". The UI surfaces this as a separate category from valid results.

**`core/aquifer_lookup.py`** — given an `AQUIFER_SUBTYPE_CODE` (e.g. `"1a"`,
`"4b"`, `"5b"`), return default T and S. Loaded from `data/ts_lookup.csv`. Codes
not in the table, or codes flagged as `not valid` in the lookup, return a
sentinel that the UI handles by requiring manual T/S entry.

**`core/well_classification.py`** — implements the legacy "reassigned aquifer
material" rule (`Impact!R` in the Excel tool). Given a well's
`FINISHED_WELL_DEPTH` and `BEDROCK_DEPTH` (both in metres after unit
conversion), classify the well as:

```
if BEDROCK_DEPTH is not null:
    if (FINISHED_WELL_DEPTH - BEDROCK_DEPTH) > 5:  # 5 ft, ~1.5 m
        return "Bedrock"
    else:
        return "Unconsolidated"
elif AQFR_MTRL from GWELLS is populated:
    return AQFR_MTRL
else:
    return "Unassigned"
```

The 5-unit threshold in the legacy Excel is in feet (the underlying values
are in feet there). When porting to SI, convert the threshold accordingly.
Client-confirmed (Q13): v1 keeps the `> 5 ft` rule.

This classification is shown alongside the GWELLS-reported `AQFR_MTRL` in
the results table, not as a replacement.

**`core/sad.py`** — computes Safe Available Drawdown for each well. SAD is
70% of available drawdown. Available drawdown depends on aquifer type
(see legacy deck slide 7):

- **Unconfined sand and gravel:** measured to *bottom of well*. Available
  drawdown = `well_bottom - non_pumping_water_level + stickup`.
- **Confined aquifer:** measured to *top of aquifer*, not well bottom.
  Over-pumping a confined aquifer below the top causes dewatering.
- **Fractured bedrock:** measured to *uppermost major water-bearing
  fracture* (read from driller's log).

For v1, match the legacy Excel exactly:

```python
# Pseudo-code matching Impact!U2 in the Excel tool
top = top_of_fracture_or_aquifer_or_screen_m  # user override if provided
if top is None:
    top = finished_well_depth_m  # fallback for unconfined case

if top is None:
    return SADResult(value=None, status="no Well Depth")
if non_pumping_water_level_m is None:
    return SADResult(value=None, status="no NPL")

stickup = stickup_m if stickup_m is not None else 0.0
available_drawdown = top - non_pumping_water_level_m + stickup
sad = available_drawdown * 0.7
```

For confined and bedrock wells, the unconfined-style formula
**over-estimates SAD**. Flag these wells with a "manual review of driller's
log recommended" note in the results table, and expose a per-well override
field `top_of_fracture_or_aquifer_or_screen_m` that the Water Officer can
fill in by reading the driller's log. Client-confirmed (Q11): v1 stays
with the manual-override approach rather than automating SAD for confined
cases.

**`core/flagging.py`** — given predicted drawdown for a well and the well's
SAD result, classify as:
- `OK` — drawdown impact < 30% of SAD (or threshold is configurable).
- `AT_RISK` — drawdown impact ≥ 30% of SAD.
- `INSUFFICIENT_DATA` — SAD could not be computed (`no NPL`, `no Well
  Depth`, well attributes missing).
- `SUSPECT_DATA` — SAD was computed but is non-positive (e.g. GWELLS
  reports static water level deeper than the well bottom — physically
  impossible, see WTN 96473). The pumping impact is fine; the
  *baseline* well record needs review against the driller's log.
  Excluded from the at-risk summary table because it is a data-quality
  channel, not an at-risk channel.
- `OUTSIDE_VALIDITY` — Cooper-Jacob `u >= 0.01` at this distance/duration.
  **Advisory only** per client direction: `analysis.effective_u_threshold`
  returns `inf` so no well's `well_status` is `OUTSIDE_VALIDITY`. The
  status is whatever the SAD-vs-impact rules produce (`AT_RISK`, `OK`,
  `INSUFFICIENT_DATA`, `SUSPECT_DATA`); a well that fails the validity
  check (`u_max >= COOPER_JACOB_U_THRESHOLD`) is instead flagged
  visually in the per-well table with a light-purple row tint. Reverting
  to a hard-fail status is a one-line change in `effective_u_threshold`.

Status precedence when more than one rule could apply:
``INSUFFICIENT_DATA`` > ``SUSPECT_DATA`` > ``AT_RISK`` > ``OK``.
(`OUTSIDE_VALIDITY` is wired through the enum and the math kernel for
future re-enablement, but is not emitted by the pipeline today.)

The 30% threshold matches the legacy Excel (`Impact!V` formula and the
summary table at `InputValues!B30`). Make the threshold a config key
(`AT_RISK_DRAWDOWN_FRACTION`, default `0.30`) so changing it later is
one line, not a refactor. Client-confirmed (Q3): the threshold is 30%.

**`data_access/db.py`** — `oracledb` thin-mode connection pool. The pool is
initialised lazily by the login handler (`init_pool(user, password)`) once
the user has entered valid BCGW credentials, and closed on logout or app
shutdown. Pool size small (e.g. 2-4) — single-user app, but pooling is the
right abstraction even for one user, and it's what we'd want at deployment
time. `get_connection()` raises a clear error if the pool isn't initialised
yet, which forces all data-access callers to be reachable only after login.

**`data_access/queries.py`** — parameterised SQL templates for the three BCGW
datasets. See `DATA_REFERENCE.md` for column names and join keys. Queries:

1. Find nearby wells within a buffer radius of a point (BC Albers).
2. Find the aquifer polygon containing a point, return AQUIFER_ID.
3. Look up AQUIFER_SUBTYPE_CODE for an AQUIFER_ID via GW_AQUIFER_ATTRS.
4. Look up well details by WELL_TAG_NUMBER (for the search-by-tag input mode).

All queries use bind variables, never string interpolation. All spatial
parameters are in BC Albers SRID 3005.

**`ui/app.py`** — Dash app entry point. Multi-page (`use_pages=True`).
Sets up server-side session handling (Flask-Session, filesystem backend),
mounts pages, wires login/logout routes. Does **not** initialise the BCGW
pool at startup — the pool is created on successful login. Thin: should be
under 150 lines, with most behaviour in pages and components.

**`ui/pages/login_page.py`** — first page the user sees. A small form with:
BCGW username, password, a read-only display of the connection target
(`bcgw.bcgov:1521/idwprod1.bcgov`), and a "Sign in" button. On submit:
attempt `oracledb.connect()` with the given credentials and run
`SELECT 1 FROM DUAL` to verify. On success: store credentials in the
server-side session, initialise the connection pool, redirect to the setup
page. On failure: show the error inline, let the user retry. Password is
never written to disk; it lives only in server-side session memory and is
cleared on logout or session expiry.

All other pages are protected — if the session has no authenticated user,
the page redirects to login.

**`ui/pages/setup_page.py`** — input page. Three input methods for locating
the proposed pumping well (click on map / enter lat-lon / search by tag
number), parameter inputs (Q with unit dropdown, duration, buffer radius,
T/S override), and the "Run Analysis" trigger. The pumping-rate input
uses the current tool's supported units: L/min, L/s, m³/d, m³/min,
m³/s, m³/yr, with a default of m³/d. Pumping duration defaults to 90 days
(client-confirmed for all of BC; the legacy Excel used 100 days for the
east-coast Vancouver Island dry-season convention, see deck slide 5),
with quick-pick presets for 30 days, 90 days, 180 days, 1 year, and 10
years.

**Single-aquifer filtering (spatial, default OFF).** Once the pumping
point is placed, the tool queries the aquifer polygon containing it.
A toggle lets the user filter the nearby-wells list to only wells
whose geometry falls **inside the source aquifer polygon** — a
spatial test (`SDO_ANYINTERACT` against the source polygon), not a
GWELLS `AQUIFER_ID` attribute match. This safeguards against
erroneous GWELLS aquifer assignments and against future
re-delineation of aquifer boundaries: a well's recorded
`AQUIFER_ID` may be stale, but where it sits on the map is not.
Default is OFF (return every well within the buffer) so the
officer sees the full set first and chooses to narrow when
appropriate. Client-confirmed (Q12): default-off, and the
filter is spatial. In manual-entry mode (see Phase 4d) the filter has
no polygon to test against and is forced off in both the UI
and the pipeline.

**Aquifer selection fallback (Phase 4d).** ``aquifers_at_point``
and ``aquifers_near_point`` both run on every point placement.
Direct hits are listed first (tagged "directly overlapping"; a
single hit is auto-selected); aquifers within a 1000 m search
radius (top 3 by ascending distance) are listed below tagged
with distance, so a nearby aquifer can be picked even when the
well directly overlaps a different one (the common stacked-
polygon case — a well in unconsolidated material can sit inside
the underlying bedrock polygon but outside the unconsolidated
polygon it should be associated with). When no polygon contains
the point, a "No mapped aquifer at this location — enter
materials manually" sentinel option is pinned at the bottom.
Selecting the manual sentinel reveals a material dropdown
(``MANUAL_AQUIFER_MATERIALS`` in ``analysis.py``: Unconsolidated
or Bedrock) and makes T/S entry mandatory; the spatial-filter
toggle is disabled, ``AnalysisInputs.source_aquifer_id`` is
``None``, ``manual_material`` carries the chosen category, and
the results page shows an orange manual-entry banner above the
run summary. ``AnalysisInputs.is_manual_mode`` is the canonical
check downstream. Client-driven addition; see the Phase 4d
entry under §6 for the rationale.

**`ui/pages/results_page.py`** — results dashboard. Layout, in priority
order:

1. **At-risk wells summary table** at the top. Columns: WTN, Reassigned
   Aquifer Material, SAD (m), Impact (m), Impact as % of SAD. Filtered
   to wells where Impact / SAD ≥ 30%. This is the artifact attached to
   the licence assessment file. Matches `InputValues!B30:E32` in the
   legacy Excel.
2. **Stat cards**: total wells found, count flagged at-risk, count with
   insufficient data, count outside Cooper-Jacob validity, max predicted
   drawdown.
3. **Distance-drawdown chart** matching the legacy Excel chart (deck slide
   21). See `references/excel_chart_layout.md` for the full spec. Three
   series: well points (red dots, labelled with WTN), Cooper-Jacob curve
   (smooth black line), SAD bars (vertical orange bars from each well
   point down to its SAD value). Y-axis inverted (drawdown grows downward
   — standard hydrogeology convention). X-axis shows distance in m.
4. **Map** colour-coded by drawdown severity, marker size by impact
   magnitude. Wells in different aquifers (when filter is off) shown in
   a distinct symbol.
5. **Per-well details table** showing all observation wells with the full
   set of attributes from the Excel `Impact` sheet: WTN, Intended Use,
   Aquifer ID, Finished Depth, Total Depth, Bedrock Depth, Yield, NPL,
   Stickup, Aquifer Material (GWELLS), Reassigned Aquifer Material,
   Distance, Drawdown Impact, Top of Fracture/Screen (overridable), SAD,
   Impact %, Status flag.

Map and chart are cross-linked (click one, highlights on the other).
Export buttons for CSV (full results table), KML (well points with
results as attributes, for Google Earth), PDF (summary + charts +
tables), and a standalone interactive HTML map. KML was chosen over
GeoJSON at client request — Water Officers are more familiar with
Google Earth.

## 5. Stage 2 considerations baked into Stage 1

These choices cost nothing now and pay off at deployment.

| Decision | Stage 1 reality | Stage 2 implication |
|----------|----------------|---------------------|
| Non-secret config in `config.py`, optional overrides via `.env` | Tool runs with no `.env` for typical use | Server may inject overrides via env; no code change |
| BCGW credentials entered through login UI, never stored | User logs in once per session | Replace login page with platform SSO; session abstraction unchanged |
| `oracledb` connection pool, lazily created on login | Pool of 2-4 for single user | Same pool per session, just more sessions |
| Server-side session via Flask-Session | Filesystem backend, single user | Swap to Redis or similar; same Flask-Session API |
| No module-level mutable state | Single user, would still work | Multi-user safe by construction |
| State in `dcc.Store` only, not Python globals | Habit | Required for multi-user |
| `logging` module from day 1, not `print` | Logs to file, configurable | Server captures stdout |
| Exports written to env-configurable output dir, served via `dcc.Download` | Dir is `./outputs/` | Dir is whatever the server provides |
| Package as `src/gwdrawdown/` | Importable as a real package | Container `pip install .` works |
| `pyproject.toml` + `uv.lock` | Reproducible local install | Same lockfile drives container build |
| Dependencies pinned exactly | `uv lock` produces this | Reproducible deploys |

What we are explicitly **not** doing in Stage 1:

- Not writing a Dockerfile.
- Not implementing single-sign-on (SSO/SAML/OIDC). The Stage 1 login is a
  thin form that authenticates directly to BCGW via `oracledb`. Stage 2 may
  replace it with platform SSO; the session abstraction is the same either
  way.
- Not writing deployment scripts.
- Not optimising for >1 concurrent user.

But every Stage 1 choice should leave Stage 2 a packaging problem, not a redesign.

## 6. Build order

Each phase ends in something runnable / testable. Don't skip ahead.

### Phase 1 — Skeleton and tooling

- `pyproject.toml` with project metadata and dependency declarations.
- `.python-version` pinned to `3.13`.
- `setup.bat` and `run.bat`.
- `.gitignore` covering `.env`, `.venv`, `__pycache__`, `dist`, `outputs/`,
  `logs/`, `flask_session/`.
- Empty package skeleton at `src/gwdrawdown/` with `__init__.py` files in each
  subdir, plus a stub `app.py` that runs an empty Dash app on `localhost:8050`.
- `config.py` containing the hardcoded `BCGW_DSN` constant and reasonable
  defaults for the optional override keys (logging level, output directory,
  threshold defaults, etc.). Reads `.env` if present, but does not require it.
- An optional `.env.example` is **not** shipped — the tool runs without one.
  If a power user needs to override a default, they create their own `.env`;
  documented in `README.md`.
- `README.md` (developer instructions) and `CLIENT_INSTALL.md` (end-user steps).
- `version.txt` at the repo root, single line containing the current version
  (initial value: `0.1.0`). Bumped on every release. Read at app startup, logged,
  shown in the UI footer, and embedded in PDF exports. Also serves as the file
  the future auto-updater (Phase 6) compares against the published version on
  the share.
- `CHANGELOG.md` with a `[Unreleased]` section. Append-only; each release moves
  unreleased items into a versioned section. Keep entries plain English — the
  changelog is shown to non-technical end users by the auto-updater.
- Initial `uv lock` run; commit the lockfile.

**Acceptance:** `setup.bat` on a clean Windows machine without Python installed
results in a running empty Dash app at `localhost:8050`. The app logs its
version on startup. No `.env` file required to launch.

### Phase 2 — Core math, no UI

- `core/units.py` with conversions (BCGW field conversions, plus the
  pumping-rate unit table loaded from `data/unit_conversions.csv`).
  Pytest unit tests for every conversion direction.
- `core/crs_utils.py` with WGS84↔BC Albers and tests.
- `core/drawdown.py` with Cooper-Jacob, the `r → 0.1 m` fallback, the
  `u < 0.01` validity check, and a superposition-ready signature
  (accepts list of pumping sources, sums linearly). Tests against
  analytical reference cases and against the legacy Excel example
  (`Q = 3.97 L/s`, `T = 250 m²/d`, `S = 0.005`, `t = 180 d` → `r = 100 m`
  yields a known drawdown value).
- `core/aquifer_lookup.py` reading `data/ts_lookup.csv`, with tests.
- `core/well_classification.py` implementing the reassigned-aquifer-material
  rule from `Impact!R` (bedrock-depth heuristic), with tests.
- `core/sad.py` implementing Safe Available Drawdown computation matching
  `Impact!U`, with the three "no NPL" / "no Well Depth" / numeric outcome
  branches, with tests.
- Tests run with `uv run pytest`.

**Acceptance:** `uv run pytest` passes. No Dash code touched yet. Drawdown
output for the legacy Excel example matches the spreadsheet to within
floating-point tolerance.

### Phase 3 — Data access

- `config.py` finalised: hardcoded `BCGW_DSN`, defaults for optional keys,
  `.env` override loading.
- `data_access/db.py` with `oracledb` thin pool. Pool is initialised by
  `init_pool(user, password)` (called by the login handler in Phase 4),
  not at app startup. Exposes `get_connection()` (raises if pool not
  initialised) and `close_pool()` (called on logout / shutdown).
- `data_access/queries.py` with parameterised SQL for the four queries above.
- A small CLI script (`scripts/smoke_test_db.py`) that prompts for username
  and password (via `getpass`), opens the pool, runs each query against a
  known test point in BC, prints results, closes the pool. The script never
  reads credentials from `.env` — same posture as the eventual UI.

**Acceptance:** smoke test script returns sensible results when run with
valid BCGW credentials entered at the prompt. Don't proceed past this until
the SQL is verified.

### Phase 4 — UI

Subdivided into five browser-verifiable sub-stages, each committed
separately so the work stayed bisectable:

- **4a — Auth shell** *(committed `239b05f`)*. Multi-page Dash app
  (`use_pages=True`), Flask-Session with filesystem backend at
  `config.SESSION_DIR`, `/login` page that runs `SELECT 1 FROM DUAL`
  before calling `data_access.init_pool`, Flask `/logout` route that
  closes the pool and clears the session, root redirect, footer
  component, session-required guard. Setup and results pages are
  stubs at this point. `is_authenticated()` also verifies the pool is
  open so a session that survives an app restart but loses the pool
  is treated as stale (cleared, redirected to login).
  `SESSION_USE_SIGNER=True` so cookies issued before a `SECRET_KEY`
  rotation are rejected.
- **4b — Setup page + analysis pipeline + flagging** *(committed
  `b831ba7`)*. Real setup page replaces the 4a stub: three input
  modes (map click via `dash-leaflet`, lat/lon, WTN with auto-aquifer
  resolution), source-aquifer picker for stacked polygons, T/S
  override checkbox with full-precision float display, Q + unit
  dropdown driven by `data/unit_conversions.csv`, duration presets
  (30 d / 100 d / 1 yr / 10 yr), buffer radius (default 1000 m),
  same-aquifer filter (default on per Q12). Run Analysis opens
  `/results` in a new browser tab via clientside callback —
  sessionStorage inheritance gives each tab its own snapshot so
  earlier results tabs aren't disturbed by re-runs. `core/flagging.py`
  and `analysis.py` (orchestration: queries → SI conversion →
  Cooper-Jacob → SAD → classification → flagging) ship in this
  sub-stage. `_compute_well_result` is a pure function unit-tested
  without a database. Cooper-Jacob `u<0.01` validity check is
  bypassed at the pipeline level pending client confirmation; the
  math still runs in `core.drawdown.cooper_jacob` and `u_max` is
  preserved on every `WellResult`. Revert is a one-line change in
  `analysis.run_analysis`.
- **4c.1 — Read-only results dashboard** *(committed `64fa593`)*.
  Replaces the 4b text dump with a structured page: run-summary
  block (timestamp, BCGW user, source aquifer, T/S used with
  "(override)" tag, Q in m³/day, duration, buffer, filter), seven
  colour-coded stat cards, at-risk summary table (5 columns,
  matches `InputValues!B30:E32`, sorted desc by Impact %, AT_RISK
  only — SUSPECT_DATA wells excluded), full per-well details table
  (17 columns, sortable / filterable / paginated 10/page, sticky
  header, status cell colour-coded). Both tables are own-scroll-
  container so the horizontal scrollbar stays in view. Custom
  Export CSV buttons (built-in `dash_table` export avoided due to
  a layout bug with `fixed_columns`); CSV reflects the current
  sort + filter state via `derived_virtual_data`. Auto-loaded
  `assets/styles.css` standardises the filter-row placeholder
  visibility on hover.
- **4c.2 — Editable per-well overrides + live recompute**
  *(committed)*. Per-well table now has four editable columns —
  NPL, finished depth, stickup (BCGW doesn't expose this; the
  table is the only way to populate it), and top of fracture /
  aquifer / screen (the existing override field on `core.sad`,
  finally exposed in the UI). Edits route through `analysis.
  recompute_well` (pure math; same kernel `_compute_well_result`
  uses), per-WTN overrides land in a sessionStorage `dcc.Store`,
  and `analysis.apply_overrides` rebuilds the totals from the
  cached pipeline output without a fresh BCGW query. Two new
  app-level Stores back this: `analysis-result` caches the
  pipeline JSON so tab refreshes and override edits don't replay
  queries (cleared whenever `analysis-inputs` changes), and
  `well-overrides` carries the per-WTN map of edited cells. Rows
  with active overrides are tinted light yellow; overridden
  values carry a trailing `*`. Hidden `<col>_base` shadow cells
  in the table data let the override-capture callback diff
  edits against the BCGW value without consulting the store.
  This is the manual-review path the legacy Excel only supports
  as a copy-paste workflow. New `analysis.effective_u_threshold`
  centralises the Cooper-Jacob bypass so it flips in one place
  for both the initial pipeline and the override recompute.
- **4c.3 — Distance-drawdown chart + colour-coded map +
  spatial filter + advisory validity flag**. Implements
  `references/excel_chart_layout.md` (deck slide 21): scatter
  chart with three series (red dots for wells with WTN labels,
  smooth black Cooper-Jacob curve, vertical orange SAD bars),
  inverted Y axis. Colour-coded `dash-leaflet` map with marker
  size proportional to drawdown impact; cross-linked to the
  chart via a `selected-well` Store. The nearby-wells SQL is
  reworked to filter spatially (`SDO_ANYINTERACT` against the
  source aquifer polygon) instead of by GWELLS `AQUIFER_ID`,
  with the filter default flipped OFF per the confirmed Q12
  answer. The Cooper-Jacob `u<0.01` check is downgraded to a
  per-row visual advisory (light-purple tint on the per-well
  table); the `well_status` continues to reflect the SAD-based
  classification. A small legend below the per-well table
  explains the row tints (yellow = override, purple = outside
  validity advisory) and reminds users the table paginates
  after 10 rows. After 4c.3, the full Phase 4 acceptance is
  met.

**Acceptance (full Phase 4) — met at v0.4.0 (2026-05-14):** user
launches the app, sees login page, enters BCGW credentials, lands
on setup page, runs an analysis through to results, clicks logout,
sees login page again. Wrong credentials show an inline error and
don't redirect. The username appears in the UI footer (and in log
entries) for the active session. The at-risk summary table and the
distance-drawdown chart are visually equivalent to the legacy Excel
output (deck slide 21). An Impact-% bar chart and a colour-coded
map sit beside the distance-drawdown chart and stay in sync via a
shared `selected-well` Store. CSV export ships for both tables.

### Phase 4d — Aquifer selection fallback + manual entry

Client-driven addition landed after v0.4.0. The original setup
page blocked the workflow when no aquifer polygon contained the
click point, which surfaced two real-world cases the BC team
flagged: (a) wells that fall just outside the boundary they
should be associated with (common at re-delineated aquifer
boundaries — the polygon is stale, not the well), and (b)
remote areas the Province hasn't mapped at all where the
officer still needs to run a screening estimate. Presenting the
choices side by side keeps the officer in control of the call.

A follow-up client note refined case (a): a well can sit inside
one aquifer (e.g. the bedrock polygon) yet just outside the
*other* polygon it should be associated with (the unconsolidated
aquifer). So the nearby search runs on every point placement —
not only when there's no direct hit — and nearby aquifers are
offered alongside the direct hit rather than as a last resort.

What ships:

- `data_access/queries.py` gains `aquifers_near_point(x, y,
  radius_m)` using `SDO_WITHIN_DISTANCE` +
  `SDO_GEOM.SDO_DISTANCE`, sorted ascending by distance.
  `aquifers_at_point` is unchanged.
- Setup page picker behaviour: both queries run on every point
  placement. Direct hits are listed first, tagged "directly
  overlapping" (a single hit is auto-selected; stacked polygons
  leave the pick to the officer). Up to `MAX_NEARBY_AQUIFERS`
  (3) polygons within `NEARBY_AQUIFER_RADIUS_M` (1000 m) are
  listed below, tagged with distance and "(nearby — not
  directly overlapping)" — so a nearby aquifer can be picked
  even when the well directly overlaps a different one. The
  nearby query returns the containing polygons too (distance
  0); those are de-duplicated out. The "No mapped aquifer at
  this location — enter materials manually" sentinel is pinned
  at the bottom only when there are no direct hits. When no
  aquifers are found within 1000 m and none contain the point,
  only the manual sentinel is offered with a note explaining
  nothing was found nearby.
- Manual-mode UI: an orange-tinted panel reveals a material
  dropdown (`MANUAL_AQUIFER_MATERIALS = ("Unconsolidated (sand
  and gravel)", "Bedrock")`) and forces T/S inputs editable.
  The default-T/S badge and override toggle hide; the
  same-aquifer filter toggle disables with a "(not applicable
  in manual entry)" label so the gesture isn't misleading.
- `AnalysisInputs` gains `source_aquifer_id: int | None` (None
  in manual mode), `manual_material: str | None`, and the
  `is_manual_mode` property as the canonical downstream check.
  `from_json` defaults `manual_material` to None so older
  sessionStorage payloads still load cleanly.
- `run_analysis` forces the spatial same-aquifer filter off in
  manual mode regardless of the UI toggle state.
- Results page shows an orange manual-entry banner above the
  run summary when `inputs.is_manual_mode`; the source-aquifer
  row reads "Manual entry (Bedrock) (no mapped aquifer)" and
  the filter row reads "n/a (manual entry)".
- Setup-page form hydration restores the manual sentinel and
  `manual_material` on /setup re-mount; T/S values are not
  restored (same posture as the existing override path —
  re-typed if the officer wants to tweak).
- Tests: five new cases in `tests/test_analysis_overrides.py`
  cover `is_manual_mode`, the new JSON round-trip, backward
  compatibility with payloads predating `manual_material`, and
  that the per-well override pipeline still works on a
  manual-mode result.

**Acceptance:** clicking a point inside an aquifer shows that
aquifer (auto-selected) plus any aquifers within 1000 m as
selectable nearby options. Clicking outside any aquifer but
within 1000 m of one shows the top 3 nearest as labelled
fallback options plus the manual sentinel. Picking the manual
option reveals the material dropdown and requires T and S;
running the analysis lands on /results with the orange
manual-entry banner. Per-well overrides recompute live in both
modes.

### Phase 5 — Visual identity, map polish, exports, disclaimers

Phase 5 expands the original "Exports and polish" scope to absorb
two things that v0.4.0 deferred: a coherent visual identity (the
v0.4.0 UI ships with per-component inline styles and no real
theming), and richer maps (the setup-page map ships with a single
OSM basemap and no aquifer overlay, the results map likewise). KML,
PDF, and standalone-HTML-map exports round out the export set (only
CSV shipped at v0.4.0), and a logging + disclaimer pass closes out
the "professional polish" theme.

Sub-staged like Phase 4 so each step is browser-verifiable and
bisectable:

- **5a — Visual identity / theme** *(shipped)*. Pull the per-component inline
  style dicts out of Python and into a single CSS theme: design
  tokens for colour, typography, spacing, and radius; a wordmark
  / header chrome consistent with the BC government visual
  language (target reference: gov.bc.ca and BC Data Catalogue);
  consistent button/card/section/form styling; real footer
  treatment with version + signed-in user + Logout. The status
  palette in `ui/components/palette.py` already centralises one
  axis; this stage centralises the rest. The largest sub-stage —
  design-token migrations always are. The visual direction was
  agreed with the client before the theme work proceeded.
- **5b — Map improvements** *(shipped)*. Reworked the setup and
  results maps into a shared, layered map experience. Both maps
  draw their basemaps and overlays from one new module,
  `ui/components/basemaps.py`.
  - **5b.1 — Basemap switcher.** A `dl.LayersControl` widget
    (top-right) offers three basemaps: OpenStreetMap (default),
    ESRI World Topographic, and ESRI World Imagery (satellite).
    All free, no API key.
  - **5b.2 — WMS context overlays.** Two BCGW layers via WMS
    (`openmaps.gov.bc.ca`): **Aquifers** (translucent fill,
    default ON on the setup map) and **All BC Wells** (setup map
    only — redundant on the results map, which already plots the
    queried wells as colour-coded markers). Both are zoom-gated:
    aquifers from zoom 9 (matching BC's `MaxScaleDenominator`, so
    the client doesn't request guaranteed-blank tiles), wells
    from zoom 13 (~150k points — a blob below that). OGL-BC
    attribution wired in.
  - **5b.2b — Water-management boundaries as GeoJSON.** The Water
    Management District and Precinct layers — added at client
    request — ship as committed, pre-simplified GeoJSON in
    `assets/` rather than as WMS. They are small and static
    (regulation-derived), so a snapshot buys full styling control
    (self-styled slate outlines), no per-tile round-trips, and
    browser-side geometry for the dynamic labels. The raw WFS
    geometry is ~24 MB / 900k vertices; a Douglas-Peucker pass
    (`scripts/fetch_water_mgmt_boundaries.py`, using `shapely` as
    a dev-only dependency) cuts that to ~1.7 MB at a tolerance
    invisible at the zoom levels these layers display. Re-run the
    script if BC re-delineates.
  - **5b.2c — Viewport-anchored boundary labels.** BC publishes
    no labelled WMS style for these boundaries, so
    `ui/components/map_labels.py` generates them. A callback clips
    each polygon to the current map viewport (Sutherland-Hodgman)
    and anchors a name label at the area-weighted centroid of the
    *visible* piece — so a label stays on screen as the officer
    pans within one district, instead of being pinned to a fixed
    centroid that scrolls away. Labels appear only while the
    overlay is toggled on (the callback reads the
    `LayersControl.overlays` prop) and a minimum-visible-area
    threshold keeps the zoomed-out view uncluttered. The
    clip/centroid geometry is pure and unit-tested
    (`tests/test_map_labels.py`).
  - **WMS legend.** A compact panel pinned bottom-right shows the
    `GetLegendGraphic` swatch for each WMS overlay (aquifers,
    wells) while it is toggled on; the self-styled GeoJSON
    overlays need none.
  - **Map-click affordances.** The setup map shows a crosshair
    cursor in "Map click" input mode (grab hand in the lat/lon
    and WTN modes), and lat/lon entry and WTN lookup now fly the
    map to the resolved point.
- **5c — Exports** *(shipped)*. CSV was already in (custom buttons
  on both tables). Added KML, PDF, and standalone-HTML-map exports
  of the full run, as three whole-run buttons in an export bar on
  the results page (`ui/components/export_bar.py`); all reflect
  any active per-well overrides.
  - **KML, not GeoJSON.** Changed at client request — Water
    Officers are more familiar with Google Earth than with
    GeoJSON tooling. `ui/components/export_kml.py` builds a KML
    document: one Placemark for the pumping well plus one per
    observation well, colour-coded by `WellStatus` and sized by
    predicted impact (an inline `<IconStyle><scale>`, echoing the
    results-map proportional sizing), with the full per-well
    result row carried as `<ExtendedData>`. Pure and unit-tested
    (`tests/test_export_kml.py`); well points are converted from
    BC Albers back to WGS84 (`core.crs_utils.to_wgs84`).
  - **PDF** (`ui/components/export_pdf.py`, `reportlab` —
    already a dep). Landscape Letter, with a fixed one-section-
    per-page layout via explicit `PageBreak`s: page 1 — input
    parameters, a summary-card row (mirroring the results-page
    stat cards), and the method-and-assumptions disclaimer; the
    distance-drawdown and impact-% chart images, one per page
    (the impact chart can be tall); the at-risk summary table;
    then a fresh page for the full per-well details table. The per-well table carries
    the override "Edited" column and the light-purple
    outside-validity row tint (the validity check is advisory,
    not enforced — called out in the disclaimer). A
    screening-tool banner sits on every page; a per-page footer
    carries run timestamp, run ID (`AnalysisResult.run_id`, a
    UUID minted per run), tool version, and signed-in user.
    (BCGW snapshot date is not obtainable from the live query
    and is omitted.)
  - **Chart images.** Plotly figures are captured in the browser
    via a clientside `Plotly.toImage` callback and handed to
    `build_pdf` as PNG bytes — chosen over a server-side
    `kaleido` render to keep a ~100 MB headless-Chromium
    dependency out of the install and to guarantee the PDF charts
    match what the officer saw on screen. A capture failure
    degrades to a "chart unavailable" note rather than erroring.
  - **Interactive HTML map** (`ui/components/export_html_map.py`).
    A self-contained HTML file — Leaflet from a CDN, OSM +
    satellite basemaps, the pumping well, buffer, and per-well
    markers with click popups. A *static image* snapshot of the
    live results map was considered for the PDF but not done:
    capturing a Leaflet map with cross-origin basemap tiles
    taints the browser canvas, so a reliable image export isn't
    feasible. The standalone HTML is both reliable to generate
    (pure string templating) and more useful — it stays
    interactive.
  - **CSV.** The per-well CSV gains a derived "Outside Validity"
    Yes/No column so the validity advisory (a purple row tint
    on screen, which CSV can't carry) survives the export.
- **5d — Logging + caveat text + disclaimer.** Rotating daily log to
  `./logs/gwdrawdown.log` (replaces the current `basicConfig`
  setup in `app._configure_logging`). Final caveat / disclaimer
  pass on /results, the PDF, and the login page (BCGW
  credentials handling reassurance). Acceptance is light: logs
  rotate, disclaimers are in place, no behavioural changes.

**Acceptance (full Phase 5):** UI reads as a coherent, professionally
branded tool rather than the Dash-default appearance. Setup-page map
offers basemap and aquifer overlay choices. All exports (CSV, KML,
PDF, interactive HTML map) produce correctly-formatted files; PDF
mirrors the legacy Excel artifact. Logs rotate daily; disclaimers are
visible on every officer-facing surface.

### Phase 6 — Documentation and distribution polish

The distribution mechanism itself — GitHub Releases, the
`publish_release.ps1` workflow, and the dual-mode `setup.bat`
installer/updater — shipped early, pulled forward into Phase 5a.
Sections 6.1–6.5 and 6.8 below document that shipped mechanism for
reference; they are **not** outstanding work. (It was originally scoped
as "auto-update from a BC government network share", then pivoted to
GitHub Releases — public repo `bcgov/groundwater-drawdown-tool`, zero
IT-provisioning, stable forever-URLs via
`releases/latest/download/<asset>`.)

Phase 6 proper is four browser/release-verifiable sub-stages:

- **6a — Documentation cleanup.** Resolve the remaining `CLIENT_TBD`
  markers and bring the doc set in line with the shipped tool.
- **6b — GitHub Pages documentation site.** A published `/docs` site
  split into a User Guide and a Developer Guide.
- **6c — Auto-update on launch.** `run.bat` silently updates from the
  latest GitHub release before starting the app.
- **6d — Version footer + CHANGELOG modal.** The footer shows the
  running version and opens a changelog.

#### Phase 6a — Documentation cleanup *(shipped)*

The project docs were written at kickoff and have drifted from the
shipped tool. This sub-stage closes that gap.

- **Resolve `CLIENT_TBD` markers** *(done)*. All marker questions are
  resolved across the `.md` files and the `.py` files: Q1, Q3, Q4, Q8,
  Q10, Q11, Q12, Q13, Q14 are client-confirmed; Q2 (single T/S value
  vs range) and Q5 (superposition) are reworded as deliberate
  future-version notes. No `CLIENT_TBD` markers remain in the codebase.
- **Sync stale content.** Re-read every `.md` file against the current
  tool and correct anything that drifted since kickoff.
- **Developer-only docs.** `PROJECT_PLAN.md`, `DATA_REFERENCE.md`, and
  `DESIGN_NOTES.md` are developer-facing and are dropped from the
  release zip — see the updated §6.1 inventory.

#### Phase 6b — GitHub Pages documentation site *(shipped)*

- A new `/docs` folder published via **GitHub Pages** (Jekyll, a
  zero-build theme such as `just-the-docs`). The `/docs` sources stay
  in the repo but are excluded from the release zip.
- Split by audience: a **User Guide** (install, locating the pumping
  well, running an analysis, reading results, exports, troubleshooting)
  and a **Developer Guide** (architecture, layer rules, running tests,
  publishing a release). The Developer Guide re-homes existing
  `README` / `DESIGN_NOTES` / `DATA_REFERENCE` content; the User Guide
  is the main new writing.
- Pages enabled in repo settings; the site is linked from `README.md`
  and from the app footer.

#### Release strategy

Every release is published as a regular GitHub release marked
`--latest` — there are **no GitHub pre-releases**. (An early plan to
cut internal-testing builds as pre-releases was dropped: GitHub's
`releases/latest` endpoint excludes pre-releases, which would have
left the canonical `releases/latest/download/setup.bat` URL pointing
at a stale build and broken the auto-updater for testers.)

`v0.5.0` was a pipeline-validation cut — it exercised the publish and
install path end to end but was never handed to testers. **`v0.5.1`
is the first build delivered to the GIS team** for internal testing;
fixes from that cycle ship forward as further `v0.5.x` releases. Once
the team is comfortable, the same channel carries the build on to
end-user (Water Officer) testing — the distinction is the version
number and how it is communicated, not the release's GitHub status.

Because every release is `--latest`, the stable URLs always resolve
and the `setup.bat --silent-update` auto-updater (§6c) carries every
install forward to the newest release with no manual re-download.

#### 6.1 The release layout

Each tagged release on GitHub carries two assets:

- **`setup.bat`** — the one file end users download. Self-contained:
  detects bootstrap vs local mode and either fetches the release zip or
  installs Python dependencies. The same file is also the in-place updater
  on subsequent runs.
- **`groundwater-drawdown-tool.zip`** — the tool payload. Contains
  `src/`, `data/`, `pyproject.toml`, `uv.lock`, `.python-version`,
  `setup.bat`, `run.bat`, `_wait_and_open.ps1` (the launch helper
  that polls the local port before opening the browser, see §6c),
  `version.txt`, `CHANGELOG.md`, and the end-user docs
  (`README.md`, `CLIENT_INSTALL.md`, `references/excel_chart_layout.md`).
  Explicitly excluded: the developer-only docs (`PROJECT_PLAN.md`,
  `DATA_REFERENCE.md`, `DESIGN_NOTES.md`), the `/docs` Pages sources,
  `.venv/`, `outputs/`, `logs/`, `flask_session/`, `.env`, `.git/`,
  `__pycache__/`, `*.pyc`, `tests/`, `scripts/`, client-confidential
  reference materials.

Both assets are exposed at stable URLs that always resolve to the latest
release:

```
https://github.com/bcgov/groundwater-drawdown-tool/releases/latest/download/setup.bat
https://github.com/bcgov/groundwater-drawdown-tool/releases/latest/download/groundwater-drawdown-tool.zip
```

The release tag follows `v<version>` (e.g. `v0.5.0`); release notes are the
matching section from `CHANGELOG.md`.

#### 6.2 The publish workflow (developer side)

`scripts/publish_release.ps1` runs from a developer workstation with `gh` CLI
installed (`winget install GitHub.cli`, then `gh auth login` once):

1. Reads `version.txt` from the local repo.
2. Confirms the local repo is clean (no uncommitted changes) and on the main
   branch — abort if not.
3. Confirms the `v<version>` tag does not already exist locally or on origin
   — abort if it does. Forces a `version.txt` bump for each release.
4. Runs `uv run pytest` — abort if any test fails. `-SkipTests` flag exists
   for emergency use; discouraged.
5. Stages the release files into a temp directory, stripping `__pycache__/`
   and `*.pyc`. Compresses to `groundwater-drawdown-tool.zip`.
6. Tags the git commit with `v<version>` and pushes the tag to origin.
7. Extracts the matching CHANGELOG section (falls back to `[Unreleased]`
   with a warning if the publisher forgot to cut the version header).
8. `gh release create v<version> --title "v<version>" --notes-file <…>
   --latest groundwater-drawdown-tool.zip setup.bat`. The explicit
   `--latest` is load-bearing: without it, `gh release create` flagged
   the first release in the repo as a pre-release, which made
   `releases/latest/download/setup.bat` return 404 and broke the
   auto-updater. Fixed after v0.5.0 publish — see commit c22399e.

A `-Draft` flag creates the release in draft state for reviewing it
before it goes live. There is no pre-release option — every published
release is marked `--latest` (see the Release strategy note above).

No CI/CD in Stage 1 — manual is fine for one developer and one client team.
The publish script is the only contract.

#### 6.3 The end-user install / update workflow (`setup.bat`)

`setup.bat` auto-detects two modes based on whether `pyproject.toml` and
`src/gwdrawdown/__init__.py` exist next to it:

**Bootstrap mode** (no `pyproject.toml` next to setup.bat — i.e., a
standalone copy in `Downloads\` or on the Desktop):

1. Calls the GitHub Releases API (`api.github.com/repos/<repo>/releases/latest`)
   to read the latest tag. Aborts with a clear error if GitHub is
   unreachable.
2. Checks for an existing install at `%USERPROFILE%\Tools\groundwater-drawdown-tool\`.
   - **No existing install** → fresh install: `mkdir`, download
     `groundwater-drawdown-tool.zip`, `Expand-Archive` to the install dir.
   - **Existing install, same version** → prints "already up to date",
     exits.
   - **Existing install, older version** → in-place update: download zip,
     `Expand-Archive -Force` over the install dir. Because the zip
     contains only tool files, `Expand-Archive -Force` overwrites tool
     files but leaves `.env`, `outputs/`, `logs/`, `flask_session/`, and
     `.venv/` untouched (they aren't in the zip).
3. Chains into the install dir's own `setup.bat` (which then runs in local
   mode) to install or refresh Python dependencies.

**Local mode** (`pyproject.toml` present — running from inside the install
folder, or from a developer clone):

1. Installs `uv` if missing (via the upstream `astral.sh` installer).
2. Runs `uv sync` to install or refresh Python dependencies from
   `uv.lock`. No GitHub calls in this mode.

The dual-mode design means there is exactly one entry point for both first
install and future updates, and exactly one entry point for developer-clone
setup — the same file.

#### 6.4 What gets preserved across updates

These paths are never present in the release zip and therefore never touched
by `Expand-Archive -Force`:

- `.env` — if it exists. Most users won't have one (the tool runs without
  it); a power user's override file is preserved.
- `flask_session/` — server-side session store. Preserved so users don't
  re-login on every release.
- `outputs/` — exports the user has generated.
- `logs/` — historical logs.
- `.venv/` — `uv sync` manages this; never touched by the file extraction.

`Expand-Archive -Force` overwrites existing tool files and creates new ones,
but does **not** delete files in the target that aren't in the zip. The
side-effect is that files removed in a new release will linger as orphans
in the install dir — acceptable for v1 (tool files are stable and the
inventory rarely shrinks). If this becomes a problem, the updater can be
hardened to do a `Compare-Object` pre-extract and prune orphans listed in
a release `MANIFEST.txt`.

A future user-data directory (e.g. saved analysis sessions in v2) should
be added to the preserve list when introduced. The way preservation works
here — by what is *not* in the zip — means the preserve list is enforced
on the publish side, not the user side.

#### 6.5 Failure modes

| Situation | Behaviour |
|---|---|
| GitHub unreachable during install | `setup.bat` prints "Could not reach GitHub", exits non-zero. User can retry when online. |
| GitHub unreachable during update | Same — but the existing install continues to work, since the local files are untouched. |
| GitHub release zip malformed or partial | `Expand-Archive` fails, error message is shown. Existing files in install dir are still consistent (no partial overwrite — `Expand-Archive` is not atomic per-file but extracts to a temp dir first by default behaviour of PowerShell 5.1+). |
| Remote version equals local | Treated as "up to date"; exit fast. |
| Remote version older than local (developer rolled back a release) | Strict equality check; setup.bat does not update unless versions differ. Downgrade requires manual deletion of the install folder. |
| `uv sync` fails (network, PyPI down) | Files are updated but venv is stale; the chained local-mode call reports the error. Re-running setup.bat retries the sync. |
| User runs setup.bat twice in quick succession | Each invocation is independent; the second will find the files installed and exit fast or no-op the extraction. No lockfile needed for the current single-user model. |

In every failure case, the user can still run their previously-installed
version of the tool. The installer can never leave the user with no working
copy: it either succeeds in updating, or leaves the prior install untouched.

#### Phase 6c — Auto-update on launch *(shipped)*

Sections 6.1–6.5 deliver "one URL, double-click, install or update".
This sub-stage makes updates happen *without the user noticing*.

What ships:

- `run.bat` calls `setup.bat --silent-update` as its first step before
  launching the Dash app.
- `setup.bat --silent-update` queries the GitHub releases API, compares
  the returned tag to local `version.txt`, and exits 0 immediately if
  the versions match (no output at all). If a newer release is
  published, it downloads the zip, extracts in place over the install
  folder (user data — `outputs\`, `logs\`, `flask_session\`, `.env` —
  is preserved by the same allow-list that builds the zip), and runs
  `uv sync` to refresh dependencies. The user sees one short
  "An update is available…" line and the `uv sync` progress.
- A failed update (GitHub unreachable, download failure, `uv sync`
  failure) appends a timestamped line to `logs\auto-update.log` and
  exits 0 — the launch is never blocked; the user keeps their prior
  version.
- `run.bat --no-update` skips the check entirely (for slow networks or
  when the user wants to launch immediately).
- After the (optional) update step, `run.bat` spawns
  `_wait_and_open.ps1` in the background and starts the Dash app in
  the foreground. The helper polls TCP port 8050 every ~500 ms (up to
  90 s) and opens the URL in the default browser via `cmd /c start`
  the moment the port accepts a connection. This replaced an earlier
  fixed 4-second delay, which was fine for warm restarts but too short
  for the cold first launch on a fresh install (Python + Dash imports
  take 10–15 s the first time, so users were seeing a connection-
  refused page and refreshing by hand). The helper is a separate
  `.ps1` file — earlier inline-PowerShell attempts in `run.bat` kept
  getting mangled by cmd's quote handling. See commit ec54efc.

The mechanism is otherwise unchanged from §6.3 — same install dir,
same preserve list, same release artifacts. It is a thin invocation
wrapper on top of the already-built installer.

Design:

- `run.bat` calls `setup.bat --silent-update` (or equivalent) as its first
  step before launching the Dash app.
- In silent-update mode, `setup.bat` skips the pause prompts, suppresses
  the console UI for the up-to-date path, and only surfaces output if it
  actually performed an update.
- A failed update (GitHub unreachable, etc.) is logged but does not block
  launch — the user still gets the prior version.
- A `--no-update` flag on `run.bat` skips the check entirely for users
  with intermittently slow networks.

The mechanism is otherwise unchanged from §6.3 — same install dir, same
preserve list, same release artifacts. It's a thin invocation wrapper on
top of the already-built installer.

#### Phase 6d — Version footer + CHANGELOG modal *(shipped)*

The footer on every page now reads
`Version X.Y.Z — last updated YYYY-MM-DD`, where the date is the
``version.txt`` mtime (the install or auto-update extraction touches
this file, so the date reflects when the running release landed on
this machine). The version text is a button — clicking it opens a
modal showing the most recent shipped CHANGELOG sections, so a user
whose colleague has a feature they don't see can self-diagnose the
version gap without touching files. Bounded to the latest few
sections (`_MAX_CHANGELOG_SECTIONS = 3` in `ui/components/footer.py`)
so the modal stays scannable. The `[Unreleased]` working-set heading
is filtered out — end users only see shipped releases (the modal is
opened by users running an installed version, so a developer-side
"queued for the next release" block is irrelevant and reads as an
empty heading above the user's actual release notes).

Implementation: small additions to `ui/components/footer.py`
(`_last_updated_date`, `_recent_changelog` with the `[Unreleased]`
filter, the modal markup, and a ``@callback`` that toggles the
modal's ``style.display``) plus `.bc-modal*` styles in
`assets/theme.css`. No new dependencies.

#### 6.8 Configuration

No new keys required. The repo is hardcoded in `setup.bat` as
`bcgov/groundwater-drawdown-tool` because, like the BCGW DSN, it is not
user-tunable — pointing the installer at a fork is a code release.

A future `--release-channel` flag could let beta-testers track a non-`latest`
release tag (e.g. `pre-release` releases on GitHub), but Stage 1 doesn't
need this.

**Acceptance:**

- A new user downloads `setup.bat` from the latest-release URL, double-
  clicks it. Tool installs to `%USERPROFILE%\Tools\groundwater-drawdown-tool\`,
  uv + Python 3.13 + dependencies installed. Total time under 3 minutes
  on a typical office machine. `run.bat` launches the app.
- An existing user re-runs the same `setup.bat`. If a newer release has
  been published, the tool is updated in place (preserving `.env`,
  `outputs/`, `logs/`, `flask_session/`) in roughly 30 seconds. If the
  current version is already latest, setup.bat exits in under a second
  with "already up to date".
- Developer runs `publish_release.ps1` with uncommitted changes: aborts,
  no tag created, no release published.
- Developer bumps `version.txt`, commits, runs `publish_release.ps1`:
  tests pass, tag pushed, GitHub release created with both assets
  uploaded, release notes populated from the CHANGELOG version section.
- No `CLIENT_TBD` markers remain in the codebase except the
  deliberately-deferred ones (Q2, Q5), reworded as stated v2 notes.
- A GitHub Pages site is live with a User Guide and a Developer Guide,
  linked from `README.md` and the app footer.
- `run.bat` silently updates from the latest GitHub release on launch
  and never blocks the app if GitHub is unreachable.
- The app footer shows the running version and last-updated date and
  opens a modal of recent CHANGELOG entries.
- The release zip no longer carries `PROJECT_PLAN.md`,
  `DATA_REFERENCE.md`, or `DESIGN_NOTES.md`.

### Phase 7 — End-user testing feedback (July 2026) *(shipped v0.5.4)*

The first round of real end-user testing, on `v0.5.3`. Twenty items,
none of them structural: no change to the architecture, the layer
rules, or the Cooper-Jacob / SAD math, and no reported wrong number.
Seventeen items shipped in `v0.5.4`; three are deferred (below).

Delivered, grouped as committed:

- **Wording and constants.** Nearby aquifer suggestions 3 → 5 (busy
  Lower Mainland areas); manual material "Unconsolidated (sand and
  gravel)" → "Unconsolidated"; impact-chart caption corrected (the
  threshold line is dark on purpose — see
  `impact_chart._THRESHOLD_LINE_COLOR` — so the caption follows the
  line, not the reverse); "sorted worst-to-best" → "sorted by
  magnitude of impact"; plain-language keys for *s* / *r* and NPL.
- **Aquifer identity + the "Other" option.** Aquifer number leads
  everywhere, material in brackets. The undelineated-aquifer sentinel
  is now offered in *every* populated picker, not only when nothing
  contains the point — a well can sit inside mapped polygons and still
  be completed in an undelineated aquifer. Because manual mode no
  longer implies "nothing is mapped here",
  `AnalysisInputs.nearest_mapped_aquifer` records what was set aside
  and the results banner names it. A new `setup-aquifer-meta-store`
  carries structured picker metadata so the Run Analysis packer reads
  fields rather than parsing a display label.
- **Max drawdown tile removed** from the results page and the PDF.
  `AnalysisResult.max_drawdown_m` still computes and still reaches the
  usage log — only the display is gone.
- **Distance-drawdown chart.** A 0 m datum line (which required
  forcing zero into the y-range: every drawdown is positive, so a
  data-derived range would have drawn nothing); SAD bars split into
  orange (headroom) and red (drawdown ≥ SAD); asymmetric y-padding and
  a wider right margin so WTN labels stop clipping.
- **Licence status end-to-end.** `LICENCE_STATUS` was already queried
  and already on `WellResult` — it had simply never been displayed. Now
  on the table, CSV, map pop-up, PDF, KML, and standalone HTML map.
  Display-only, client-confirmed: it feeds no classification. NULL
  renders "Unknown", never folded into "Unlicensed". Licensed wells get
  a dark ring on the map — fill already encodes `WellStatus` and stroke
  weight encodes selection, so a ring is the channel left.
- **Method guidance.** Client-supplied paragraphs in
  `ui/disclaimers.py`, placed next to the control each is about rather
  than stacked in one block; the PDF carries all of it in one section
  because that artifact must stand alone.

Deferred, with the reasons recorded so the next pass starts informed:

- **Impact-chart WTN labels thin out** on a busy buffer
  (`_MAX_CHART_HEIGHT` squeezes bars until Plotly drops ticks).
- **Distance-drawdown WTN labels overlap** at similar radial
  distances. The client asked for vertical labels; **plotly 5.24's
  `go.Scatter` has no `textangle`**, so that needs the labels rebuilt
  as layout annotations. A cheaper option is alternating
  `textposition` plus a label on/off toggle. Both items are also
  bounded by a constraint neither fix escapes: charts are captured as
  PNGs into a fixed-size PDF page, so "show every WTN" cannot fully
  survive the export.
- **Flagging non-delineated aquifers** (e.g. Aquifer 1143) in the
  per-well table. Deliberately not a hardcoded ID, which would rot the
  first time BC adds another. Lead to chase first: the new aquifer
  label renders a null `MATERIAL` as "Aquifer 1143 (material not
  recorded)", so "has no `MATERIAL`" may be the data-driven rule. One
  query against `GW_AQUIFERS_CLASSIFICATION_SVW` settles it; pending
  client consultation either way.

## 7. Decision register

Nothing here is outstanding. These questions were raised at kickoff and are
now settled — most client-confirmed, two (Q2, Q5) deliberately deferred to a
future version.

The register is kept because the code cites these Q-numbers directly: `Q1` in
`core/aquifer_lookup.py`, `Q3`/`Q4`/`Q10` in `config.py`, `Q8` in
`data_access/db.py`, `Q12` in `ui/pages/setup_page.py`. Each entry records
what was decided and why, so those citations resolve to something.

- **Q1** (T/S lookup table by aquifer subtype) — **confirmed**: matches
  the legacy Excel `AquiferProperty_DB` exactly (Wei et al. 2009
  medians), stored in `data/ts_lookup.csv`. If the client later wants
  different values it is a `ts_lookup.csv` edit, no code change.
- **Q2** (T/S range vs single value per subtype) — **deferred to a
  future version**: v1 uses a single (T, S) per subtype, matching the
  legacy Excel. A later version may expose a range per subtype.
- **Q3** (at-risk threshold) — **confirmed**: drawdown ≥ **30%** of SAD,
  matching the legacy Excel `Impact!V` and the `InputValues!B30` summary
  filter. Configurable in `config.py` via `AT_RISK_DRAWDOWN_FRACTION`.
- **Q4** (default pumping duration) — **confirmed**: default **90 days**.
  The legacy Excel used 100 d (deck slide 5: east-coast Vancouver Island
  dry season, no recharge assumed); the client directed 90 d in Phase 5.
  UI offers presets for 30 d / 90 d / 180 d / 1 yr / 10 yr (3652.5 d).
- **Q5** (multiple pumping wells / superposition) — **deferred to a
  future version**: Stage 1 is single-well only in the UI.
  `core/drawdown.py` already accepts a list of pumping sources and sums
  them linearly, so adding superposition later is a UI change, not a
  math change.
- **Q6** (PDF report content) — generic professional layout for now;
  revisit after client review. Should mirror the legacy Excel outputs:
  input parameters, at-risk summary table, distance-drawdown chart,
  full per-well details table, disclaimers.
- **Q7** (existing Excel tool by D. van Everdingen and M. Leahey, 2024) — **received** as
  `iMapBCDistDrawdown_20241108.xlsx`. Used to derive: T/S lookup, SAD
  formula, reassigned-aquifer-material rule, chart layout, unit list,
  default duration, 30% threshold. Will also serve as the validation
  harness for `core/drawdown.py` — known input set produces known output.
- **Q8** (IT / network / outbound connectivity) — **confirmed**: IT
  permits user workstations outbound TCP to `bcgw.bcgov:1521` (over the
  gov network or VPN), and Python making such connections is acceptable
  to IT/security. Credentials are entered at runtime, never stored on
  disk.
- **Q9** (BCGW account model) — confirmed: each Water Officer has their
  own personal BCGW account.
- **Q10** (pumping duration default by region) — **confirmed**: the
  90-day default applies to all of BC; no region-specific conventions.
- **Q11** (SAD calculation for confined and bedrock aquifers) —
  **confirmed**: v1 matches the legacy Excel — compute unconfined-style
  SAD, flag confined and bedrock wells with a "manual review of driller's
  log recommended" note, and let the Water Officer enter the correct top
  via the per-well `top_of_fracture_or_aquifer_or_screen_m` override.
  Automated SAD for confined cases (using top-of-aquifer data from BCGW)
  is deferred to a future version.
- **Q12** (single-aquifer filtering default) — **confirmed**:
  default-OFF, and the filter is spatial (`SDO_ANYINTERACT` against
  the source aquifer polygon), not a GWELLS `AQUIFER_ID` attribute
  match. The spatial test safeguards against erroneous GWELLS aquifer
  assignments and against future re-delineation of aquifer boundaries.
- **Q13** (reassigned aquifer material rule) — **confirmed**: v1 ports
  the legacy Excel rule verbatim: `if BedrockDepth populated AND
  (FinishedDepth - BedrockDepth) > 5 ft, classify as "Bedrock", else
  "Unconsolidated"`. The client confirmed the `> 5 ft` threshold.

## 8. Working agreements

- No Dash imports anywhere in `core/` or `data_access/`.
- No SQL strings outside `data_access/queries.py`.
- No hardcoded paths. Anything filesystem-related goes through `config`.
- Use `logging`, never `print`.
- Use `pathlib.Path`, never raw strings for paths.
- Type hints on all public function signatures. `from __future__ import annotations`
  at the top of every module.
- Docstrings on every public function. For the math, include the equation in
  the docstring and cite the source (Cooper & Jacob 1946; Theis 1935).
- Tests for every function in `core/`. Tests in `tests/` mirror the package
  structure.

## 9. References

- Cooper, H. H., and C. E. Jacob (1946). A generalized graphical method for
  evaluating formation constants and summarizing well-field history.
  *Transactions, American Geophysical Union*, 27(4), 526–534.
- Theis, C. V. (1935). The relation between the lowering of the piezometric
  surface and the rate and duration of discharge of a well using ground-water
  storage. *Transactions, American Geophysical Union*, 16(2), 519–524.
- BC Water Sustainability Act:
  https://www.bclaws.gov.bc.ca/civix/document/id/complete/statreg/14015
- BC Data Catalogue (BCGW): https://catalogue.data.gov.bc.ca/
- GWELLS application: https://apps.nrs.gov.bc.ca/gwells/
