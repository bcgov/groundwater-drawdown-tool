# Data Reference

This document is the source of truth for column names, data types, units, and
relationships in the BCGW datasets used by this tool. **Do not guess**
column names — use what is documented here.

## 1. BCGW datasets used

All three are in the `WHSE_WATER_MANAGEMENT` schema.

| Object | What it is | Used for |
|---|---|---|
| `GW_WATER_WELLS_WRBC_SVW` | Spatial feature class of registered wells (GWELLS) | Locating nearby wells, reading static water level, depth, etc. |
| `GW_AQUIFERS_CLASSIFICATION_SVW` | Spatial feature class of aquifer polygons | Determining which aquifer a point falls within |
| `GW_AQUIFER_ATTRS` | Attribute table (non-spatial) | Mapping AQUIFER_ID → AQUIFER_SUBTYPE_CODE |

All spatial geometry is `SDO_GEOMETRY` (Oracle Spatial). Production projection
on BCGW is BC Albers (EPSG:3005).

## 2. Join keys

```
GW_AQUIFERS_CLASSIFICATION_SVW.AQUIFER_ID  ⇄  GW_AQUIFER_ATTRS.AQUIFER_ID
GW_WATER_WELLS_WRBC_SVW.AQUIFER_ID         ⇄  GW_AQUIFERS_CLASSIFICATION_SVW.AQUIFER_ID
```

A well belongs to at most one aquifer. An aquifer can contain many wells.

## 3. Columns we care about

Below are only the columns the tool actually uses. Many more exist; ignore
them in queries.

### 3.1 GW_WATER_WELLS_WRBC_SVW (wells)

| Column | Type | Unit | Notes |
|---|---|---|---|
| `WELL_TAG_NUMBER` | NUMBER(10) | — | Provincial well ID. Unique. User-facing search key. |
| `IDENTIFICATION_PLATE_NUMBER` | NUMBER(10) | — | Physical plate on regulated wells. Optional. |
| `WELL_STATUS` | VARCHAR2(300) | — | New, Abandoned, Alteration, Closure, Other. Filter to active in queries if appropriate. |
| `WELL_CLASS` | VARCHAR2(100) | — | Water Supply, Monitoring, Recharge, etc. Filter to Water Supply for impact assessment. |
| `INTENDED_WATER_USE` | VARCHAR2(100) | — | private domestic, irrigation, etc. |
| `LICENCE_STATUS` | VARCHAR2(300) | — | Licensed, Unlicensed, Historical. |
| `AQUIFER_ID` | NUMBER(10) | — | Join to aquifer classification. May be NULL. |
| `FINISHED_WELL_DEPTH` | NUMBER(8) | **feet** below ground level | Working depth of the well. May be NULL. |
| `TOTAL_DEPTH_DRILLED` | NUMBER(7) | **feet** below ground level | Drilled depth. May be NULL. |
| `BEDROCK_DEPTH` | NUMBER(8) | **feet** below ground level | May be NULL. |
| `YIELD` | NUMBER(8) | **US gallons per minute** | Driller's estimate. May be NULL. |
| `YIELD_ESTIMATION_DURATION` | NUMBER(9) | hours | Duration of yield test. |
| `STATIC_WATER_LEVEL` | NUMBER(8) | **feet** below top of casing | Pre-pumping water level. May be NULL. **Critical for at-risk evaluation.** |
| `DIAMETER` | NUMBER(8) | inches | Casing diameter. |
| `GROUND_ELEVATION` | NUMBER(10) | **feet above sea level** | Ground elevation at well. |
| `AQUIFER_MATERIAL` | VARCHAR2(100) | — | bedrock, unconsolidated, unknown. |
| `WELL_DETAILS_URL` | VARCHAR2(255) | — | Link to GWELLS page. Useful for results display. |
| `GEOMETRY` | SDO_GEOMETRY | — | Point in EPSG:3005. |

**Critical units rule:** depths and water levels are in **feet**, yield is in **US gallons per minute**.
The tool's math operates in SI (metres, m³/day). Convert in `core/units.py`,
nowhere else.

A well missing `STATIC_WATER_LEVEL` or `FINISHED_WELL_DEPTH` (or `TOTAL_DEPTH_DRILLED`)
cannot be evaluated for at-risk status — flag as `INSUFFICIENT_DATA`.

### 3.2 GW_AQUIFERS_CLASSIFICATION_SVW (aquifer polygons)

| Column | Type | Notes |
|---|---|---|
| `AQUIFER_ID` | NUMBER(10) | Aquifer Number, unique. e.g. 1100. |
| `NAME` | VARCHAR2(150) | Display name. |
| `LOCATION` | VARCHAR2(200) | Geographic context. |
| `MATERIAL` | VARCHAR2(100) | Sand and Gravel / Bedrock / etc. |
| `SUBTYPE` | VARCHAR2(200) | **Long description.** e.g. "Unconfined sand and gravel - large river system". This is *not* the join key for T/S — use `AQUIFER_SUBTYPE_CODE` from `GW_AQUIFER_ATTRS`. |
| `VULNERABILITY` | VARCHAR2(100) | Low / Moderate / High |
| `PRODUCTIVITY` | VARCHAR2(100) | Low / Moderate / High |
| `DEMAND` | VARCHAR2(100) | Low / Moderate / High |
| `AQUIFER_DETAILS_URL` | VARCHAR2(255) | Link to GWELLS aquifer summary. |
| `GEOMETRY` | SDO_GEOMETRY | Polygon in EPSG:3005. |

### 3.3 GW_AQUIFER_ATTRS (aquifer attribute table)

This table is not in the BC Data Catalogue documentation we have, but column
names from the sample CSV are known. Relevant columns:

| Column | Type | Notes |
|---|---|---|
| `AQUIFER_ID` | NUMBER | Join key. |
| `AQUIFER_SUBTYPE_CODE` | VARCHAR2 | **The join key for T/S lookup.** Values seen: `1a`, `1b`, `1c`, `2`, `3`, `4a`, `4b`, `4c`, `5a`, `5b`, `6a`, `6b`, `UNK`. |
| `AQUIFER_CLASSIFICATION` | VARCHAR2 | e.g. IIA, IIIA. Different from subtype code. Not used by the tool. |
| `AQUIFER_NAME` | VARCHAR2 | Possibly redundant with `NAME` from `_SVW`. |
| `AQUIFER_RANKING_VALUE` | NUMBER | Not used. |
| `SIZE_KM2` | NUMBER | Not used. |

`UNK` means subtype not assigned. Treat the same as a missing entry: requires
manual T/S input from the user.

## 4. T/S lookup table (sample, pending Q1 client confirmation)

Source: September 2024 client deck, slide 11. Typed verbatim from the screenshot.
Stored in `data/ts_lookup.csv` with columns
`subtype_code,subtype_description,T_m2_per_day,S_dimensionless,valid`.

| Code | Description | T (m²/day) | S | Valid |
|---|---|---|---|---|
| 1a | Unconfined sand and gravel - large river system | 4500 | 0.3 | yes |
| 1b | Unconfined sand and gravel aquifer - medium stream system | 1300 | 0.3 | yes |
| 1c | Unconfined sand and gravel aquifer - small stream system | 200 | 0.02 | yes |
| 2 | Unconfined sand and gravel - deltaic | 1049 | 0.02 | yes |
| 3 | Unconfined sand and gravel - alluvial or colluvial fan | 710 | 0.019 | yes |
| 4a | Unconfined sand and gravel - late glacial outwash | 690 | 0.02 | yes |
| 4b | Confined sand and gravel - glacial | 250 | 0.005 | yes |
| 4c | Confined sand and gravel - glacio-marine | 150 | 0.005 | yes |
| 5a | Fractured sedimentary rock | 4 | 0.00003 | yes |
| 5b | Karstic limestone | — | — | no (not valid) |
| 6a | Flat-lying to gently-dipping volcanic bedrock | 23 | 0.00064 | yes |
| 6b | Fractured crystalline bedrock | 1.7 | 0.00064 | yes |

When `valid` is `no`, `aquifer_lookup.py` returns a sentinel that the UI
handles by requiring manual T/S entry.

## 5. Coordinate reference systems

- User input (lat/lon from map click or manual entry): **WGS84, EPSG:4326**.
- All processing (buffers, distance calculations, Oracle spatial queries):
  **BC Albers, EPSG:3005**.
- All map rendering: WGS84 (Leaflet expects this).

The CRS conversion happens at exactly two points:
1. Inbound: lat/lon → BC Albers immediately on input (`crs_utils.to_albers`).
2. Outbound: BC Albers → lat/lon when assembling map markers (`crs_utils.to_wgs84`).

`pyproj.Transformer` should be created once at module load with `always_xy=True`
and reused, not constructed per call.

## 6. Required spatial query patterns

### 6.1 Find nearby wells within radius (BC Albers)

Two variants — with and without same-aquifer filtering. The setup page
exposes a toggle (default **off** per the confirmed Q12 answer) that
restricts results to wells whose geometry falls **spatially inside** the
source aquifer polygon. The filter is a spatial test
(`SDO_ANYINTERACT` against the polygon for the user-selected source
`AQUIFER_ID`), not an attribute equality on `w.AQUIFER_ID`. This
safeguards against erroneous GWELLS aquifer assignments and against
future re-delineation of aquifer boundaries — a well's recorded
`AQUIFER_ID` may be stale, but its geometry on the map is authoritative.

The `GW_WATER_WELLS_WRBC_SVW` features are stored as point geometries with
the `SDO_POINT` attribute populated. Reading `GEOMETRY.SDO_POINT.X` /
`.SDO_POINT.Y` is much faster than parsing WKT — avoid `SDO_UTIL.TO_WKTGEOMETRY`
unless we hit a row where the SDO_POINT is null.

```sql
-- Inputs: bind variables :x (Albers easting), :y (Albers northing),
--         :radius_m, optionally :aquifer_id (or NULL for no filter)
SELECT
    w.WELL_TAG_NUMBER,
    w.AQUIFER_ID,
    w.FINISHED_WELL_DEPTH,
    w.TOTAL_DEPTH_DRILLED,
    w.BEDROCK_DEPTH,
    w.STATIC_WATER_LEVEL,
    w.GROUND_ELEVATION,
    w.YIELD,
    w.YIELD_ESTIMATION_DURATION,
    w.WELL_STATUS,
    w.WELL_CLASS,
    w.INTENDED_WATER_USE,
    w.LICENCE_STATUS,
    w.WELL_DETAILS_URL,
    w.AQUIFER_MATERIAL,
    w.GEOMETRY.SDO_POINT.X AS X_ALBERS,
    w.GEOMETRY.SDO_POINT.Y AS Y_ALBERS
FROM WHSE_WATER_MANAGEMENT.GW_WATER_WELLS_WRBC_SVW w
WHERE SDO_WITHIN_DISTANCE(
    w.GEOMETRY,
    SDO_GEOMETRY(2001, 3005, SDO_POINT_TYPE(:x, :y, NULL), NULL, NULL),
    'distance=' || :radius_m || ' unit=meter'
) = 'TRUE'
  AND (:aquifer_id IS NULL OR EXISTS (
        SELECT 1
        FROM WHSE_WATER_MANAGEMENT.GW_AQUIFERS_CLASSIFICATION_SVW a
        WHERE a.AQUIFER_ID = :aquifer_id
          AND SDO_ANYINTERACT(a.GEOMETRY, w.GEOMETRY) = 'TRUE'
      ))
```

Bind parameters, never string-format. The spatial filter is implemented as
a correlated `EXISTS` subquery so a single SQL template handles both cases
(pass `NULL` to disable filtering). `SDO_ANYINTERACT` is the
relationship-agnostic predicate (point on the boundary still counts as
inside); for point-in-polygon it behaves identically to `SDO_INSIDE` /
`SDO_CONTAINS` while being more forgiving of polygon-edge cases at
aquifer boundaries. Distance from the pumping point is computed
Python-side using `(X_ALBERS, Y_ALBERS)` — plain Euclidean, matching
the legacy Excel.

### 6.2 Find containing aquifer for a point

```sql
SELECT AQUIFER_ID, NAME, SUBTYPE
FROM WHSE_WATER_MANAGEMENT.GW_AQUIFERS_CLASSIFICATION_SVW
WHERE SDO_CONTAINS(
    GEOMETRY,
    SDO_GEOMETRY(2001, 3005, SDO_POINT_TYPE(:x, :y, NULL), NULL, NULL)
) = 'TRUE'
```

### 6.3 Look up subtype code

```sql
SELECT AQUIFER_SUBTYPE_CODE
FROM WHSE_WATER_MANAGEMENT.GW_AQUIFER_ATTRS
WHERE AQUIFER_ID = :aquifer_id
```

### 6.4 Look up well by tag number

Standard equality query on `WELL_TAG_NUMBER`. Returns the same fields as
query 6.1 plus the geometry transformed back to WGS84 for map placement.

## 7. Sample data files

Files used to validate schema understanding and port behaviour from the
legacy tool:

- `sample_aquifers_attr_joined.csv` — sample rows from
  `GW_AQUIFERS_CLASSIFICATION_SVW` joined with `GW_AQUIFER_ATTRS` on
  `AQUIFER_ID`. Useful for verifying the join works and the subtype code
  values match the T/S lookup table.
- `iMapBCDistDrawdown_20241108.xlsx` — the legacy Excel tool currently
  used by Water Officers, developed by D. van Everdingen and M. Leahey
  (2024). Source of truth for SAD formula, unit list, default duration,
  30% threshold, chart layout, and reassigned-material rule. See
  section 13.

The sample CSV has duplicated columns (e.g. `DEMAND` and `DEMAND.1`,
`AQUIFER_ID` and `AQUIFER_ID.1`) because of the join. In real queries,
select explicit columns, don't use `SELECT *`.

## 8. Things explicitly **not** in the data

- No T/S table exists in BCGW. The `data/ts_lookup.csv` shipped with this
  tool comes from the legacy Excel `AquiferProperty_DB` sheet (Wei et al.
  2009 medians). Client-confirmed (Q1).
- No "available drawdown" or "SAD" column on wells. The tool computes
  these from `FINISHED_WELL_DEPTH`, `STATIC_WATER_LEVEL`, and `STICKUP`
  (in metres after unit conversion). See section 9.
- No flag column for "at-risk". The tool computes this from inputs and
  the configured threshold (default 30%, client-confirmed — Q3).
- No "top of fracture / aquifer / screen" column for wells in confined
  aquifers or fractured bedrock. This must be read from the driller's log
  by the Water Officer and entered as a per-well manual override. The UI
  exposes an editable field for this (matches the legacy Excel `Impact!S`).

## 9. Safe Available Drawdown (SAD) computation

SAD is the operational threshold the legacy Excel uses to flag wells.
Definition (matches `Impact!U` and deck slide 7):

```
SAD = available_drawdown × 0.7

available_drawdown depends on aquifer type:
  Unconfined sand and gravel:  well_bottom_m − NPL_m + stickup_m
  Confined aquifer:            top_of_aquifer_m − NPL_m + stickup_m
  Fractured bedrock:           top_of_uppermost_water_bearing_fracture_m
                               − NPL_m + stickup_m
```

Where:
- `well_bottom_m` = `FINISHED_WELL_DEPTH` (or `TOTAL_DEPTH_DRILLED` if
  finished is missing), converted from feet to metres.
- `NPL_m` = non-pumping water level = `STATIC_WATER_LEVEL`, converted from
  feet to metres. **Note:** GWELLS reports static water level "below top of
  casing", not "below ground". Hence the `+ stickup` correction.
- `stickup_m` = `STICKUP` (height of casing above ground), converted from
  inches to metres.

**Excel SAD formula, ported verbatim:**

```python
top = top_of_fracture_or_aquifer_or_screen_m  # user override if provided
if top is None:
    top = finished_well_depth_m  # unconfined fallback
if top is None:
    return SADResult(value=None, status="no Well Depth")
if non_pumping_water_level_m is None:
    return SADResult(value=None, status="no NPL")

stickup = stickup_m if stickup_m is not None else 0.0
available_drawdown = top - non_pumping_water_level_m + stickup
sad = available_drawdown * 0.7
```

For confined and bedrock wells, the unconfined-style fallback
**over-estimates SAD** (deck slide 7). Tag these wells in the results UI
with a "manual review of driller's log recommended" note; the Water
Officer enters the correct top via the per-well
`top_of_fracture_or_aquifer_or_screen_m` override. Client-confirmed: v1
keeps the manual-override approach rather than automating SAD for
confined cases.

## 10. Reassigned Aquifer Material rule

GWELLS reports `AQFR_MTRL` for many wells, but the legacy Excel computes a
parallel "reassigned" classification used to inform SAD interpretation
(`Impact!R`). Port verbatim:

```python
if bedrock_depth_m is not None:
    if (finished_well_depth_m - bedrock_depth_m) > 1.524:  # 5 ft in m
        return "Bedrock"
    else:
        return "Unconsolidated"
elif aquifer_material_from_gwells is not None:
    return aquifer_material_from_gwells
else:
    return "Unassigned"
```

**The 5-foot threshold is from the legacy Excel.** Client-confirmed: v1
keeps the `> 5 ft` rule.

Both the GWELLS-reported `AQFR_MTRL` and the reassigned classification are
shown in the results table; the reassigned value is the one used for
downstream interpretation.

## 11. Pumping rate unit conversions

The setup page accepts pumping rate in any of the units below. Default is
**m³/d**. All inputs are converted to **m³/day** before reaching
`core/drawdown.py`. Conversion factors are stored in
`data/unit_conversions.csv` so they're auditable without touching code.

| Unit | Multiplier to m³/day |
|---|---|
| L/min | 1.44 |
| L/s | 86.4 |
| m³/d | 1.0 |
| m³/min | 1440.0 |
| m³/s | 86400.0 |
| m³/yr | 0.00273785 |

The legacy Excel dropdown also included Imp GPM and US GPM, but the
current tool uses a curated subset of those units. BCGW well yield is still
handled separately in US GPM when converting the `YIELD` field to
SI for drawdown calculations.
(Imperial gallon = 4.54609 L; US gallon = 3.785412 L; conversion factors
derived in legacy Excel `Lookup_DB!B4:I10`.)

## 12. iMap export field abbreviations (for context)

The legacy workflow exports wells from iMapBC as a CSV pasted into the
Excel `DistanceToWell` sheet. The CSV uses abbreviated column names
different from the BCGW column names this tool queries directly. They're
listed here so the team understands the legacy schema if they ever need
to reconcile a result against an old Excel run.

| iMap CSV column | BCGW column | Notes |
|---|---|---|
| `WELL_TAG` | `WELL_TAG_NUMBER` | |
| `ID_PLATE` | `IDENTIFICATION_PLATE_NUMBER` | |
| `INTEND_USE` | `INTENDED_WATER_USE` | |
| `LIC_STATUS` | `LICENCE_STATUS` | |
| `AQUIFER_ID` | `AQUIFER_ID` | same |
| `FNSH_DEPTH` | `FINISHED_WELL_DEPTH` | feet (both) |
| `TTL_DEPTH` | `TOTAL_DEPTH_DRILLED` | feet (both) |
| `BED_DEPTH` | `BEDROCK_DEPTH` | feet (both) |
| `YIELD` | `YIELD` | US GPM (both) |
| `STATIC_LVL` | `STATIC_WATER_LEVEL` | feet below top of casing (both) |
| `STICKUP` | (no equivalent column name; need confirmation) | inches |
| `GRND_ELEV` | `GROUND_ELEVATION` | feet above sea level (both) |
| `AQFR_MTRL` | `AQUIFER_MATERIAL` | |
| `WELL_URL` | `WELL_DETAILS_URL` | |
| `X_COORDINATE` | `GEOMETRY.SDO_POINT.X` | BC Albers |
| `Y_COORDINATE` | `GEOMETRY.SDO_POINT.Y` | BC Albers |

The tool does **not** import iMap CSVs — it queries BCGW directly. This
table exists only for cross-reference.

## 13. Legacy Excel reference

The legacy tool is `iMapBCDistDrawdown_20241108.xlsx`. Key sheets and the
artefacts ported into this codebase:

| Excel artefact | Ported to |
|---|---|
| `Impact!Q` (Cooper-Jacob formula with `r=0.1` fallback) | `core/drawdown.py` |
| `Impact!U` (SAD nested-IF formula) | `core/sad.py` |
| `Impact!R` (reassigned aquifer material rule) | `core/well_classification.py` |
| `Impact!V` (impact / SAD ratio) and 30% threshold | `core/flagging.py` |
| `InputValues!B30:E32` (at-risk summary FILTER) | results page summary table |
| `AquiferProperty_DB` (T/S by subtype) | `data/ts_lookup.csv` |
| `Lookup_DB!B3:I10` (unit conversions) | `data/unit_conversions.csv` |
| Distance-Drawdown chart on `InputValues` | results page chart, see `references/excel_chart_layout.md` |

The full 100% match between this tool's output and the Excel for a known
input set is the validation gate before Phase 4 acceptance.
