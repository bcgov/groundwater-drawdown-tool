# Excel Distance-Drawdown chart — layout reference

The results page in this tool replicates the chart from the legacy Excel
tool (`iMapBCDistDrawdown_20241108.xlsx`, sheet `InputValues`) and the
2024-11-04 client deck slide 21. This document captures the visual
specification so the Phase 4 implementation matches.

The Water Officer team's expected output is well-established — they read
this chart routinely. Deviating from it (e.g. flipping the Y-axis to grow
upward) is a usability mistake, not an improvement.

## Chart properties

- **Type:** Scatter (Plotly: `go.Scatter`).
- **Title:** "Distance-Drawdown".
- **X-axis:** "Distance [m]". Linear scale by default; the underlying data
  density is exponential because the Cooper-Jacob curve is generated on a
  log-spaced grid in the Excel (`Lookup_DB!N4:N43` is linear from −1 to
  log10(max_dist), and `O = 10^N`). For our chart, use a linear X-axis to
  match the slide-21 visual; a log-X toggle can be a Phase 5 nice-to-have.
- **Y-axis:** "Drawdown Impact [m]". **Inverted** — drawdown grows
  *downward*. This is hydrogeology convention: water level drops, so the
  curve drops. Plotly: `yaxis=dict(autorange='reversed')`.
- **Legend:** bottom centre or right. Three entries: "Wells", "Drawdown
  Curve", "SAD".

## Three series

### Series 1 — "Wells" (red dots, with WTN labels)

One scatter point per observation well. X = distance to pumping well in
metres. Y = predicted Cooper-Jacob drawdown at that distance.

- Marker: red filled circle, size ~10 px.
- Label: well tag number, positioned above the point. In Plotly,
  `mode='markers+text'`, `textposition='top center'`, `text=[wtn for wtn
  in wells]`.
- Tooltip: WTN, distance, drawdown, SAD, impact %, well status flag.
- The pumping well itself appears at `r = 0.1 m` (per the `r → 0.1`
  fallback) — render with a distinct symbol (e.g. red triangle) so users
  see it but don't confuse it with an observation.

When many wells crowd close together their labels overlap. The legacy
deck (slide 21) suggests rotating labels 270°. In Plotly, set
`textangle=-90` on the trace if more than ~10 wells are within the
visible distance range. Not blocking for v1 — v1 ships with horizontal
labels and we revisit if the team complains.

### Series 2 — "Drawdown Curve" (smooth black line)

The Cooper-Jacob theoretical curve, parameterised by the user's chosen
`Q`, `T`, `S`, `t`. Sampled at log-spaced X values from 0.1 m to ~110% of
the furthest observation well distance (the legacy Excel uses
`MAX(Impact!P) * 1.1`).

- Line: black, ~2 px, no markers.
- ~40 sample points along the X range (Excel uses 40 in `Lookup_DB`).
- Compute via `core/drawdown.py`'s `cooper_jacob` function — single
  source of truth for the math.
- Same Y-axis (inverted) as the well points, so the curve appears as a
  shape descending from high drawdown near r→0 and rising (visually) to
  near zero at large r.

### Series 3 — "SAD" (vertical orange bars)

For each observation well, a vertical line segment from the well's
plotted point down to the well's SAD value (in metres). Visualises "how
much headroom this well has before reaching its safe limit". When the
drawdown curve crosses or passes the bottom of an SAD bar, the well is
at risk.

- Implemented as one `go.Scatter` trace per well in `mode='lines'` with
  X repeated and Y from drawdown to SAD, OR (cleaner) one trace with
  `None` separators between segments.
- Colour: orange (#FFA500 or similar).
- Hide from legend duplication: set `showlegend=True` only on the first
  segment, `False` on the rest, with name "SAD".

Wells with `INSUFFICIENT_DATA` (no NPL or no Well Depth) have no SAD
bar. Wells outside Cooper-Jacob validity (`u > 0.01`) have neither a
plotted drawdown point nor an SAD bar — they appear in the per-well
table with the appropriate flag instead.

## Worked example (from deck slide 21, for sanity checking Phase 4)

Inputs:
- Pumping well WTN: 85199
- Aquifer 680, subtype 6b — Fractured crystalline bedrock
- T = 1.7 m²/d (override of generic 1.7), S = 0.00064
- Pumping well row override: `T = 208 m²/d, S = 0.0048`
  (in the screenshot these are user-entered overrides)
- Q = 3.97 L/s = 343.0 m³/d
- t = 180 d

Observation wells (sample): 23742, 96604, 32107, 53310, ...

Result (visual): two wells (23742 and 53310) flagged, both Bedrock,
SAD ~5.3 m and ~1.1 m, impact 52% and 56% respectively.

When implementing the chart in Phase 4, reproducing this case to
visually match the slide-21 image is the acceptance criterion.