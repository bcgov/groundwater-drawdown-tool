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
Excel tool (`Lookup_DB!B3:I10`) supports: Imp GPM, L/min, **L/s** (default),
m³/d, m³/min, m³/s, US GPM. Match this list. Default is L/s — Water Officers
think in L/s (the canonical example pumping rate is `3.97 L/s`). All inputs
are converted to m³/day before reaching `core/drawdown.py`. The conversion
factors are sourced from `data/unit_conversions.csv` so they can be
reviewed without touching code.

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
**CLIENT_TBD: Q13** — confirm whether `> 5 ft` is the standard rule or just
a convention in the Excel.

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
fill in by reading the driller's log. **CLIENT_TBD: Q11** — confirm whether
v1 should attempt automated SAD for confined cases (using top-of-aquifer
data from BCGW) or stay with the Excel's manual-override approach.

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
one line, not a refactor. **CLIENT_TBD: Q3** — confirm the threshold.

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
matches the legacy Excel: numeric value plus unit dropdown of Imp GPM,
L/min, L/s (default), m³/d, m³/min, m³/s, US GPM. Pumping duration
defaults to 100 days (legacy Excel convention for east-coast Vancouver
Island dry season; see deck slide 5), with quick-pick presets for "30
days", "100 days", "1 year", "10 years (perpetual licence)".
**CLIENT_TBD: Q4, Q10**.

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
appropriate. **CLIENT_TBD: Q12 — confirmed** (default-off,
spatial).

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
Export buttons for CSV (full results table), GeoJSON (well points with
results as attributes), and PDF (summary + chart + at-risk table).

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

## 6. Build order (phases for Claude Code)

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

### Phase 5 — Visual identity, map polish, exports, disclaimers

Phase 5 expands the original "Exports and polish" scope to absorb
two things that v0.4.0 deferred: a coherent visual identity (the
v0.4.0 UI ships with per-component inline styles and no real
theming), and richer maps (the setup-page map ships with a single
OSM basemap and no aquifer overlay, the results map likewise). PDF
export rounds out the exports trio (CSV ships; GeoJSON and PDF
don't), and a logging + disclaimer pass closes out the
"professional polish" theme.

Sub-staged like Phase 4 so each step is browser-verifiable and
bisectable:

- **5a — Visual identity / theme.** Pull the per-component inline
  style dicts out of Python and into a single CSS theme: design
  tokens for colour, typography, spacing, and radius; a wordmark
  / header chrome consistent with the BC government visual
  language (target reference: gov.bc.ca and BC Data Catalogue);
  consistent button/card/section/form styling; real footer
  treatment with version + signed-in user + Logout. The status
  palette in `ui/components/palette.py` already centralises one
  axis; this stage centralises the rest. Probably the largest
  sub-stage — design-token migrations always are. Wants a design
  sketch / reference set before committing to a direction
  (CLIENT_TBD: visual-direction conversation pending).
- **5b — Setup-page map improvements.** Basemap layer switcher
  (OSM / topographic / satellite imagery), an aquifer-polygon
  overlay so the officer can see polygon boundaries when picking
  the pumping point (lazy-loaded vector tiles or WMS against
  BCGW where available), an existing-wells overlay drawn once
  the point is placed so the officer can eyeball the buffer
  contents before clicking Run Analysis. The results map
  inherits the same basemap switcher and overlays as a
  consistency win.
- **5c — Exports.** CSV is already in (custom buttons on both
  tables). Add GeoJSON export of the well set (one feature per
  well, properties = full per-well row including overrides) and
  PDF export of the full run. PDF stack: `reportlab` is already a
  dep. Content per the legacy-Excel parity goal:
  - Input parameters block (pumping point, source aquifer + subtype,
    T/S with `(override)` tag when applicable, Q, duration, buffer,
    spatial-filter on/off).
  - Cooper-Jacob assumptions disclaimer.
  - At-risk summary table.
  - Distance-drawdown chart image.
  - Impact-% bar chart image.
  - Full per-well details table (with override markers).
  - Footer: BCGW snapshot date (if obtainable), run timestamp,
    run ID (UUID), tool version from `version.txt`, signed-in user.
  - "Screening tool — not a replacement for qualified hydrogeologist
    review" banner on every page.
- **5d — Logging + caveat text + disclaimer.** Rotating daily log to
  `./logs/gwdrawdown.log` (replaces the current `basicConfig`
  setup in `app._configure_logging`). Final caveat / disclaimer
  pass on /results, the PDF, and the login page (BCGW
  credentials handling reassurance). Acceptance is light: logs
  rotate, disclaimers are in place, no behavioural changes.

**Acceptance (full Phase 5):** UI reads as a coherent, professionally
branded tool rather than the Dash-default appearance. Setup-page map
offers basemap and aquifer overlay choices. All three exports (CSV,
GeoJSON, PDF) produce correctly-formatted files; PDF mirrors the
legacy Excel artifact. Logs rotate daily; disclaimers are visible on
every officer-facing surface.

### Phase 6 — Distribution and updates via GitHub Releases

Goal: end users get the tool by downloading one file from a URL, and future
releases reach them with at most one re-run of that same file. The mechanism
must be invisible when there's nothing to do, and self-explanatory when there
is. Users are non-technical.

This section was originally scoped as "auto-update from a BC government
network share". Pivoted in Phase 5a to **GitHub Releases** as the
distribution channel — public repo (`bcgov/groundwater-drawdown-tool`),
zero IT-provisioning to set up, stable forever-URLs via
`releases/latest/download/<asset>`. The bulk of the work (publish workflow,
install/update via `setup.bat`) lands ahead of Phase 5b; the auto-update-on-
launch wrapper is the remaining Phase 6 work.

#### 6.1 The release layout

Each tagged release on GitHub carries two assets:

- **`setup.bat`** — the one file end users download. Self-contained:
  detects bootstrap vs local mode and either fetches the release zip or
  installs Python dependencies. The same file is also the in-place updater
  on subsequent runs.
- **`groundwater-drawdown-tool.zip`** — the tool payload. Contains
  `src/`, `data/`, `pyproject.toml`, `uv.lock`, `.python-version`,
  `setup.bat`, `run.bat`, `version.txt`, `CHANGELOG.md`, and the project
  docs (`README.md`, `CLIENT_INSTALL.md`, `PROJECT_PLAN.md`,
  `DATA_REFERENCE.md`, `DESIGN_NOTES.md`, `references/excel_chart_layout.md`).
  Explicitly excluded: `.venv/`, `outputs/`, `logs/`, `flask_session/`,
  `.env`, `.git/`, `__pycache__/`, `*.pyc`, `tests/`, `scripts/`,
  client-confidential reference materials.

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
   groundwater-drawdown-tool.zip setup.bat`.

A `-Draft` flag creates the release in draft state for pre-release review.

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

#### 6.6 Phase 6 proper — auto-update on launch (deferred)

Sub-stages 6.1–6.5 deliver "one URL, double-click, install or update". The
remaining piece — making updates happen *without the user noticing* — is
the Phase 6 work that lands after Phase 5.

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

#### 6.7 What gets surfaced in the UI

A footer line on every page: `Version 0.5.0 — last updated 2026-05-19`.
Clicking it opens a modal showing the recent CHANGELOG entries, so users
can see what changed without touching files. This is also where you handle
"my colleague says feature X exists but I don't see it" — they're on
different versions, the footer tells them. Implementation is a small
addition to `ui/components/footer.py` and lands alongside the §6.6 launch-
update wrapper.

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

## 7. Open questions, kept visible in the codebase

These are placeholders pending client confirmation. Each one is tagged in code
with `# CLIENT_TBD: Q<n>` so they're greppable. When answers come in, find and
update.

- **Q1** (T/S lookup table by aquifer subtype) — confirmed: matches the
  legacy Excel `AquiferProperty_DB` exactly (Wei et al. 2009 medians).
  Stored in `data/ts_lookup.csv`. Q1 effectively closed unless the client
  wants different values; flag remains so they can opt-in to a refresh.
- **Q2** (T/S range vs single value per subtype) — single value for now,
  matching legacy Excel behaviour. Hydrogeologists can be invited to
  expand this later.
- **Q3** (at-risk threshold) — updated default: drawdown ≥ **30%** of SAD,
  matching the legacy Excel `Impact!V` and the `InputValues!B30` summary
  filter. Configurable in `config.py` via `AT_RISK_DRAWDOWN_FRACTION`.
- **Q4** (default pumping duration) — updated default: **100 days**,
  matching the legacy Excel convention (deck slide 5: east-coast Vancouver
  Island dry season, no recharge assumed). UI offers presets for 30 d /
  100 d / 1 yr / 10 yr (3652.5 d, "perpetual licence" — deck slide 21).
- **Q5** (multiple pumping wells / superposition) — Stage 1 is single-well
  only in the UI. `core/drawdown.py` accepts a list of pumping sources
  and sums them linearly, so adding superposition later is a UI change,
  not a math change.
- **Q6** (PDF report content) — generic professional layout for now;
  revisit after client review. Should mirror the legacy Excel outputs:
  input parameters, at-risk summary table, distance-drawdown chart,
  full per-well details table, disclaimers.
- **Q7** (existing Excel tool by Lepitre and Beebe) — **received** as
  `iMapBCDistDrawdown_20241108.xlsx`. Used to derive: T/S lookup, SAD
  formula, reassigned-aquifer-material rule, chart layout, unit list,
  default duration, 30% threshold. Will also serve as the validation
  harness for `core/drawdown.py` — known input set produces known output.
- **Q8** (IT / network / outbound connectivity) — confirm that user
  workstations are permitted outbound TCP to `bcgw.bcgov:1521` (over the
  gov network or VPN), and that Python making such connections is
  acceptable to IT/security. Credentials are entered at runtime, never
  stored on disk.
- **Q9** (BCGW account model) — confirmed: each Water Officer has their
  own personal BCGW account.
- **Q10** (pumping duration default by region) — confirm that 100 days is
  the right default for all of BC, or whether different regions
  (Interior, North) use different conventions. Also confirm the 10-year
  preset (3652.5 d) wording — "perpetual licence" or something else?
- **Q11** (SAD calculation for confined and bedrock aquifers) — v1
  matches the legacy Excel: compute unconfined-style SAD, flag confined
  and bedrock wells with a "manual review of driller's log recommended"
  note, expose a per-well override field for `top_of_fracture_or_aquifer_or_screen_m`.
  Confirm whether this is acceptable, or whether v1 should attempt
  automated SAD for confined cases using top-of-aquifer data from BCGW
  (more complex — needs a separate data source for aquifer-top
  elevations).
- **Q12** (single-aquifer filtering default) — **confirmed**:
  default-OFF, and the filter is spatial (`SDO_ANYINTERACT` against
  the source aquifer polygon), not a GWELLS `AQUIFER_ID` attribute
  match. The spatial test safeguards against erroneous GWELLS aquifer
  assignments and against future re-delineation of aquifer boundaries.
- **Q13** (reassigned aquifer material rule) — v1 ports the legacy Excel
  rule verbatim: `if BedrockDepth populated AND (FinishedDepth -
  BedrockDepth) > 5 ft, classify as "Bedrock", else "Unconsolidated"`.
  Confirm whether the `> 5 ft` threshold is a documented standard or
  just convention; if convention, confirm it's still appropriate.

## 8. Working agreements for Claude Code

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
- Commit at the end of every phase with a clear message. Don't squash phases.
- If a design decision wasn't covered in this plan, surface it in chat before
  implementing. Don't silently invent.

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
