# Groundwater Drawdown Tool — Installation Guide

This guide is for end users (Water Officers and support staff) installing the
tool on a Windows machine. **One download, two double-clicks.**

## What gets installed

The tool runs locally on your computer. It is not a website or a server.
First-time setup downloads:

- The tool itself (Python source + data files) — into your user folder.
- `uv` — a Python project manager (~30 MB), installed to your user folder.
- Python 3.13 — managed by `uv`, installed to your user folder.
- The tool's Python dependencies — installed into an isolated environment
  inside the tool's folder.

Default install location: `%USERPROFILE%\Tools\groundwater-drawdown-tool\`
(for example: `C:\Users\<your_idir>\Tools\groundwater-drawdown-tool\`).

Total disk usage: roughly 150 MB. Nothing is installed system-wide; nothing
requires administrator rights.

After first-time setup, the tool runs locally on your computer. The only
network connection it needs is to BCGW, for well and aquifer data — and
that requires the BC government network (see Prerequisites below).

## Prerequisites

- Windows 10 or Windows 11.
- An internet connection for first-time setup and for future updates.
- A personal BCGW account (Oracle username and password).
- **A connection to the BC government network to run an analysis** —
  either in a BC government office, or over **VPN** when working from
  home. The tool fetches well and aquifer data from BCGW
  (`bcgw.bcgov:1521`), so **sign-in and analysis will not work without
  it.** First-time setup and updates only need a normal internet
  connection, not the government network.

## Step 1 — Download `setup.bat`

Download this file:

**<https://github.com/bcgov/groundwater-drawdown-tool/releases/latest/download/setup.bat>**

Save it anywhere convenient (your Desktop or your Downloads folder is fine).
You only need this one file — `setup.bat` will fetch everything else.

## Step 2 — Run `setup.bat`

Double-click `setup.bat`.

A console window opens and the installer runs automatically:

1. Checks GitHub for the latest released version.
2. Downloads the tool package and extracts it to
   `%USERPROFILE%\Tools\groundwater-drawdown-tool\`.
3. Installs `uv` if it isn't already installed.
4. Uses `uv` to download Python 3.13 and create an isolated environment.
5. Installs the tool's Python dependencies.

This takes a few minutes the first time. When it finishes, the console shows
**"Setup complete."** and pauses.

**No editing any files. No administrator rights needed.**

## Step 3 — Run the tool

Open the install folder:

```
%USERPROFILE%\Tools\groundwater-drawdown-tool\
```

Double-click `run.bat`. Optionally, right-click it once and choose
"Send to → Desktop (create shortcut)" so you have it on your Desktop next
time.

A console window opens (leave it running — closing it stops the tool) and
the tool launches. After a few seconds, your default browser opens to
`http://localhost:8050` showing a sign-in page.

Enter your BCGW username and password. The tool checks them against BCGW
and, on success, brings you to the analysis page.

If your browser doesn't open automatically, open any browser and go to:
`http://localhost:8050`

## Updating to a new version

When a new release is published, **re-run the same `setup.bat` you
downloaded the first time** (or download a fresh copy from the URL above —
the URL always points to the latest version).

`setup.bat` detects your existing install, compares versions, and updates
the tool's files in place:

- If you're already on the latest version: it tells you and exits in under
  a second.
- If a newer version is available: it downloads it, refreshes the
  dependencies, and you're done in roughly 30 seconds.

The following are **preserved** across updates and never overwritten:

- `.env` — if you have one (most users don't).
- `outputs\` — any reports or CSVs you've exported.
- `logs\` — historical logs.
- `flask_session\` — your active sign-in session.

You do not need to delete your install folder, copy any files manually, or
worry about losing your data.

## About your password

- Your password is **never saved** on your computer by this tool. You enter
  it each time you launch the tool.
- If you want a faster sign-in, your browser (Chrome, Edge, etc.) can offer
  to save the password — that's between you and your browser. The tool
  itself stores nothing.
- When your BCGW password expires (typically every 3 months), just enter
  the new password the next time you sign in. There is nothing to update
  in the tool.

## Stopping the tool

Close the console window that `run.bat` opened, or press Ctrl+C inside it.
The browser tab will show a connection error after the tool stops — this
is normal.

## Troubleshooting

**`setup.bat` shows "execution policy" errors.**
Right-click `setup.bat` → Properties → check "Unblock" if it appears, then
click OK and try again.

**`setup.bat` says it can't reach GitHub.**
Your network may block `github.com` or `api.github.com`. Confirm you have
internet access, then contact IT if it still fails. The full list of
required hosts for setup:

- `api.github.com` and `github.com` (release lookup and download)
- `astral.sh` (uv installer)
- `objects.githubusercontent.com` (Python distributions, via uv)
- `pypi.org` and `files.pythonhosted.org` (Python packages)

**`setup.bat` fails to install Python or packages.**
Same hosts as above — `pypi.org` is the most common one blocked on
locked-down networks. Contact IT.

**Sign-in says "authentication failed" but my password is correct.**
First, confirm you can sign in to BCGW from another tool (e.g. SQL Developer)
to rule out a password issue. If that works but the drawdown tool still
fails: check that you're connected to the BC government network or VPN.
The tool needs to reach `bcgw.bcgov:1521`.

**Browser shows "This site can't be reached."**
The tool may not have finished starting yet — wait 10 seconds and refresh.
If it still doesn't load, check the console window for error messages.

**I see weird red text in the console.**
The first lines after launch are usually informational, not errors. Only
worry if the tool stops or the browser fails to load.

**I want to install somewhere other than `%USERPROFILE%\Tools\...`.**
The default location is recommended (no admin rights, no OneDrive sync
issues). If you need a different location, contact your project lead —
this is a developer-mode install, not the standard end-user path.

## Uninstalling

Delete the folder `%USERPROFILE%\Tools\groundwater-drawdown-tool\`. That's it.

`uv` itself remains installed in `%USERPROFILE%\.local\bin\` — if you also
want to remove `uv`, delete that folder. (It's harmless to leave; other
Python tools may use it.)

## Getting help

Contact: [project lead — fill in].
Include the contents of the console window if there's an error. (Do **not**
include your BCGW password, even if it appears in an error message — let
your project lead know it leaked instead.)
