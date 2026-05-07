"""Parameterised SQL templates for the four BCGW queries the tool needs.

This module is the **only** place SQL strings exist in the codebase
(working agreement, PROJECT_PLAN.md §8). Every query uses bind
variables; never f-string user input into SQL.

The four queries match DATA_REFERENCE.md §6:

1. ``nearby_wells`` — find wells within a buffer (BC Albers), with an
   optional same-aquifer filter (DATA_REFERENCE.md §6.1).
2. ``aquifers_at_point`` — find aquifer polygons containing a point.
   Returns a list because aquifer polygons can stack vertically (e.g.
   bedrock under sand-and-gravel) and both layers are returned by
   ``SDO_CONTAINS`` for the same XY (DATA_REFERENCE.md §6.2).
3. ``subtype_code_for_aquifer`` — map AQUIFER_ID to AQUIFER_SUBTYPE_CODE
   for the T/S lookup (DATA_REFERENCE.md §6.3).
4. ``well_by_tag`` — fetch one well by its provincial tag number
   (DATA_REFERENCE.md §6.4).

All spatial parameters are BC Albers metres (EPSG:3005). The caller is
responsible for projecting WGS84 input via ``core.crs_utils.to_albers``
before calling any of these.

Returned values are raw rows: keys are uppercase column names, values
are whatever ``oracledb`` returns (floats for NUMBER, str for VARCHAR,
None for NULL). Unit conversion (feet→metres, US GPM→m³/day) happens
later in the pipeline via ``core.units``; aquifer-material classification
in ``core.well_classification``. This layer does no business logic.
"""

from __future__ import annotations

from typing import Any

import oracledb

# --- SQL templates -----------------------------------------------------------

# Query 6.1: nearby wells. The same-aquifer filter is implemented as a
# trailing OR so a single template covers both filtered and unfiltered
# cases — pass aquifer_id=None to disable. Reading SDO_POINT.X/.Y is
# faster than SDO_UTIL.TO_WKTGEOMETRY for these point features
# (DATA_REFERENCE.md §6.1).
_SQL_NEARBY_WELLS = """
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
  AND (:aquifer_id IS NULL OR w.AQUIFER_ID = :aquifer_id)
"""

# Query 6.2: containing aquifer polygons.
_SQL_AQUIFERS_AT_POINT = """
SELECT a.AQUIFER_ID, a.NAME, a.SUBTYPE, a.MATERIAL,
       a.VULNERABILITY, a.PRODUCTIVITY, a.DEMAND
FROM WHSE_WATER_MANAGEMENT.GW_AQUIFERS_CLASSIFICATION_SVW a
WHERE SDO_CONTAINS(
        a.GEOMETRY,
        SDO_GEOMETRY(2001, 3005, SDO_POINT_TYPE(:x, :y, NULL), NULL, NULL)
      ) = 'TRUE'
"""

# Query 6.3: subtype-code lookup.
_SQL_SUBTYPE_CODE = """
SELECT AQUIFER_SUBTYPE_CODE
FROM WHSE_WATER_MANAGEMENT.GW_AQUIFER_ATTRS
WHERE AQUIFER_ID = :aquifer_id
"""

# Query 6.4: single well by tag number. Returns the same well columns
# as query 6.1, so the row shape matches and downstream code can treat
# both queries uniformly.
_SQL_WELL_BY_TAG = """
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
WHERE w.WELL_TAG_NUMBER = :well_tag_number
"""


# --- Public functions --------------------------------------------------------


def _rows_as_dicts(cursor: oracledb.Cursor) -> list[dict[str, Any]]:
    """Convert a cursor's results to a list of column-name-keyed dicts.

    Column names come from ``cursor.description`` so a query change
    cannot silently drop a column from downstream output.
    """
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def nearby_wells(
    conn: oracledb.Connection,
    *,
    x_albers: float,
    y_albers: float,
    radius_m: float,
    aquifer_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return wells within ``radius_m`` of (x, y) in BC Albers.

    Implements DATA_REFERENCE.md §6.1.

    Args:
        conn: Live Oracle connection (typically from ``db.get_connection``).
        x_albers: Easting in EPSG:3005 metres.
        y_albers: Northing in EPSG:3005 metres.
        radius_m: Buffer radius in metres.
        aquifer_id: Optional same-aquifer filter. ``None`` returns all
            wells in the buffer regardless of aquifer (UI toggle off);
            a value restricts to wells whose ``AQUIFER_ID`` matches.

    Returns:
        A list of dicts; one per well. Distance from the pumping point
        is **not** included — the caller computes it Python-side from
        the returned ``X_ALBERS`` / ``Y_ALBERS`` (matches the legacy
        Excel's plain Euclidean distance).
    """
    with conn.cursor() as cur:
        cur.execute(
            _SQL_NEARBY_WELLS,
            {
                "x": x_albers,
                "y": y_albers,
                "radius_m": radius_m,
                "aquifer_id": aquifer_id,
            },
        )
        return _rows_as_dicts(cur)


def aquifers_at_point(
    conn: oracledb.Connection,
    *,
    x_albers: float,
    y_albers: float,
) -> list[dict[str, Any]]:
    """Return aquifer polygons containing the given BC Albers point.

    Implements DATA_REFERENCE.md §6.2. Returns a list because polygons
    can stack vertically (e.g. unconfined sand-and-gravel above
    fractured bedrock); both layers are returned for the same XY. The
    Phase 4 setup page lets the user pick which one is the "source"
    aquifer for the same-aquifer filter on ``nearby_wells``.
    """
    with conn.cursor() as cur:
        cur.execute(_SQL_AQUIFERS_AT_POINT, {"x": x_albers, "y": y_albers})
        return _rows_as_dicts(cur)


def subtype_code_for_aquifer(
    conn: oracledb.Connection,
    aquifer_id: int,
) -> str | None:
    """Return ``AQUIFER_SUBTYPE_CODE`` for an aquifer, or None.

    Implements DATA_REFERENCE.md §6.3. The returned code is the join
    key for the T/S lookup in ``core.aquifer_lookup``.

    Returns ``None`` when the aquifer has no row in ``GW_AQUIFER_ATTRS``
    or the code is NULL — the lookup layer treats both as "manual T/S
    entry required".
    """
    with conn.cursor() as cur:
        cur.execute(_SQL_SUBTYPE_CODE, {"aquifer_id": aquifer_id})
        row = cur.fetchone()
        if row is None:
            return None
        return row[0]


def well_by_tag(
    conn: oracledb.Connection,
    well_tag_number: int,
) -> dict[str, Any] | None:
    """Return one well by its provincial tag number, or None.

    Implements DATA_REFERENCE.md §6.4. Same row shape as
    ``nearby_wells`` so the setup page can pass either through the
    same downstream pipeline. Geometry is returned in BC Albers; the
    caller projects to WGS84 via ``core.crs_utils.to_wgs84`` for map
    placement.
    """
    with conn.cursor() as cur:
        cur.execute(_SQL_WELL_BY_TAG, {"well_tag_number": well_tag_number})
        rows = _rows_as_dicts(cur)
        if not rows:
            return None
        return rows[0]
