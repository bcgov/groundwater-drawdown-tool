---
title: Methods and assumptions
parent: User Guide
nav_order: 8
---

# Methods and assumptions

This page describes the calculations the tool performs and the
assumptions behind them. It is written for users who want to understand
where the numbers come from — no familiarity with the legacy Excel
tool or with hydrogeology software is needed.

> The tool's calculations are ported directly from the legacy Excel
> tool *iMapBCDistDrawdown* (file `iMapBCDistDrawdown_20241108.xlsx`),
> **developed by D. van Everdingen & M. Leahey (2024).** Cell
> references throughout (e.g. `Impact!Q2`, `Impact!U2`) point to the
> exact formula in that workbook.

## The Cooper-Jacob distance-drawdown formula

The tool estimates drawdown at any observation well using the
**Cooper-Jacob (1946) distance-drawdown approximation** to the Theis
(1935) well equation:

```
s(r, t) = (Q / 4πT) × ln(2.25 × T × t / (r² × S))
```

where

- *s* — drawdown at the observation well (metres)
- *Q* — pumping rate of the proposed well (m³/day)
- *T* — aquifer transmissivity (m²/day)
- *S* — aquifer storativity (dimensionless)
- *r* — straight-line distance from the pumping well (metres)
- *t* — duration of pumping (days)

The legacy Excel tool used the equivalent base-10 form

```
s = (2.303 × Q / 4πT) × log₁₀(2.25 × T × t / (S × r²))
```

The two forms produce identical numbers.

### `r → 0` fallback

If an observation point coincides with the pumping well (`r = 0`) the
formula is undefined. The tool substitutes `r = 0.1 m`, matching the
convention used in the legacy Excel tool (`Impact!Q2`), so the pumping
well itself returns a finite, large drawdown rather than an error.

### Cooper-Jacob validity check

Cooper-Jacob is an approximation that holds only when the
dimensionless parameter

```
u = r² × S / (4 × T × t)
```

is small (`u < 0.01`). When `u` exceeds the threshold for a given
distance and duration, the calculation is less reliable. The tool
still reports the drawdown number but flags the affected wells in the
per-well details table with a **light-purple row tint** — treat those
values as advisory.

## Default transmissivity and storativity (T, S)

Each aquifer in BCGW carries an aquifer subtype code (`1a`, `4b`,
`5b`, and so on). The tool looks the subtype up in a table of default
(T, S) values sourced from **Wei et al. (2009)** medians — the same
table used by the legacy Excel tool (`AquiferProperty_DB`). The values
can be overridden on the setup page if local data are available.

For karstic (subtype `5b`) and unknown (subtype `UNK`) aquifers, no
defaults are provided — the tool requires manual T and S entry.

## Safe Available Drawdown (SAD)

For each observation well the tool computes the **Safe Available
Drawdown**, a screening estimate of how much that well can withstand:

```
available drawdown = top − non-pumping water level + stickup

SAD = available drawdown × 0.7
```

where

- *top* — the relevant top depth in metres. For unconfined sand-and-
  gravel wells this is the bottom of the well. For confined and
  fractured-bedrock wells it should be the top of the aquifer or the
  uppermost major water-bearing fracture, read from the driller's log
  and entered via the per-well **"Top of fracture / aquifer / screen"**
  override.
- *non-pumping water level* — the static water level reported by GWELLS.
- *stickup* — the height of the well casing above the ground surface,
  if available.

The 0.7 (70%) safety factor matches the legacy Excel tool (`Impact!U2`).

### Confined and fractured-bedrock wells

For confined or bedrock wells the unconfined formula above
**over-estimates** SAD. The tool flags these wells with a *"manual
review of driller's log recommended"* note and exposes the per-well
"Top of fracture / aquifer / screen" override so you can supply the
correct top depth.

## At-risk classification

Each observation well receives a status based on the ratio of
predicted drawdown to SAD:

| Status | Meaning |
|---|---|
| **OK** | Predicted impact is below 30% of SAD. |
| **AT_RISK** | Predicted impact is 30% of SAD or more. |
| **INSUFFICIENT_DATA** | SAD could not be computed (missing water level or well depth). |
| **SUSPECT_DATA** | SAD was computed but is non-positive — the GWELLS baseline record is physically impossible and should be reviewed against the driller's log. |

The 30% threshold matches the legacy Excel tool's at-risk filter
(`Impact!V` and the `InputValues!B30` summary).

## Reassigned aquifer material

GWELLS reports an aquifer material for many wells, but the legacy
Excel tool computes a parallel **"reassigned material"** classification
using the bedrock depth on the driller's log (`Impact!R`):

- If bedrock depth is recorded and *(finished well depth − bedrock
  depth)* is greater than **5 feet**, classify the well as **Bedrock**.
- Otherwise classify as **Unconsolidated**.
- If neither is available, fall back to the GWELLS-reported material.

Both values appear in the per-well details table. The reassigned value
is the one used for downstream interpretation.

## Single-source pumping (v1)

The v1 user interface accepts a **single** proposed pumping well. The
underlying math already supports multiple pumping sources — their
contributions are summed linearly, which is mathematically free for
Cooper-Jacob (it is linear in Q). Multi-well analyses are a future
user-interface enhancement, not a new calculation.

## Assumptions and limitations

These are **screening-level** estimates. The tool assumes:

- A confined or semi-confined aquifer of **uniform transmissivity and
  storativity** over the area of interest.
- **Continuous pumping** at the chosen rate for the chosen duration.
- **No recharge** during the pumping period — a worst-case dry-season
  assumption.
- **Straight-line distance** to each observation well; no faults,
  barriers, or anisotropy are modelled.

The default 90-day pumping duration matches the dry-season convention
used by the legacy Excel tool and is appropriate for screening across
BC.

> **Always review.** Results are advisory and must be reviewed by a
> qualified hydrogeologist. The tool is not a replacement for
> professional assessment.

## References

- Cooper, H.H., and C.E. Jacob (1946). *A generalized graphical method
  for evaluating formation constants and summarizing well-field
  history.* Transactions, American Geophysical Union, 27(4), 526–534.
- Theis, C.V. (1935). *The relation between the lowering of the
  piezometric surface and the rate and duration of discharge of a well
  using ground-water storage.* Transactions, American Geophysical
  Union, 16(2), 519–524.
- Wei, M., Allen, D.M., Kohut, A.P., Grasby, S., Ronneseth, K., and
  Turner, B. (2009). *Understanding the types of aquifers in the
  Canadian Cordillera hydrogeologic region to better manage and
  protect groundwater.* Streamline Watershed Management Bulletin,
  13(1), 10–18.
- **Legacy Excel tool:** *iMapBCDistDrawdown* (file
  `iMapBCDistDrawdown_20241108.xlsx`), developed by **D. van Everdingen
  & M. Leahey, 2024.** This tool's screening calculations — the
  Cooper-Jacob form, the SAD formula, the reassigned-material rule,
  the chart layout, the unit list, the default duration, and the 30%
  at-risk threshold — are ported directly from that workbook.
