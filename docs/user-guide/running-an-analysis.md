---
title: Running an analysis
parent: User Guide
nav_order: 4
---

# Running an analysis

After signing in you land on the **setup page**. An analysis has three
parts: locate the proposed pumping well, choose its source aquifer, and
set the pumping parameters. Then click **Run Analysis**.

## 1. Locate the proposed pumping well

Choose one of three input methods:

- **Click on the map** — switch to map-click mode and click the proposed
  well location. The map cursor becomes a crosshair in this mode.
- **Enter latitude / longitude** — type WGS84 coordinates. The map flies
  to the point you entered.
- **Search by well tag number (WTN)** — look up an existing registered
  well by its tag number; the tool places the point at that well and
  resolves its aquifer automatically.

### Map layers

The map offers several layers, chosen from the control in the top-right
corner:

- **Basemaps** — OpenStreetMap (default), ESRI World Topographic, or
  ESRI World Imagery (satellite).
- **Aquifers** — the BCGW aquifer polygons, shown translucent (on by
  default).
- **All BC wells** — every registered well; appears once you zoom in.
- **Water management districts and precincts** — administrative
  boundaries with on-screen labels.

## 2. Choose the source aquifer

Once the pumping point is placed, the tool looks up the aquifer polygons
at and near that location and lists them:

- **Directly overlapping** aquifers are listed first. If exactly one
  aquifer contains the point, it is selected automatically.
- **Nearby** aquifers — up to three within 1000 m — are listed below,
  tagged with their distance. This matters where a well sits just outside
  the aquifer it should really be associated with (common at
  re-delineated aquifer boundaries, or with stacked polygons).
- **No mapped aquifer** — if the point is not inside any aquifer, a
  "enter materials manually" option is offered.

### Manual entry

If you choose the manual option (no mapped aquifer at the location), the
tool reveals a **material** dropdown — *Unconsolidated (sand and gravel)*
or *Bedrock* — and requires you to enter the aquifer's transmissivity
(T) and storativity (S) yourself. The same-aquifer filter is not
available in manual mode. The results page shows an orange "manual
entry" banner so the run is clearly marked.

## 3. Set the pumping parameters

| Parameter | Notes |
|---|---|
| **Pumping rate (Q)** | A number plus a unit. Units: Imp GPM, L/min, L/s (default), m³/d, m³/min, m³/s, US GPM. |
| **Pumping duration** | In days. Default 90 days. Quick presets: 30 d, 90 d, 180 d, 1 year, 10 years. |
| **Buffer radius** | How far out to search for nearby wells. Default 1000 m. |
| **T and S** | Filled from the aquifer's default values. Tick the override box to enter your own. Required in manual-entry mode. |
| **Same-aquifer filter** | Off by default. When on, the nearby-well list is narrowed to wells whose location falls inside the source aquifer polygon. |

> **T and S** are transmissivity and storativity — the aquifer
> properties that drive the drawdown calculation. The tool fills them
> from a lookup table keyed to the aquifer subtype. If the subtype has no
> reliable default (for example karstic limestone), you must enter them
> yourself.

## 4. Run the analysis

Click **Run Analysis**. The tool validates your inputs, queries BCGW, and
opens the results in a **new browser tab**. Your setup tab stays as it
is, so you can adjust and re-run without losing an earlier results tab.

Continue to [Reading the results]({{ site.baseurl }}{% link user-guide/reading-results.md %}).
