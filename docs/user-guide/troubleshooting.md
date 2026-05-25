---
title: Troubleshooting
parent: User Guide
nav_order: 7
---

# Troubleshooting

## `setup.bat` shows "execution policy" errors

Right-click `setup.bat` → **Properties** → tick **Unblock** if it
appears, click **OK**, and try again.

## `setup.bat` says it can't reach GitHub

Your network may block `github.com` or `api.github.com`. Confirm you have
internet access, then contact IT if it still fails. The hosts setup
needs:

- `api.github.com` and `github.com` — release lookup and download
- `astral.sh` — the `uv` installer
- `objects.githubusercontent.com` — Python distributions, via `uv`
- `pypi.org` and `files.pythonhosted.org` — Python packages

## `setup.bat` fails to install Python or packages

Same hosts as above — `pypi.org` is the one most often blocked on
locked-down networks. Contact IT.

## Sign-in fails with a connection or network error

The tool cannot reach BCGW. Check that you are connected to the **BC
government network** — in a government office, or over **VPN** if you are
working from home. The tool needs to reach `bcgw.bcgov:1521`.

A quick way to confirm the network path, from PowerShell:

```powershell
Test-NetConnection -ComputerName bcgw.bcgov -Port 1521
```

Look for `TcpTestSucceeded : True`. If it says `False`, you are not on a
network that can reach BCGW.

## Sign-in says "authentication failed" but my password is correct

First confirm you can sign in to BCGW from another tool (for example
ArcGIS Pro or SQL Developer) to rule out a password problem. If that works but the
drawdown tool still fails, re-check the network/VPN connection as above.

Remember that BCGW passwords expire periodically — if yours just expired,
sign in with the new one.

## Browser shows "This site can't be reached"

The tool may not have finished starting — wait about 10 seconds and
refresh `http://localhost:8050`. If it still does not load, check the
`run.bat` console window for error messages.

## I see red text in the console window

The first lines after launch are usually informational, not errors. Only
worry if the tool stops or the browser fails to load.

## The tool stopped working

Make sure the `run.bat` console window is still open — closing it stops
the tool. Re-run `run.bat` to start it again.

## An analysis returns no nearby wells

Check the buffer radius on the setup page — a small radius in a sparsely
drilled area may genuinely contain no registered wells. Try a larger
radius. Also confirm the pumping point is where you intended.

## Getting more help

Contact your project lead. Include the contents of the `run.bat` console
window if there is an error — but **do not** include your BCGW password,
even if it appears in an error message. If a password has been exposed,
tell your project lead so it can be changed.
