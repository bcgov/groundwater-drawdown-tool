---
title: Developer Guide
nav_order: 3
has_children: true
---

# Developer Guide

For developers maintaining or extending the Groundwater Drawdown Tool.

The tool is a Python [Dash](https://dash.plotly.com/) application. Stage 1
runs locally on a user's Windows machine and connects to BC's Oracle
spatial database (BCGW). It is built so that a future Stage 2 (deployment
to a server) is mostly packaging work, not a rewrite.

## Pages in this guide

1. [Architecture]({% link developer-guide/architecture.md %}) — the layer
   model and module responsibilities.
2. [Development setup]({% link developer-guide/development-setup.md %}) —
   getting a working environment with `uv`.
3. [Releasing]({% link developer-guide/releasing.md %}) — cutting a
   GitHub release that end users install from.
4. [Reference documents]({% link developer-guide/reference.md %}) — the
   in-repository specification and data documents.

## Technology

- **Python 3.13**, pinned via `.python-version`.
- **[uv](https://docs.astral.sh/uv/)** for environment, dependency, and
  interpreter management.
- **Dash** (with `dash-leaflet` and `plotly`) for the UI.
- **oracledb** (thin mode) for the BCGW Oracle connection.
- **pyproj** for coordinate transforms, **pandas** for tabular data.
- **pytest** for the test suite.
