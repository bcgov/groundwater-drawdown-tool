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

### Removed

- `.env.example`. The tool runs without a `.env`; BCGW credentials are
  entered through the login UI at runtime. Override variables are
  documented in `README.md`.

## [0.1.0] — TBD

First development version. Not yet released to users.
