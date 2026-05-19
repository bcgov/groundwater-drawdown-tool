# Changelog

All notable changes to the Groundwater Drawdown Tool are recorded here.
Each release moves items from `[Unreleased]` into a versioned section.

The wording in this file is shown to end users when the tool auto-updates,
so write entries in plain English. Avoid jargon. Lead with what changed
from the user's perspective, not how it was implemented.

Format inspired by [Keep a Changelog](https://keepachangelog.com/) — Added,
Changed, Fixed, Removed.

## [Unreleased]

### Phase 4d — Aquifer selection fallback + manual entry

#### Added

- **Nearby-aquifer fallback** on the setup page. When the pumping
  point doesn't sit inside a mapped aquifer polygon, the tool now
  searches a 1000 m radius for nearby aquifers and lists the three
  closest as fallback choices, each labelled with its distance
  (e.g. "Aquifer 123 — 47 m away") and tagged as "(nearby — not
  directly overlapping)" so it's clear they aren't direct hits.
  Helpful for wells that fall just outside a re-delineated aquifer
  boundary.
- **Manual-entry mode** for remote areas the Province hasn't
  mapped. A "No mapped aquifer at this location — enter materials
  manually" option appears at the bottom of the picker in the same
  fallback list. Choosing it reveals an aquifer-material dropdown
  (Unconsolidated or Bedrock) and requires you to enter T and S
  values directly. The same-aquifer filter is disabled in this
  mode (there's no polygon to filter against), and the results
  page shows an orange banner above the run summary so reviewers
  can see at a glance the run was based on user-supplied
  materials and T/S rather than mapped data.
- If no aquifers are found within 1000 m **and** none contain the
  point, the picker shows just the manual-entry option with a
  note explaining nothing nearby was found, so the workflow is
  never blocked by missing aquifer coverage.

### Phase 5a.3 — Distribution via GitHub Releases

#### Changed

- The tool now ships through GitHub Releases instead of being handed
  out as a folder. End users download **one file** —
  `setup.bat` from
  <https://github.com/bcgov/groundwater-drawdown-tool/releases/latest/download/setup.bat>
  — and double-click it. The installer pulls the matching release
  zip, extracts it to `%USERPROFILE%\Tools\groundwater-drawdown-tool\`,
  installs `uv` + Python 3.13, and runs `uv sync`. No editing files,
  no admin rights.
- Re-running the same `setup.bat` checks for newer releases and
  updates the install in place. `.env`, `outputs\`, `logs\`, and
  `flask_session\` are preserved across updates so users don't lose
  exports or have to re-login on every release. Update time is
  roughly 30 seconds; "already up to date" exits in under a second.
- `CLIENT_INSTALL.md` rewritten end-to-end for the one-URL flow.

#### Added

- `scripts/publish_release.ps1` — developer-side release script.
  Verifies a clean tree on `main`, runs `uv run pytest`, builds
  `groundwater-drawdown-tool.zip` excluding dev cruft, tags the
  commit, pushes the tag, and creates the GitHub release with the
  zip and `setup.bat` as assets. Release notes are extracted from
  the matching `CHANGELOG.md` section. `-Draft` flag for pre-release
  review; `-SkipTests` for emergency use.
- README publish-workflow section covering `gh` CLI setup and the
  release cut steps.

### Phase 5a.2 — Setup-page polish and form styling

#### Added

- Section icons beside each setup-page section heading
  (location pin, layers, sliders).
- The setup page's source-aquifer "Override default T / S" and
  "Filter out wells spatially outside source aquifer" controls
  are now **on/off toggle switches** (instead of basic checkboxes)
  so it's clearer at a glance whether they are on or off.
- The setup-page input-mode selector (Map click / Lat-Lon / Well
  tag number) is now a **segmented control** — one row of three
  buttons rather than radio dots.
- A new **m³/yr** pumping-rate unit, so multi-year licence-volume
  estimates can be entered directly without pre-converting.

#### Changed

- Pumping-rate unit list reordered to lead with m³/d (now default),
  followed by m³/min, m³/s, m³/yr, L/min, L/s. Imperial GPM and
  US GPM removed (BC officers don't use them outside the legacy
  BCGW YIELD column, which still flows through its own conversion).
  Default Q value is now 200 m³/d (was 3.97 L/s).
- Default pumping duration is **90 days** (was 100). Quick-pick
  presets are now 30 d / 90 d / 180 d / 1 yr / 10 yr.
- Results page now reads as a sequence of clearly-separated
  sections (Distance-drawdown, Impact %, Map, At-risk, All wells)
  with a faint divider line above each section heading. Headings
  are smaller and more compact so the charts and tables get the
  visual attention.
- "Map" section heading renamed to **"Wells in buffer (map view)"**
  so it describes what the map actually shows.
- "Editable columns" line on the per-well details table is now
  on its own bold line and lists the four columns directly, with
  the longer usage notes below it.
- The pagination reminder under the at-risk and per-well tables
  moved from above the table to below — closer to the page
  controls themselves.
- Setup-page Lat / Lon and Well-tag-number input panels now have
  compact, fixed-width inputs with the action button on its own
  row below.

#### Fixed

- The footer no longer floats above the bottom of the screen on
  short pages like the login screen — the page wrapper was
  shortening itself by the header height it contained.

### Phase 5a.1 — Visual identity

#### Added

- The tool now follows the BC government visual identity. Every
  page has a dark-blue header with the "British Columbia"
  wordmark, a thin gold stripe, the app title, and (once signed in)
  your username with a Logout button. Matching dark-blue footer
  with the version, your username, and a "screening tool" reminder.
- A **show / hide password** button (eye icon) on the sign-in
  screen, in case you want to double-check what you typed.

#### Changed

- The status tiles on the results page (Total wells, At risk, OK,
  etc.) have been redesigned. White tiles with a coloured left
  edge and a larger number, in place of the pale pastel
  backgrounds — easier to read at a glance and consistent with the
  rest of the new BC theme.
- Buttons, section panels, and link colours updated to match the
  BC navy and gold palette.

## [0.4.0] — 2026-05-14

First milestone release. Phase 4 complete: end-to-end interactive
workflow from BCGW login through to a results dashboard with two
charts, a colour-coded map, an at-risk summary table, and an
editable per-well details table with live recompute. The tool now
runs the same canonical example case as the legacy Excel and
produces visually-equivalent output (deck slide 21 reference).

Not yet released to end users — the auto-update mechanism (Phase 6)
isn't built, so installation is still a manual checkout. Treat 0.4.0
as the milestone version against which Phase 5 polish and exports
will land.

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
- Phase 4c.2 editable per-well overrides + live recompute. The
  per-well details table on /results gains four editable columns —
  NPL, finished depth, stickup, and top of fracture/aquifer/screen
  — and rebuilds SAD, Impact %, status, the at-risk summary table,
  and the seven stat cards as the officer types. Overrides live in
  a sessionStorage `dcc.Store` keyed by WTN; the page-level
  pipeline callback caches the BCGW result in another Store
  (`analysis-result`) so override edits and tab refreshes don't
  replay the queries. Editing a cell to match the BCGW value
  reverts the override; clearing a cell does the same. The four
  editable columns are declared with `type="any"` (rather than
  `numeric`) so dash_table doesn't treat empty input as invalid
  and silently revert the cell; the trade-off is alphabetical sort
  on those four columns, which the new "Edited" summary column at
  the right of the table compensates for. The Edited column
  lists the field names of any active overrides for each row
  (e.g. `"NPL, Stickup"`) and is carried through to the CSV
  export. A "Reset all overrides" button next to Export CSV wipes
  every per-well override in one click. Rows with active
  overrides are tinted light yellow. New
  `analysis.recompute_well` (pure math,
  no DB) shares its kernel with `_compute_well_result`;
  `analysis.apply_overrides` rebuilds the `AnalysisResult` totals
  from a cached base + per-WTN override map. New
  `analysis.effective_u_threshold` centralises the Cooper-Jacob
  bypass — flipping the bypass back is now a one-line edit shared
  by the initial pipeline and the override recompute. JSON
  round-trip on `WellResult` and `AnalysisResult` preserves the
  three enum fields. 110 pytest tests passing (14 new); ruff
  clean.
- Phase 4c.3 distance-drawdown chart, results map, spatial source-
  aquifer filter, and advisory Cooper-Jacob validity flag. The
  /results page now leads with a Plotly distance-drawdown chart
  (red dots with WTN labels, smooth black Cooper-Jacob curve,
  vertical orange SAD bars, inverted Y axis) matching the legacy
  Excel chart from deck slide 21, followed by a `dash-leaflet` map
  with the pumping well, a translucent buffer-radius circle, and a
  `CircleMarker` per observation well coloured by status and sized
  by predicted impact. Chart and map are cross-linked through a
  page-scoped `selected-well` Store: clicking a chart point or a
  map marker highlights the matching well in both views.
- Source-aquifer filter is now **spatial** and **default off**
  (CLIENT_TBD Q12 confirmed). When enabled, the nearby-wells query
  filters with an `SDO_ANYINTERACT` correlated subquery against
  the source aquifer polygon geometry rather than comparing
  `w.AQUIFER_ID` to the source id. This safeguards against stale
  GWELLS aquifer assignments and against future re-delineation of
  aquifer boundaries — a well's recorded `AQUIFER_ID` may drift,
  but its point geometry is authoritative. Filter label updated
  to "Filter out wells spatially outside source aquifer".
- Cooper-Jacob u<0.01 validity check is now an **advisory** rather
  than a hard status (per client direction). Wells failing the
  check keep their SAD-based status (`AT_RISK`, `OK`, etc.) and
  the math still computes `u_max` per row, but the per-well table
  tints the affected rows light purple so the officer can spot
  them at a glance. Purple takes precedence over the yellow
  override tint on rows that trip both. A small legend above the
  per-well table explains the row tints and reminds users that
  the table paginates after 10 rows.
- Setup page now restores the last-run inputs on Back-to-Setup.
  Point, lat/lon, Q + unit, duration, buffer radius, same-aquifer
  filter, and the source-aquifer pick all replay from
  `analysis-inputs` on /setup mount, so iterating on a parameter
  no longer means re-keying the whole form. T/S override values
  are deliberately not restored — re-tick "Override default T / S"
  if you customised them.
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

## [0.1.0] — superseded

Initial scaffolding version, never released; rolled into 0.4.0
above when Phase 4 closed out.
