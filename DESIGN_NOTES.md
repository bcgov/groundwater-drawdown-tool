# Design Notes — Stage 1 Decisions Made With Stage 2 in Mind

This file exists so that, six months from now, no one undoes a Stage 1
decision because it looks unnecessary for a single-user local tool. Every
choice listed here is intentional and exists for the deployment we're not
doing yet.

If you find yourself thinking "this is over-engineered for a local tool" —
read the relevant section first.

## Why `src/gwdrawdown/` and not flat scripts

A real installable package means `from gwdrawdown.core.drawdown import cooper_jacob`
works identically:

- in tests (`uv run pytest`),
- when the Dash app launches via `run.bat`,
- when a future ArcGIS Pro `.pyt` imports the same function,
- when a future container runs `pip install .` and exposes a CLI.

Flat scripts in a top-level directory only work in one of these contexts.
Switching layouts later is a tedious, error-prone refactor that touches every
import.

## Why a connection pool for one user

`oracledb` thin-mode pooling has near-zero overhead at pool size 2-4. A single
user clicking "Run Analysis" still benefits from connection reuse across
sub-queries. More importantly, the surrounding code (acquire / release / close)
is the same code we'd want at deployment, so we never have to retrofit it.

## Why no module-level mutable state

Dash makes it tempting to cache things in module globals (e.g. "remember the
last user's pumping point so I can show it on the results page"). It works on
a single-user laptop. It fails immediately on a multi-user server because all
users share the same Python process. State lives in:

- `dcc.Store` — browser-side, per-user.
- Component values — implicit per-session.

The Python process is treated as stateless from day one. This costs nothing
locally and is mandatory at deployment.

## Why configuration is split: hardcoded constants, optional `.env`, runtime credentials

There are three categories of "config" in this tool, and they're handled
differently on purpose.

**Hardcoded constants in `config.py`.** Things that are the same for every
user, every machine, every deployment, and that we don't want a user to
fiddle with. The BCGW DSN (`bcgw.bcgov:1521/idwprod1.bcgov`) is the
canonical example. It's not secret, but it's also not something an end
user has any business editing. If BC ever changes the host, we ship a
new release.

**Optional overrides via `.env`.** Things that have sensible defaults but
that a power user or a deployment might want to vary (logging level,
output directory, threshold defaults). These live as defaults inside
`config.py` and are overridable via `os.environ` (loaded from `.env` if
present). The tool runs without any `.env` file. A `.env.example`
ships with the repo as documentation; it is not required to copy it.

**User credentials (BCGW username and password).** Never stored on disk.
Entered at runtime through the login UI, held in server-side session
memory for the duration of the session, cleared on logout or session
expiry. Rationale below in its own section.

What this avoids: a deployment story where end users have to edit a config
file with secrets in it, get the format wrong, ask for help, leak the
file in a backup, or forget to update it when their password rotates.

Hardcoded paths to `C:\Users\moez\...` in particular will silently break on
every other developer's machine and on every server. They're forbidden.

## Why BCGW credentials are entered at runtime, not stored

A few interlocking reasons:

**Quarterly password rotation.** BCGW passwords expire every ~3 months.
If passwords lived in `.env`, every quarter every user would either have a
broken tool or need to be walked through editing a config file. Runtime
login means rotation is a no-op for the tool — they type the new password
the next time they launch it.

**Plain-text storage is an audit problem.** A `.env` file containing an
Oracle password is a stored credential, even if the user is the only one
on the machine. It can be screen-shared by accident, swept up by AV/DLP
scanning, end up in a backup, or get checked into source control by a
confused user. "The password only exists in memory while the tool is
running" is a much cleaner story for IT/security review.

**Per-user accounts get enforced naturally.** Each Water Officer has their
own BCGW account. Runtime login makes it obvious that you sign in as
yourself; no shared `.env` file means no accidentally-shared credentials.
The username appears in logs and PDF exports, which matters for audit
defensibility on statutory decisions.

**Trade-off, named honestly:** the tool can't run unattended. There's no
way to schedule a nightly batch run with no human to log in. For a
screening tool used during licence review, that's fine — it's interactive
by design. If someone ever asks for automation, the answer is "that
needs a service account and a different design," not "let's add a
credentials file."

What we explicitly do not build:

- No "Remember me" checkbox in the login form. The browser's password
  manager (Chrome, Edge) handles convenience for users who want it; the
  tool itself never writes credentials anywhere.
- No `.env` fallback for credentials, even for "developer convenience."
  Same posture for everyone, including the developer running the smoke
  test (`scripts/smoke_test_db.py` prompts via `getpass`).

## Why `logging` and not `print`

`print` writes to stdout with no level, no timestamp, no module name, and no
ability to filter or rotate. `logging` does all of that and supports both file
output (Stage 1) and stdout capture by an orchestrator (Stage 2) with no
code change. The `logging.config` is set up once in `app.py`, and every other
module just calls `logger = logging.getLogger(__name__)`.

## Why exports go through `dcc.Download` and a configurable output dir

Local: write to `./outputs/`, then `dcc.Download` streams the file to the
user's browser.

Deployed: write to the platform's allowed output dir (env var), then
`dcc.Download` does exactly the same thing. The user never sees the server's
filesystem in either case.

What we are **not** doing: writing files to a fixed path and telling the user
where to look. That works on a laptop and is unfixable on a server.

## Why `pyproject.toml` + `uv.lock` and not `requirements.txt`

`pyproject.toml` is the modern Python project metadata standard (PEP 621).
`uv.lock` records exact resolved versions of every transitive dependency.
Together they give us:

- Reproducible installs on any machine running `uv sync`.
- A single source of truth for both Stage 1 (`uv sync` in `setup.bat`) and
  Stage 2 (container build runs the same `uv sync`).
- No pip / virtualenv / requirements.txt drift.

## Why `core/` has zero Dash imports

If `cooper_jacob()` imports `dash` to read a callback context, the function
can no longer be tested without spinning up Dash, can't be called from a
script or notebook, and can't be re-used from a future toolbox. The cost of
keeping `core/` pure is zero — we just pass values in and return values out.

## What we're explicitly not doing in Stage 1

To be unambiguous:

- **No Dockerfile.** Adding one in Stage 2 will be ~20 lines and mechanical
  given the package layout.
- **No SSO.** The Stage 1 login is a thin form that authenticates directly
  to BCGW via `oracledb`. Stage 2 may replace it with platform SSO; the
  Flask-Session abstraction is the same either way.
- **No CI / CD.** Tests run locally via `uv run pytest`. A GitHub Actions
  workflow can be added later in 30 lines.
- **No multi-tenancy infrastructure.** Each user logs in with their own
  BCGW credentials; the connection pool is per-session. In Stage 2 the
  pool architecture is identical, the platform just hosts more sessions.

## What this means in practice for Stage 1 development

Habits to keep:

1. Before writing a path literal, ask: "could this be a config value?"
2. Before writing `print(...)`, ask: "should this be `logger.info`?"
3. Before storing something at module level, ask: "is this safe if 10 users
   share this Python process?"
4. Before importing `dash` in a non-`ui/` module, ask: "really?"

Habits to avoid:

1. Don't add `if __name__ == "__main__":` blocks to library modules. They
   indicate the module is doing too much.
2. Don't catch broad exceptions and swallow them. Log and re-raise, or let
   them propagate.
3. Don't write SQL outside `data_access/queries.py`.
4. Don't add a "TODO: refactor for deployment" comment. Either it's correct
   for both now and later, or it's wrong.

## What we kept from the legacy Excel — and what we changed

The legacy Excel tool (`iMapBCDistDrawdown_20241108.xlsx`) is the team's
current working tool. The new tool replaces it, but does not redesign
what's working. The Water Officer team reads the same chart, the same
summary table, and the same reassigned-aquifer-material classification
they're used to. Familiarity here is a feature.

**Kept verbatim, with citations to the Excel source:**

- The Cooper-Jacob equation form, including the `r → 0.1 m` fallback
  (`Impact!Q2`).
- The T/S lookup table by aquifer subtype (`AquiferProperty_DB`, Wei et al.
  2009).
- The 30% at-risk threshold (`Impact!V`, `InputValues!B30:E32` filter).
- The SAD nested-IF formula with `no NPL` / `no Well Depth` branches
  (`Impact!U2`).
- The reassigned aquifer material rule (`Impact!R2`, the bedrock-depth
  heuristic with `> 5 ft`).
- The pumping rate unit dropdown including all seven units, with L/s as
  default (`Lookup_DB!B3:I10`).
- The default pumping duration of 100 days (deck slide 5).
- The distance-drawdown chart layout: scatter, inverted Y, three series
  (Wells, Drawdown Curve, SAD bars), WTN labels (`InputValues` chart, deck
  slide 21).
- The at-risk wells summary table at the top of the results
  (`InputValues!B30`).

**Changed deliberately, with rationale:**

- *Eliminated the paste-and-drag workflow.* The Excel requires the user
  to paste an iMap CSV, identify the pumping well by row number, then
  drag formulas down to fill the right number of rows. We replace this
  with a click-to-place pumping well, automatic same-aquifer query, and
  vectorised computation across all wells in one pass.
- *Automatic single-aquifer filtering.* The Excel's deck (slide 19) tells
  the user to manually remove out-of-aquifer wells from the pasted list.
  We do this in SQL via `WHERE w.AQUIFER_ID = :pumping_well_aquifer_id`,
  with a UI toggle to disable it. Less work, fewer errors.
- *Direct BCGW connectivity.* No intermediate iMap CSV export. Always
  current data. (The legacy iMap field abbreviations are documented in
  `DATA_REFERENCE.md` section 12 for cross-reference only.)
- *Superposition-ready math.* `core/drawdown.py` accepts a list of pumping
  sources. The Excel handles only one. The UI exposes only one for v1
  (Q5 deferred), but adding multi-well in v2 is a UI change, not a math
  change.

**Ported from the legacy Excel (client-confirmed):**

- The `> 5 ft` bedrock-depth threshold in the reassigned-material rule.
  The client confirmed this rule is kept as-is for v1.
- SAD is computed unconfined-style for all wells. For confined and
  bedrock wells, this over-estimates SAD (deck slide 7). The UI flags
  these wells with a "manual review of driller's log recommended" note
  and exposes a per-well override. The client confirmed v1 keeps this
  manual-override approach. A more thorough v2 could pull top-of-aquifer
  elevations from BCGW for confined wells, but that's out of v1 scope.
