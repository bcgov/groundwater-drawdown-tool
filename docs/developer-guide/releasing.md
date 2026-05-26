---
title: Releasing
parent: Developer Guide
nav_order: 3
---

# Releasing

End users install and update the tool by downloading a single `setup.bat`
from the latest GitHub release. Publishing a release is a manual,
one-developer workflow driven by `scripts/publish_release.ps1`.

## One-time prerequisites

On the developer's machine:

```powershell
winget install GitHub.cli
gh auth login    # authenticate against github.com/bcgov/groundwater-drawdown-tool
```

## Cutting a release

1. **Bump `version.txt`** (for example `0.4.0` → `0.5.0`).
2. **Update `CHANGELOG.md`** — move the relevant entries from
   `[Unreleased]` into a new versioned section
   `## [0.5.0] — YYYY-MM-DD`. The publish script extracts this section as
   the GitHub release notes.
3. **Commit** those two changes on `main` and push.
4. From the repo root, run:

   ```powershell
   .\scripts\publish_release.ps1
   ```

   The script verifies the working tree is clean and on `main`, confirms
   the version tag does not already exist, runs `uv run pytest`, builds
   `groundwater-drawdown-tool.zip`, tags `v<version>`, pushes the tag,
   and creates the GitHub release with `setup.bat` and the zip as assets.

5. Verify the release page:
   <https://github.com/bcgov/groundwater-drawdown-tool/releases>

By default the release is published as a regular release flagged
`--latest` — that is what makes `releases/latest/download/setup.bat`
resolve to it (the canonical install URL the auto-updater uses).

Add `-Draft` to publish a draft release for review:

```powershell
.\scripts\publish_release.ps1 -Draft
```

Add `-Prerelease` to publish as a pre-release (excluded from
`releases/latest`):

```powershell
.\scripts\publish_release.ps1 -Prerelease
```

A `-SkipTests` flag exists for emergencies; its use is discouraged.

## What ships in the release zip

The zip is built from an explicit allow-list in `publish_release.ps1`. It
contains the tool itself — `src/`, `data/`, `pyproject.toml`, `uv.lock`,
`.python-version`, `setup.bat`, `run.bat`, `_wait_and_open.ps1`,
`version.txt` — plus `CHANGELOG.md`, `README.md`, `CLIENT_INSTALL.md`,
and `references/excel_chart_layout.md`.

Developer-only documents (`PROJECT_PLAN.md`, `DATA_REFERENCE.md`,
`DESIGN_NOTES.md`) and the `docs/` site sources are **not** shipped — they
stay in the repository for developers.

## How updates reach users

- **New users** download `setup.bat` from the stable latest-release URL.
- **Existing users** re-run the same `setup.bat`; it detects the install,
  compares versions, and updates in place. User data (`outputs/`,
  `logs/`, `flask_session/`, `.env`) is preserved because those paths are
  never in the release zip.

The full distribution design — release layout, install/update modes,
failure modes — is in `PROJECT_PLAN.md` §6.
