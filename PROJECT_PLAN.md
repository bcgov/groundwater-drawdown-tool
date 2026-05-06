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
- `OUTSIDE_VALIDITY` — Cooper-Jacob `u >= 0.01` at this distance/duration.

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

**Single-aquifer filtering.** Once the pumping point is placed, the tool
queries the aquifer polygon containing it and offers (default on) to
filter the nearby-wells list to only wells with the same `AQUIFER_ID`.
This automates a manual step from the legacy workflow (deck slide 19:
"remove or otherwise flag all wells that are in a different aquifer").
A toggle lets the user disable filtering to show all wells in the
buffer with a clear visual distinction for "different aquifer".
**CLIENT_TBD: Q12** — confirm preferred default behaviour.

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

- `ui/app.py` with multi-page setup, server-side session handling
  (Flask-Session, filesystem backend pointed at `./flask_session/`),
  and a session-required decorator/check for protected pages.
- `ui/pages/login_page.py` — BCGW credentials form, read-only display of
  the connection target, connection-test on submit (`SELECT 1 FROM DUAL`),
  initialises pool on success, redirects to setup. Logout button on every
  page footer that closes the pool, clears the session, and returns to
  login.
- `ui/pages/setup_page.py` with all three input methods, the Q-with-units
  dropdown, duration presets (30 d / 100 d / 1 yr / 10 yr), and the
  single-aquifer filter toggle. Protected: redirects to login if no
  session.
- `ui/pages/results_page.py` with the at-risk summary table, stat cards,
  the distance-drawdown chart matching the legacy Excel layout (see
  `references/excel_chart_layout.md`), the colour-coded map, and the
  full per-well details table. Protected: redirects to login if no
  session.
- `core/flagging.py`, `core/well_classification.py`, and `core/sad.py`
  integrated into the results pipeline.
- Session timeout configured (default 8 hours of inactivity → re-login).

**Acceptance:** user launches the app, sees login page, enters BCGW
credentials, lands on setup page, runs an analysis through to results,
clicks logout, sees login page again. Wrong credentials show an inline
error and don't redirect. The username appears in the UI footer (and in
log entries) for the active session. The at-risk summary table and the
distance-drawdown chart are visually equivalent to the legacy Excel
output (deck slide 21).

### Phase 5 — Exports and polish

- CSV, GeoJSON, PDF export buttons wired up via `dcc.Download`.
- PDF includes: input parameters, T/S used (default vs manual override flagged),
  Cooper-Jacob assumptions disclaimer, BCGW snapshot date if obtainable from
  the database, timestamp, run ID (UUID), tool version (read from `version.txt`).
- Logging configured to write to `./logs/gwdrawdown.log` rotating daily.
- Final pass on caveat / disclaimer text in the UI.

**Acceptance:** all exports produce correctly-formatted files; logs capture
each analysis run with input parameters and tool version.

### Phase 6 — Auto-update from network share

Goal: end users running an older version automatically receive the latest version
the next time they double-click `run.bat`. Zero clicks beyond the normal launch.
Users are non-technical; the mechanism must be invisible when there's nothing to
do, and self-explanatory when there is.

#### 6.1 The publishing layout

A folder on a BC government network share that all Water Officers can read and
the developer can write to. Layout:

```
\\<share>\<path>\groundwater-drawdown-tool\
├── version.txt              # single line: latest published version, e.g. 0.4.2
├── CHANGELOG.md             # latest changelog (mirror of repo)
└── releases\
    └── latest\              # contents of the latest release (tool folder
        │                    # without .env, outputs/, logs/, .venv)
        ├── version.txt
        ├── pyproject.toml
        ├── uv.lock
        ├── src/
        ├── data/
        ├── run.bat
        ├── setup.bat
        ├── update.bat
        └── ...
```

The `version.txt` at the share root exists so the updater can read it cheaply
(one small file) before deciding whether to copy anything.

A separate `releases\archive\<version>\` folder retains previous releases for
rollback. The updater never reads from `archive/`; it exists for manual recovery.

#### 6.2 The publish workflow (developer side)

A `scripts/publish_release.bat` (or `.ps1`) script that:

1. Reads `version.txt` from the local repo.
2. Confirms the local repo is clean (no uncommitted changes) and on the main
   branch — abort if not.
3. Runs `uv run pytest` — abort if any test fails.
4. Tags the git commit with the version (`git tag v<version>`).
5. Robocopies the repo to `\\<share>\...\releases\latest\`, excluding `.env`,
   `.venv\`, `outputs\`, `logs\`, `__pycache__\`, `.git\`, `tests\`,
   `*.pyc`, and any other dev-only files.
6. Copies the same files to `\\<share>\...\releases\archive\<version>\`.
7. Updates the `version.txt` and `CHANGELOG.md` at the share root last (so the
   version flip is the final atomic step — users are never pointed at an
   incomplete release folder).

The publish script is run by the developer from a connected workstation. No
CI/CD in Stage 1 — manual is fine for one developer and one client team.

#### 6.3 The update workflow (user side)

A new `update.bat` (idempotent, callable directly or by `run.bat`):

1. Read remote `version.txt` from the share path. If unreachable (offline,
   VPN down, share not mapped): log a warning, exit 0 (do not block launch).
2. Read local `version.txt`. If equal to remote: exit 0 silently.
3. If remote is newer: show a small console window: "A new version (X.Y.Z) is
   available. Updating... please wait." Display the relevant section of the
   remote `CHANGELOG.md` so the user sees what changed.
4. Robocopy `releases\latest\` over the local install. Exclude (preserve)
   `.env`, `outputs\`, `logs\`, `.venv\`. Use `/MIR` mode but with explicit
   `/XD` and `/XF` for the preserved paths.
5. Run `uv sync` so any dependency changes in the new release are applied.
6. Show "Updated to version X.Y.Z. Launching..."
7. Exit 0; the calling `run.bat` proceeds to launch the app.

`run.bat` is modified to call `update.bat` as its first step, then proceed
to launch the Dash app regardless of update outcome (a failed update should
not prevent the user running the previous version).

A `--no-update` flag on `run.bat` skips the update check, in case the share
is intermittently slow and a user wants to launch quickly. Document this in
`CLIENT_INSTALL.md` for IT/support reference; don't surface it as a normal
option to end users.

#### 6.4 What gets preserved across updates

These paths are never overwritten by the updater:

- `.env` — if it exists. Most users won't have one (the tool runs without
  it); but if a user has created one to override defaults, it must be
  preserved.
- `flask_session/` — server-side session store. Preserving it across update
  avoids forcing every user to re-login on every release.
- `outputs/` — exports the user has generated.
- `logs/` — historical logs (rotated separately).
- `.venv/` — `uv sync` manages this, never the file copy.

A user-data directory is reserved for future use (e.g. saved analysis sessions
in v2). When introduced, add to the preserve list.

#### 6.5 Failure modes and behaviour

| Situation | Behaviour |
|---|---|
| Share unreachable | Log warning, launch local version, no error to user |
| Remote `version.txt` malformed | Log warning, launch local version |
| Remote version older than local (developer rolled back) | Treat as "up to date", do not downgrade silently |
| Robocopy partial failure (file locked, etc.) | Log error, launch local version, don't leave a half-updated install |
| `uv sync` fails (network, PyPI down) | Log error, launch local version. Files are updated but venv is stale; on next launch `uv sync` retries via setup |
| User launches while previous update is in progress | `update.bat` uses a lockfile to detect concurrent runs and skips |

In every failure case, the user can still run yesterday's version of the tool.
The updater can never leave the user with no working tool.

#### 6.6 Configuration

New key in `.env.example` and `config.py`:

```
# Path to the network share where releases are published.
# Leave empty to disable auto-update (e.g. for offline or testing use).
UPDATE_CHECK_SHARE=
```

The path is read by `update.bat`, not by Python — but it's documented in
`config.py` for completeness so all configuration is discoverable from one
place.

#### 6.7 What gets surfaced in the UI

A footer line on every page: `Version 0.4.2 — last updated 2026-05-05`.
Clicking it opens a modal showing the recent changelog entries, so users can
see what changed without touching files. This is also where you handle
"my colleague says feature X exists but I don't see it" — they're on
different versions, the footer tells them.

**Acceptance:**

- A user with version 0.1.0 installed launches `run.bat`. The updater detects
  version 0.2.0 on the share, copies the new files (preserving `.env` if
  present, plus `flask_session/`, `outputs/`, `logs/`), runs `uv sync`,
  and the app launches as 0.2.0. Total time under 30 seconds.
- The same user, run again: the updater detects same version and exits in
  under a second. Launch is indistinguishable from no auto-update.
- The same user, with the share unreachable: the app launches as 0.2.0 with
  a warning logged. No error popup.
- Developer runs `publish_release.bat` with uncommitted changes: aborts, no
  files written to the share.

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
- **Q12** (single-aquifer filtering default) — v1 will offer the filter
  default-on (auto-filter results to wells in the same aquifer as the
  pumping point). Confirm that's the preferred default; an alternative
  is default-off with a clear visual indicator on out-of-aquifer wells.
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
