# Groundwater Drawdown Tool

A screening tool for BC Water Authorizations staff to estimate drawdown
impacts on nearby wells from a proposed groundwater withdrawal. Uses the
Cooper-Jacob (1946) distance-drawdown solution against well and aquifer
data in BC's Geographic Warehouse (BCGW).

The specifications are largely derived from the client's previous
solution, which relied on iMap and Excel-based tools.

## Documentation

Full documentation is published as a site:

**<https://bcgov.github.io/groundwater-drawdown-tool/>**

- **End users** (Water Officers) — the User Guide covers installation and
  use.
- **Developers** — the Developer Guide covers architecture, development
  setup, and releasing.

## Quick start (developers)

Requires [uv](https://docs.astral.sh/uv/) on Windows.

```powershell
# Install uv if needed (then open a new PowerShell window):
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# In the project directory:
uv sync

# Run the app (serves at http://localhost:8050):
uv run python -m gwdrawdown.app

# Run the tests:
uv run pytest
```

No `.env` file is needed — BCGW credentials are entered at runtime through
the login UI. Running an analysis requires the BC government network or
VPN. See the
[Developer Guide](https://bcgov.github.io/groundwater-drawdown-tool/developer-guide/)
for details.

## End-user install

End users install by downloading one file — `setup.bat` — from the latest
GitHub release:

<https://github.com/bcgov/groundwater-drawdown-tool/releases/latest/download/setup.bat>

Step-by-step instructions are in the
[User Guide](https://bcgov.github.io/groundwater-drawdown-tool/user-guide/installation/).

## Repository layout

- `src/gwdrawdown/` — the application package (`core/`, `data_access/`,
  `ui/`).
- `data/` — T/S lookup and unit-conversion tables.
- `tests/` — the pytest suite.
- `scripts/` — release and smoke-test scripts.
- `docs/` — the documentation site source (published via GitHub Pages).
- `PROJECT_PLAN.md`, `DATA_REFERENCE.md`, `DESIGN_NOTES.md` — the
  developer specification and reference documents.

## License

To be determined.
