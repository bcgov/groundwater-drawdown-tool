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

- The **"Well tag number" input mode now links to the BC Groundwater
  Wells and Aquifers map** (apps.nrs.gov.bc.ca/gwells). If you don't
  have a well tag number handy, you can find one by location on that
  map; the link opens in a new tab.

### Changed

- The **page header now uses the official BC Government wordmark**,
  which sits flush in the dark-blue band instead of appearing as a
  white panel.

- **Storativity (S) now reads as a plain decimal** (e.g. `0.00003`)
  in the results-page input parameters and the PDF export, instead of
  scientific notation (`3e-05`). Transmissivity displays the same way.

- **When a results table is empty, the message is now a clearly
  highlighted notice instead of a faint line of text** — and the
  table's **Export CSV button is hidden when there's nothing to
  export**. This covers both "no wells were flagged at risk" and "no
  wells were found in the buffer". The buffer-empty message also
  suggests increasing the buffer radius and re-running.

### Fixed

- **Refreshing the Results page no longer re-runs the analysis or
  discards your edits.** Previously, pressing F5 (or restoring the tab)
  silently re-queried the BC Geographic Warehouse, wiped any per-well
  values you had overridden in the details table, and recorded the run
  a second time in the usage statistics. The page now reuses the cached
  result when the inputs haven't changed, so your overrides survive a
  refresh.

- The **Run Analysis button is now greyed out until you place a pumping
  point**, instead of letting you click it and then showing a "Place a
  pumping point first" message. Once a point is set (by map click,
  lat/lon, or well tag number), the button enables and any earlier
  message clears — so there's no need to scroll back up to check whether
  a point was placed.

## [0.5.1] — 2026-06-01

### Changed

- The **documentation site now opens in light mode by default**. 
  The light/dark toggle in the sidebar still works and still remembers your choice per browser.

### Fixed

- The footer's **"What's new"** panel no longer shows an empty
  *"Unreleased"* heading above the current release notes.
- **First launch on a fresh install no longer shows a
  connection-refused page.** `run.bat` now waits for the local server
  to be ready before opening your browser, instead of opening it
  after a fixed 4-second delay. On a cold first launch the server
  can take 10–15 seconds to start (Python and Dash have to load); the
  browser now opens at the moment the page is actually available, so
  there is no error page to refresh past. Subsequent launches are
  unchanged — the wait is essentially zero once everything is warm.

## [0.5.0] — 2026-05-25

First broadly-installable release. Phase 5 (visual identity, map
overlays, KML/PDF/HTML exports, logging and disclaimers) and Phase 6
(documentation site, auto-update on launch, version footer with
changelog modal) shipped. Distributed through GitHub Releases — end
users download `setup.bat` from the latest-release URL and the
installer pulls the matching tool zip. A pre-release security audit
closed out the open Dependabot advisories.

Pre-release for internal testing by the GIS team; a non-pre-release
follows for end users once internal sign-off is in.

### Security

- A pre-release dependency-and-code audit was completed; nine
  advisories were either resolved or formally reviewed. Five were
  fixed by refreshing transitive dependencies (`idna`, `urllib3`)
  and the development-only test runner (`pytest`). Four affect
  components that the tool depends on indirectly (Flask, Werkzeug)
  and are not exploitable on a localhost-only single-user tool; they
  will clear automatically when the tool migrates to the next major
  Dash release.
- The signed-in BCGW username is no longer written to the general
  application log file when a session starts. It remains in the
  structured usage log used for monitoring and troubleshooting, so
  traceability is unchanged.

### Phase 6 — Online documentation

#### Added

- An **online documentation site** is now available, with a
  step-by-step User Guide covering installation, BCGW account
  help, running an analysis, reading the results, exporting
  them, troubleshooting, and the methods and assumptions behind
  the calculations:
  <https://bcgov.github.io/groundwater-drawdown-tool/>
- A **"Documentation"** link in the footer of every page opens
  that site.
- The documentation site supports a **light/dark theme toggle**
  (defaults to dark; your choice is remembered per browser).
- When the tool starts, it now **checks for a new release on GitHub
  and updates itself in place** if one is available. The check is
  silent when nothing has changed; if an update is applied you see a
  short "An update is available…" line and the dependency refresh.
  Pass `--no-update` to `run.bat` to skip the check on a slow
  network. Update failures are logged to `logs\auto-update.log` and
  never block the app from starting.
- The footer on every page now shows **the running version and the
  date it was installed** — for example, *"Version 0.5.0 — last
  updated 2026-05-25"*. Clicking the version opens a **"What's new"
  panel** with the most recent release notes, so you can see at a
  glance what changed (and whether a colleague with a different
  install is on the same version as you).

### Phase 5d — Logging, sign-in messaging, and UI polish

#### Added

- The tool now keeps a **daily log file** in the `logs\` folder
  next to the tool (`gwdrawdown.log`). A new file starts each day
  and the last 30 days are kept, so if something goes wrong there
  is a record to look back on.
- **Usage logging.** Each time an analysis is run, a small summary
  record (run parameters and headline results — no passwords) is
  written to a central GeoBC log location, along with sign-in and
  error events. This helps the team monitor the tool's health,
  understand how it is used, and troubleshoot issues. If the
  central location can't be reached (for example, off the
  government network), logging quietly switches off — it never
  blocks or slows the tool.
- The sign-in screen now shows a **"BCGW account help guide"** link
  when sign-in fails, pointing at the documentation page that
  covers the common causes (locked or expired account, expired
  password, network or VPN) and the right next step for each.
- A short note on the sign-in screen confirming that **your
  password is never stored** — it is held only in memory for the
  session and discarded when you sign out.
- A second **"← Back to Setup"** button at the foot of the results
  page, so you don't have to scroll back to the top to start a new
  analysis.

#### Changed

- The page header now shows the official **British Columbia logo**
  in place of the typographic "British Columbia / Government of
  B.C." text.
- **Friendlier sign-in error messages.** A failed sign-in now
  explains the problem in plain language — wrong username or
  password, locked account, expired password, or a network /
  connection problem — instead of showing the raw database error.
  The technical error code is still shown, in small print, in
  case you need to quote it to support.
- Reworded the sign-in screen subtitle to "Connect to your BC
  Geographic Warehouse (BCGW) account to use the tool."
- Minor visual polish: the footer no longer repeats the signed-in
  user name (it is already shown in the header) and its
  disclaimer is centred; the "Impact % per well" chart caption is
  smaller so it sits below the section heading rather than
  competing with it.

### Phase 5b — Map layers and overlays

#### Added

- **Basemap switcher** on both the setup and results maps. A
  layers control in the top-right corner switches between
  OpenStreetMap (the default), a topographic basemap, and
  satellite imagery.
- **Context overlays** you can toggle on either map:
  - **Aquifers** — BC's mapped aquifer polygons, shown by default
    on the setup map. Appears once you are zoomed in to roughly
    regional scale.
  - **All BC Wells** — every registered well in the province, on
    the setup map. Appears only when zoomed in close, so it
    doesn't swamp the view.
  - **Water Management Districts** and **Water Management
    Precincts** — the administrative boundaries, each with a name
    label that tracks the part of the boundary you're looking at
    and follows you as you pan and zoom.
- A small **legend** in the bottom-right corner of the map
  explains the aquifer and well symbology. It appears only while
  those layers are switched on.
- The setup map shows a **crosshair cursor** while you are in
  "Map click" mode — a clearer cue that the map is waiting for a
  click to place the pumping point.

#### Changed

- Entering a latitude / longitude or looking up a well tag number
  now **recentres and zooms the map** to that point automatically,
  so you see it in context without panning there yourself.

### Phase 5c — Exports

#### Added

- **Download KML** button on the results page. Exports the
  pumping well and every nearby well as a KML file you can open
  directly in Google Earth. Each well is colour-coded by its
  status (at-risk, OK, and so on) and sized by its predicted
  impact — the same scheme as the results-page map — and carries
  its full result row (distance, drawdown, SAD, impact, and the
  rest), so you can inspect any well by clicking it in Google
  Earth.
- **Download PDF report** button on the results page. Produces a
  print-ready summary of the whole analysis, one section per
  page: page 1 — input parameters, a row of summary cards, and a
  method-and-assumptions note; the two result charts, one per
  page; then the at-risk wells table; then the full per-well
  details table. Every page carries a screening-tool disclaimer
  banner
  and a footer with the run timestamp, a unique run ID, the tool
  version, and your username — suitable for attaching to a
  licence assessment file. Wells outside the Cooper-Jacob
  validity range are tinted light purple in the per-well table,
  matching the on-screen view.
- **Download interactive map (HTML)** button on the results
  page. Produces a self-contained HTML file that opens in any
  browser as an interactive Leaflet map — the pumping well, its
  buffer, and every well with a click-through popup. A handy way
  to share the result without the full tool.
- All three exports reflect any per-well overrides you have
  applied, and the PDF charts are captured from exactly what you
  see on screen.

#### Changed

- The per-well CSV export gains an **"Outside Validity"** Yes/No
  column, so the Cooper-Jacob validity advisory (shown as a
  purple row tint on screen) survives the export to a format
  that can't carry cell colour.

### Phase 4d — Aquifer selection fallback + manual entry

#### Added

- **Nearby aquifers** are now offered on the setup page alongside
  the aquifer the well directly overlaps. The tool searches a
  1000 m radius and lists the three closest aquifers, each
  labelled with its distance (e.g. "Aquifer 123 — 47 m away") and
  tagged "(nearby — not directly overlapping)". The aquifer the
  well sits inside is tagged "directly overlapping" and
  pre-selected, but you can pick a nearby one instead — useful
  when a well sits inside one aquifer (e.g. bedrock) but just
  outside the boundary of the aquifer it should really be
  associated with (e.g. an unconsolidated aquifer 50 m away).
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
  (confirmed with the client). When enabled, the nearby-wells query
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
