---
title: Home
nav_order: 1
---

# Groundwater Drawdown Tool

A screening and decision-support tool for BC Water Authorizations staff to estimate drawdown impacts at nearby
wells from a proposed groundwater withdrawal, supporting licence
application reviews under the *Water Sustainability Act*.

The tool predicts how much groundwater levels in nearby registered wells
(from BC's GWELLS database) may decline due to a proposed pumping well at
a chosen location, using the Cooper-Jacob (1946) distance-drawdown
solution.

> **Screening tool.** Results are screening-level estimates intended to be
> reviewed by a qualified hydrogeologist. This tool is **not** a
> replacement for professional assessment.

## Who this is for

- **Water Officers and support staff** running the tool — start with the
  [User Guide]({{ site.baseurl }}{% link user-guide/index.md %}).
- **Developers** maintaining or extending the tool — see the
  [Developer Guide]({{ site.baseurl }}{% link developer-guide/index.md %}).

## What it does

- Place a proposed pumping well by map click, coordinates, or well tag
  number.
- Query nearby registered wells and aquifer polygons directly from the
  BC Geographic Warehouse (BCGW).
- Compute predicted drawdown at each nearby well, the Safe Available
  Drawdown (SAD) of each well, and an at-risk classification.
- Present results as summary tables, a distance-drawdown chart, and a
  colour-coded map.
- Export the run as CSV, KML, PDF, or a standalone interactive HTML map.

## Quick links

- [Install the tool]({{ site.baseurl }}{% link user-guide/installation.md %})
- [Run your first analysis]({{ site.baseurl }}{% link user-guide/running-an-analysis.md %})
- [Troubleshooting]({{ site.baseurl }}{% link user-guide/troubleshooting.md %})
