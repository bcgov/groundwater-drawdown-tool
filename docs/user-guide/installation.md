---
title: Installation
parent: User Guide
nav_order: 1
---

# Installation

**One download, two double-clicks.** The tool installs into your own user
folder — nothing system-wide, and no administrator rights needed.

## What gets installed

The tool runs locally on your computer. It is not a website or a server.
First-time setup downloads:

- The tool itself (Python source and data files).
- [`uv`](https://docs.astral.sh/uv/) — a Python project manager (~30 MB).
- Python 3.13 — managed by `uv`.
- The tool's Python dependencies, in an isolated environment.

Default install location:

```
C:\Users\<your_idir>\Tools\groundwater-drawdown-tool\
```

Total disk usage is roughly 150 MB. After first-time setup, the tool runs
locally on your computer; the only network connection it needs is to
BCGW, for well and aquifer data (see [Prerequisites](#prerequisites)).

## Prerequisites

- Windows 10 or Windows 11.
- An internet connection for first-time setup and for future updates.
- A personal BCGW account (Oracle username and password).
- **A connection to the BC government network to run an analysis** —
  either in a BC government office, or over **VPN** when working from
  home. The tool fetches well and aquifer data from BCGW, so sign-in and
  analysis will not work without it. First-time setup and updates only
  need ordinary internet, not the government network.

## Step 1 — Download `setup.bat`

Download this one file:

[**setup.bat — latest release**](https://github.com/bcgov/groundwater-drawdown-tool/releases/latest/download/setup.bat)

Save it anywhere convenient — your Desktop or Downloads folder is fine.
`setup.bat` will fetch everything else.

## Step 2 — Run `setup.bat`

Double-click `setup.bat`. A console window opens and the installer runs
automatically:

1. Checks GitHub for the latest released version.
2. Downloads the tool package and extracts it to your user folder.
3. Installs `uv` if it isn't already installed.
4. Uses `uv` to download Python 3.13 and create an isolated environment.
5. Installs the tool's Python dependencies.

This takes a few minutes the first time. When it finishes, the console
shows **"Setup complete."** and pauses. No editing files, no
administrator rights.

## Step 3 — Run the tool

Open the install folder:

```
C:\Users\<your_idir>\Tools\groundwater-drawdown-tool\
```

Double-click `run.bat`. (Tip: right-click `run.bat` once and choose
**Send to → Desktop (create shortcut)** so it is easy to find next time.)

A console window opens — leave it running; closing it stops the tool.
After a few seconds your browser opens to `http://localhost:8050`. If it
does not open on its own, open any browser and go to that address.

Continue to [First run]({{ site.baseurl }}{% link user-guide/first-run.md %}).

## Updating to a new version

When a new release is published, **re-run the same `setup.bat`** (or
download a fresh copy from the link above — it always points to the
latest version).

`setup.bat` detects your existing install, compares versions, and updates
in place:

- Already on the latest version → it tells you and exits in about a
  second.
- A newer version is available → it downloads and refreshes everything in
  roughly 30 seconds.

These are **preserved** across updates and never overwritten:

- `outputs\` — reports and files you have exported.
- `logs\` — historical logs.
- `flask_session\` — your active sign-in session.
- `.env` — if you have one (most users do not).

You never need to delete your install folder or copy files manually.

## Uninstalling

Delete the folder `C:\Users\<your_idir>\Tools\groundwater-drawdown-tool\`.
That is all.

`uv` itself remains in `C:\Users\<your_idir>\.local\bin\`. It is harmless
to leave; delete that folder too if you want it gone.
