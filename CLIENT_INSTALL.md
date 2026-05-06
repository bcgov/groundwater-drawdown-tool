# Groundwater Drawdown Tool — Installation Guide

This guide is for end users (Water Officers and support staff) installing the
tool on a Windows machine. There are only two steps after you have the folder.

## What gets installed

The tool runs locally on your computer. It is not a website or a server.
First-time setup downloads:

- `uv` — the Python project manager (~30 MB), installed to your user folder.
- Python 3.13 — managed by `uv`, installed to your user folder.
- The tool's Python dependencies — installed into an isolated environment
  inside the tool's folder.

Total disk usage: roughly 150 MB. Nothing is installed system-wide; nothing
requires administrator rights.

After first-time setup, the tool runs offline (except for connecting to BCGW
to fetch well and aquifer data, which it does over your normal network).

## Prerequisites

- Windows 10 or Windows 11.
- An internet connection for first-time setup.
- A personal BCGW account (Oracle username and password).
- Network access to BCGW (usually via the BC government network or VPN).

## Step 1 — Get the tool

Place the tool folder somewhere stable on your machine, for example:

```
C:\Users\<your_idir>\Tools\groundwater-drawdown-tool\
```

Do not put it on a network drive or a synced folder (OneDrive, Dropbox).
Local disk only.

## Step 2 — First-time setup

Double-click `setup.bat`.

A console window opens and runs the following automatically:

1. Install `uv` if it isn't already installed.
2. Use `uv` to download Python 3.13 and create an isolated environment.
3. Install the tool's dependencies into that environment.

This takes a few minutes the first time. When it finishes, the console
shows "Setup complete." and pauses.

You only need to do this once per machine. **No editing any files.**

## Step 3 — Run the tool

Double-click `run.bat`.

A console window opens (leave it running — closing it stops the tool) and
the tool launches. After a few seconds, your default browser opens to
`http://localhost:8050` showing a sign-in page.

Enter your BCGW username and password. The tool checks them against BCGW
and, on success, brings you to the analysis page.

If your browser doesn't open automatically, open any browser and go to:
`http://localhost:8050`

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

**`setup.bat` fails to download Python or packages.**
Your network may block downloads from `astral.sh` or `pypi.org`. Contact
IT to confirm these hosts are accessible. The full list of required hosts:

- `astral.sh` (uv installer)
- `github.com` (Python distributions, via uv)
- `pypi.org` and `files.pythonhosted.org` (Python packages)

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

## Updating the tool

When you receive a new version of the tool, replace the entire folder
(or delete the `.venv` subfolder inside it and run `setup.bat` again).

> **Coming soon:** the tool will check a shared network folder for updates
> automatically each time you launch it. When that's available, you won't
> need to do anything — new versions will install themselves the next time
> you double-click `run.bat`. Until then, your project lead will let you
> know when a new version is ready.

## Getting help

Contact: [project lead — fill in].
Include the contents of the console window if there's an error. (Do **not**
include your BCGW password, even if it appears in an error message — let
your project lead know it leaked instead.)
