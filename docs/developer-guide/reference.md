---
title: Reference documents
parent: Developer Guide
nav_order: 4
---

# Reference documents

The deep specification and data documents live in the repository as
Markdown files. They are developer-facing and are not shipped to end
users. They remain in the repo (rather than being folded into this site)
because code comments reference them directly by filename and section.

| Document | What it covers |
|---|---|
| [`PROJECT_PLAN.md`](https://github.com/bcgov/groundwater-drawdown-tool/blob/main/PROJECT_PLAN.md) | The full specification: purpose, architecture, the build phases, the Cooper-Jacob and SAD formulas, and the resolved open questions. |
| [`DATA_REFERENCE.md`](https://github.com/bcgov/groundwater-drawdown-tool/blob/main/DATA_REFERENCE.md) | BCGW dataset column names, units, join keys, the T/S lookup table, and the SAD / reassigned-material logic. The source of truth for column names — do not guess them. |
| [`DESIGN_NOTES.md`](https://github.com/bcgov/groundwater-drawdown-tool/blob/main/DESIGN_NOTES.md) | The rationale behind Stage-1 design choices, including ones that exist to make a future Stage-2 deployment a packaging job rather than a rewrite. |
| [`references/excel_chart_layout.md`](https://github.com/bcgov/groundwater-drawdown-tool/blob/main/references/excel_chart_layout.md) | The distance-drawdown chart specification, matching the legacy Excel chart. |
| [`CHANGELOG.md`](https://github.com/bcgov/groundwater-drawdown-tool/blob/main/CHANGELOG.md) | Human-readable release notes, one section per version. |

## The legacy Excel tool

The tool's screening calculations are ported from a legacy Excel
workbook — *iMapBCDistDrawdown* (file
`iMapBCDistDrawdown_20241108.xlsx`), **developed by D. van Everdingen
and M. Leahey (2024).** That workbook is the source of truth for the
Cooper-Jacob implementation, the SAD formula, the
reassigned-aquifer-material rule, the chart layout, the unit list, the
default duration, and the 30% at-risk threshold. It also serves as the
validation harness — a known input set produces a known output that
`core/drawdown.py` is tested against.

A user-facing summary of the math and assumptions, including
references, is in the User Guide:
[Methods and assumptions]({% link user-guide/methods-and-assumptions.md %}).
