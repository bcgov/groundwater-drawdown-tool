---
title: Reading the results
parent: User Guide
nav_order: 5
---

# Reading the results

The results page opens in a new tab. From top to bottom:

## Run summary

A header block recording how the run was made: timestamp, signed-in BCGW
user, source aquifer, the T and S values used (tagged "(override)" if you
supplied them), pumping rate, duration, buffer radius, and filter state.
A run ID (a unique code) identifies this specific run; it also appears on
the PDF export.

If the run used manual entry, an orange banner appears here.

## Stat cards

A row of summary cards: total wells found, count flagged at-risk, count
with insufficient data, count outside the Cooper-Jacob validity range,
and the maximum predicted drawdown.

## At-risk wells summary table

The key artifact for a licence assessment file. It lists only the wells
where the predicted impact is at least 30% of that well's Safe Available
Drawdown (SAD), with columns: WTN, reassigned aquifer material, SAD (m),
impact (m), and impact as a percentage of SAD.

![At-risk wells summary table with WTN, reassigned material, SAD, impact, and impact-percent columns]({{ site.baseurl }}/assets/img/at-risk-table.png)
*The at-risk wells summary table.*

## Distance-drawdown chart

A chart of drawdown against distance from the pumping well, matching
the legacy Excel tool (*iMapBCDistDrawdown*, D. van Everdingen & M.
Leahey, 2024):

- **Red dots** — each nearby well, labelled with its WTN.
- **Black curve** — the Cooper-Jacob drawdown curve.
- **Orange bars** — each well's SAD, drawn down from its point.
- The Y axis is **inverted** — drawdown increases downward, the standard
  hydrogeology convention.

![Distance-drawdown chart with red WTN-labelled well points, a smooth black Cooper-Jacob curve, and vertical orange SAD bars, on an inverted Y axis]({{ site.baseurl }}/assets/img/distance-drawdown-chart.png)
*The distance-drawdown chart: wells (red), Cooper-Jacob curve (black), SAD bars (orange).*

## Map

A colour-coded map of the wells. Marker colour shows drawdown severity
and marker size shows the magnitude of impact. Clicking a well on the
map highlights it on the chart, and vice versa — the two views are
linked.

![Results map with observation wells colour-coded by drawdown severity and sized by predicted impact, around the proposed pumping well at the centre]({{ site.baseurl }}/assets/img/results-map.png)
*The results map. Marker colour shows drawdown severity; marker size shows impact magnitude.*

## Per-well details table

Every observation well, with the full set of attributes (WTN, intended
use, aquifer ID, depths, yield, water level, distance, predicted impact,
SAD, status, and more). The table is sortable, filterable, and
paginated.

### Editable columns and live recompute

Four columns can be edited directly in the table:

- **Non-pumping water level (NPL)**
- **Finished well depth**
- **Stickup** — BCGW does not record this; the table is the only place to
  supply it.
- **Top of fracture / aquifer / screen** — for confined or fractured
  bedrock wells, read from the driller's log.

When you edit a cell, the tool recomputes that well's SAD and status
immediately, without re-querying BCGW. Edited rows are tinted **light
yellow** and edited values carry a trailing `*`.

![Per-well details table with one row tinted light yellow to mark an edited value and one row tinted light purple to mark outside Cooper-Jacob validity]({{ site.baseurl }}/assets/img/per-well-table.png)
*The per-well details table. Yellow rows have edited values; purple rows fall outside the Cooper-Jacob validity range.*

## Status flags

Each well is classified:

| Status | Meaning |
|---|---|
| **OK** | Predicted impact is below 30% of the well's SAD. |
| **AT_RISK** | Predicted impact is 30% of SAD or more. |
| **INSUFFICIENT_DATA** | SAD could not be computed — a required value (water level or well depth) is missing. |
| **SUSPECT_DATA** | SAD was computed but is non-positive — the BCGW baseline record for that well looks physically impossible and should be checked against the driller's log. |

Rows with a **light-purple** tint fall outside the Cooper-Jacob validity
range for this distance and duration — the predicted drawdown for those
wells is less reliable and should be treated as advisory.

> **Always review.** These are screening-level estimates. Confined and
> fractured-bedrock wells, in particular, may need a manual review of the
> driller's log — the tool flags them with a note. Have a qualified
> hydrogeologist review the results.

Next: [Exporting results]({{ site.baseurl }}{% link user-guide/exports.md %}).
