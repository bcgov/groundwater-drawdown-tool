"""Parameterised SQL templates for the BCGW queries the tool needs.

This module is the **only** place SQL strings exist in the codebase
(working agreement, PROJECT_PLAN.md §8). Every query uses bind
variables; never f-string user input into SQL.

The queries match DATA_REFERENCE.md §6:

1. ``nearby_wells`` — find wells within a buffer (BC Albers), with an
   optional same-aquifer filter (DATA_REFERENCE.md §6.1).
2. ``aquifers_at_point`` — find aquifer polygons containing a point.
   Returns a list because aquifer polygons can stack vertically (e.g.
   bedrock under sand-and-gravel) and both layers are returned by
   ``SDO_CONTAINS`` for the same XY (DATA_REFERENCE.md §6.2).
3. ``aquifers_near_point`` — fallback for ``aquifers_at_point`` when no
   polygon contains the point: returns polygons within a search radius
   with their distance, sorted nearest first.
4. ``subtype_code_for_aquifer`` — map AQUIFER_ID to AQUIFER_SUBTYPE_CODE
   for the T/S lookup (DATA_REFERENCE.md §6.3).
5. ``well_by_tag`` — fetch one well by its provincial tag number
   (DATA_REFERENCE.md §6.4).
6. ``delineated_aquifer_ids`` — of a set of AQUIFER_IDs seen on well
   rows, which ones actually have a polygon in the aquifer view
   (DATA_REFERENCE.md §6.5).

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

from collections.abc import Iterable
from typing import Any

import oracledb

# --- SQL templates -----------------------------------------------------------

# Query 6.1: nearby wells. The same-aquifer filter is a SPATIAL test —
# wells whose point geometry intersects the source aquifer polygon —
# not a GWELLS attribute match on w.AQUIFER_ID. The attribute filter
# misses two cases the spatial filter catches: wells with a stale or
# erroneous GWELLS aquifer assignment, and wells correctly tagged
# today but inside a polygon BC has since re-delineated. Implemented
# as a correlated EXISTS subquery so a single SQL template still
# covers both filtered and unfiltered cases — pass aquifer_id=None
# to disable. SDO_ANYINTERACT is forgiving of polygon-edge cases at
# aquifer boundaries and behaves identically to SDO_INSIDE /
# SDO_CONTAINS for typical point-in-polygon queries. Reading
# SDO_POINT.X/.Y is faster than SDO_UTIL.TO_WKTGEOMETRY for these
# point features (DATA_REFERENCE.md §6.1).
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
  AND (:aquifer_id IS NULL OR EXISTS (
        SELECT 1
        FROM WHSE_WATER_MANAGEMENT.GW_AQUIFERS_CLASSIFICATION_SVW a
        WHERE a.AQUIFER_ID = :aquifer_id
          AND SDO_ANYINTERACT(a.GEOMETRY, w.GEOMETRY) = 'TRUE'
      ))
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

# Nearby-aquifer fallback. Returns polygons within ``radius_m`` of the
# point with their distance in metres, sorted nearest first. Only used
# by the setup page when ``aquifers_at_point`` returns no hits — wells
# that fall just outside the polygon they should be associated with
# are common at re-delineated boundaries, so the picker surfaces these
# as fallback choices rather than blocking the workflow.
# ``SDO_GEOM.SDO_DISTANCE`` returns 0 for touching/overlapping
# geometries; the 0.005-metre tolerance is the geometry simplification
# tolerance used during the distance computation, not a buffer.
_SQL_AQUIFERS_NEAR_POINT = """
SELECT a.AQUIFER_ID, a.NAME, a.SUBTYPE, a.MATERIAL,
       a.VULNERABILITY, a.PRODUCTIVITY, a.DEMAND,
       SDO_GEOM.SDO_DISTANCE(
           a.GEOMETRY,
           SDO_GEOMETRY(2001, 3005, SDO_POINT_TYPE(:x, :y, NULL), NULL, NULL),
           0.005
       ) AS DISTANCE_M
FROM WHSE_WATER_MANAGEMENT.GW_AQUIFERS_CLASSIFICATION_SVW a
WHERE SDO_WITHIN_DISTANCE(
        a.GEOMETRY,
        SDO_GEOMETRY(2001, 3005, SDO_POINT_TYPE(:x, :y, NULL), NULL, NULL),
        'distance=' || :radius_m || ' unit=meter'
      ) = 'TRUE'
ORDER BY DISTANCE_M
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

# Query 6.5: of a set of AQUIFER_IDs, which are formally delineated.
# GWELLS assigns some wells an AQUIFER_ID that has no polygon in
# GW_AQUIFERS_CLASSIFICATION_SVW (verified against live BCGW,
# 2026-08-06: AQUIFER_ID 1143 returns no rows there). Those IDs are
# not formally delineated aquifers, and the tool flags them in the
# per-well output. The rule is data-driven on purpose — a hardcoded
# ID list would rot the first time BC delineates one of them or adds
# another.
#
# ``{placeholders}`` is filled with generated bind-variable NAMES
# (``:id0, :id1, …``) only — never with values. The IDs themselves are
# still bound, so this does not breach the no-f-string-user-input rule.
_SQL_DELINEATED_AQUIFER_IDS = """
SELECT DISTINCT a.AQUIFER_ID
FROM WHSE_WATER_MANAGEMENT.GW_AQUIFERS_CLASSIFICATION_SVW a
WHERE a.AQUIFER_ID IN ({placeholders})
"""

# Oracle rejects an IN list longer than 1000 expressions (ORA-01795).
# A buffer typically spans well under 20 distinct aquifers so one pass
# is the norm, but chunking costs nothing and keeps a huge buffer from
# failing the whole run.
_MAX_IN_LIST = 500


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
        aquifer_id: Optional **spatial** same-aquifer filter. ``None``
            returns all wells in the buffer regardless of aquifer (UI
            toggle off — the default); a value restricts to wells whose
            point geometry lies inside the polygon for that
            ``AQUIFER_ID`` in ``GW_AQUIFERS_CLASSIFICATION_SVW``. This
            is intentionally a spatial check, not ``w.AQUIFER_ID =
            :aquifer_id``, so stale GWELLS aquifer assignments or
            re-delineated boundaries don't drop wells that physically
            sit inside the source aquifer today.

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
    setup page lets the user pick which one is the "source" aquifer for
    the same-aquifer filter on ``nearby_wells``.
    """
    with conn.cursor() as cur:
        cur.execute(_SQL_AQUIFERS_AT_POINT, {"x": x_albers, "y": y_albers})
        return _rows_as_dicts(cur)


def aquifers_near_point(
    conn: oracledb.Connection,
    *,
    x_albers: float,
    y_albers: float,
    radius_m: float,
) -> list[dict[str, Any]]:
    """Return aquifer polygons within ``radius_m`` of the BC Albers point.

    Fallback for ``aquifers_at_point`` when no polygon contains the
    click location. Used by the setup page to offer "nearby" choices
    when the user's well sits just outside a polygon (a common case at
    re-delineated aquifer boundaries) rather than blocking the
    workflow.

    Args:
        conn: Live Oracle connection.
        x_albers: Easting in EPSG:3005 metres.
        y_albers: Northing in EPSG:3005 metres.
        radius_m: Search radius in metres.

    Returns:
        A list of dicts, sorted ascending by ``DISTANCE_M`` (metres).
        Empty when no polygons fall within the radius — the caller is
        expected to fall back to the manual-entry option in that case.
        Boundary touches return ``DISTANCE_M = 0`` and may appear when
        the click was on a polygon edge that ``SDO_CONTAINS`` rejected.
    """
    with conn.cursor() as cur:
        cur.execute(
            _SQL_AQUIFERS_NEAR_POINT,
            {"x": x_albers, "y": y_albers, "radius_m": radius_m},
        )
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


def delineated_aquifer_ids(
    conn: oracledb.Connection,
    aquifer_ids: Iterable[int],
) -> set[int]:
    """Return the subset of ``aquifer_ids`` that have a mapped polygon.

    Implements DATA_REFERENCE.md §6.5. Callers pass the distinct
    ``AQUIFER_ID`` values seen on well rows; anything missing from the
    returned set has no row in ``GW_AQUIFERS_CLASSIFICATION_SVW`` and
    is therefore not a formally delineated aquifer.

    Args:
        conn: Live Oracle connection.
        aquifer_ids: Aquifer IDs to test. Duplicates and ``None`` are
            ignored; an empty input short-circuits with no query.

    Returns:
        The delineated IDs, as a set. Never larger than the input.
        The caller computes the undelineated set by difference —
        this function deliberately reports what *exists* rather than
        what is missing, so a partial result can never be mistaken
        for "these are undelineated".
    """
    ids = sorted({int(a) for a in aquifer_ids if a is not None})
    if not ids:
        return set()
    found: set[int] = set()
    with conn.cursor() as cur:
        for start in range(0, len(ids), _MAX_IN_LIST):
            chunk = ids[start : start + _MAX_IN_LIST]
            names = [f"id{i}" for i in range(len(chunk))]
            sql = _SQL_DELINEATED_AQUIFER_IDS.format(
                placeholders=", ".join(f":{n}" for n in names)
            )
            cur.execute(sql, dict(zip(names, chunk, strict=True)))
            found.update(int(row[0]) for row in cur.fetchall() if row[0] is not None)
    return found


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
