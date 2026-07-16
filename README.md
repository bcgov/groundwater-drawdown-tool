# Groundwater Drawdown Tool

A screening tool for BC Water Authorizations staff to estimate drawdown
impacts on nearby wells from a proposed groundwater withdrawal. Uses the
Cooper-Jacob (1946) distance-drawdown solution against well and aquifer
data in BC's Geographic Warehouse (BCGW).

> **Screening tool.** Results are screening-level estimates, intended to
> be interpreted by, or in consultation with, a regional hydrogeologist
> or a Qualified Professional with expertise in hydrogeology. This tool
> is **not** a replacement for professional assessment.

The specifications are largely derived from the client's previous
solution — the Excel workbook developed by
D. van Everdingen and M. Leahey (2024).

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
- `spec/` — the developer specification and reference documents
  (`PROJECT_PLAN.md`, `DATA_REFERENCE.md`, `DESIGN_NOTES.md`). Developer-facing;
  not shipped to end users.
- `references/` — supporting material for the legacy Excel tool. Only
  `excel_chart_layout.md` is tracked; the client-confidential source files
  are kept locally and are git-ignored.
- `setup.bat`, `run.bat`, `_wait_and_open.ps1` — the end-user install and
  launch scripts.
- `version.txt` — the release version, and the source of truth for it.
- `CHANGELOG.md` — release notes, surfaced to users when the tool updates.
- `CLIENT_INSTALL.md` — the short install summary handed to end users.

## License

Code in this repository is licensed under the **Apache License, Version
2.0** — see [LICENSE](LICENSE).

Documentation (the `docs/` site source) is licensed under
**[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)**
(CC BY 4.0).

This follows the B.C. government's
[open source licensing guidance](https://github.com/bcgov/BC-Policy-Framework-For-GitHub/blob/master/BC-Open-Source-Development-Employee-Guide/Licenses.md):
Apache 2.0 for code, Creative Commons for documentation.

    Copyright 2026 Province of British Columbia

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
