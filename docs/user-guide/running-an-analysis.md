---
title: Running an analysis
parent: User Guide
nav_order: 4
---

# Running an analysis

After signing in you land on the **setup page**. An analysis has three
parts: locate the proposed pumping well, choose its source aquifer, and
set the pumping parameters. Then click **Run Analysis**.

![Top of the setup page showing the locate-the-well input modes and the map]({{ site.baseurl }}/assets/img/setup-page-locate.png)

*The top of the setup page: choose how to locate the pumping well, then place it on the map.*

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

![Source-aquifer dropdown showing directly-overlapping aquifers first, nearby aquifers below with distance tags, and a manual-entry option at the bottom]({{ site.baseurl }}/assets/img/aquifer-picker.png)

*The source-aquifer picker after placing a pumping point.*

### Aquifer transmissivity (T) and storativity (S)

Once an aquifer is selected, the tool fills in **transmissivity (T)**
and **storativity (S)** from a lookup table keyed to the aquifer's
subtype. These two values drive the drawdown calculation and are
shown in a small panel directly under the picker, with the subtype
that produced them.

To use your own values, tick **Override default T / S** and edit the
T and S fields. The override applies to this run only; untick it to
restore the lookup defaults for the selected aquifer.

> **T** is transmissivity in m²/day; **S** is storativity
> (dimensionless). They describe how readily an aquifer transmits
> water and how much water it releases from storage — together they
> govern how the drawdown wave propagates outward from the pumping
> well. If the aquifer subtype has no reliable default (for example
> karstic limestone), the panel says so and you must enter T and S
> yourself.

### Manual entry

If you choose the "no mapped aquifer" option (offered for points the
Province has not mapped), the tool reveals a **material** dropdown —
*Unconsolidated* or *Bedrock* — and the T and S
fields become **mandatory** (there are no lookup defaults to fall
back on). The same-aquifer filter is not available in manual mode.
The results page shows an orange "manual entry" banner so the run
is clearly marked.

![Manual-entry mode with the orange banner, a material dropdown, and the required T and S input fields]({{ site.baseurl }}/assets/img/manual-entry-mode.png)

*Manual-entry mode: material dropdown and required T / S inputs.*

## 3. Set the pumping parameters

| Parameter | Notes |
|---|---|
| **Pumping rate (Q)** | A number plus a unit. Units: m³/d (default), m³/min, m³/s, m³/yr, L/min, L/s. |
| **Pumping duration** | In days. Default 90 days. Quick presets: 30 d, 90 d, 180 d, 1 year, 10 years. |
| **Buffer radius** | How far out to search for nearby wells. Default 1000 m. |
| **Same-aquifer filter** | Off by default. When on, the nearby-well list is narrowed to wells whose location falls inside the source aquifer polygon. Disabled in manual-entry mode. |

![Pumping parameters panel with the pumping-rate input and unit dropdown, the duration field with preset buttons, the buffer radius, and the same-aquifer filter toggle]({{ site.baseurl }}/assets/img/setup-page-parameters.png)

*The pumping parameters panel: Q with its unit dropdown, duration with quick presets, buffer radius, and the same-aquifer filter toggle.*

## 4. Run the analysis

Click **Run Analysis**. The tool validates your inputs, queries BCGW, and
opens the results in a **new browser tab**. Your setup tab stays as it
is, so you can adjust and re-run without losing an earlier results tab.

Continue to [Reading the results]({{ site.baseurl }}{% link user-guide/reading-results.md %}).
