"""Dynamic in-polygon labels for the water management overlays.

BC publishes no labelled WMS style for the water management district
and precinct boundaries. The boundaries themselves ship as committed,
pre-simplified GeoJSON (see ``basemaps.py``); this module turns that
geometry into map labels that:

- appear only when the matching overlay is toggled on (the page-level
  callback gates on the ``LayersControl`` ``overlays`` prop),
- sit *inside* the polygon, and
- re-anchor to the *visible* part of the polygon as the officer pans
  and zooms — so a label stays on screen even when zoomed deep inside
  one precinct, instead of being pinned to a fixed centroid that
  scrolls out of view.

The re-anchoring is a Sutherland-Hodgman clip of each polygon against
the current map viewport rectangle, with the label placed at the
area-weighted centroid of the clipped (visible) piece:

- whole polygon in view  -> clipped piece is the whole polygon, label
  sits at its natural centroid;
- zoomed into one corner -> clipped piece is that corner, label tracks
  it;
- polygon barely clipping the viewport edge -> clipped area falls
  below ``_MIN_VIEWPORT_COVERAGE`` and no label is drawn, which keeps
  the zoomed-out view uncluttered.

``clip_ring`` and ``polygon_area_centroid`` are pure geometry helpers
and are unit-tested directly.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import dash_leaflet as dl

logger = logging.getLogger(__name__)

# assets/ holds the committed boundary GeoJSON; this module lives at
# gwdrawdown/ui/components/, so the assets dir is two parents up.
_ASSETS_DIR: Final[Path] = Path(__file__).resolve().parents[1].parent / "assets"

# A polygon's clipped-visible area must reach this fraction of the
# viewport area to earn a label. Naturally declutters the zoomed-out
# view (only polygons occupying a real share of the screen are named)
# while still labelling whichever polygon you are zoomed inside — it
# fills the viewport, so its coverage approaches 1.0.
_MIN_VIEWPORT_COVERAGE: Final[float] = 0.02

# Point type alias: (longitude, latitude).
_Pt = tuple[float, float]


# --- Pure geometry -----------------------------------------------------------


def _clip_edge(
    poly: list[_Pt],
    inside: Callable[[_Pt], bool],
    intersect: Callable[[_Pt, _Pt], _Pt],
) -> list[_Pt]:
    """One Sutherland-Hodgman pass: clip ``poly`` against a half-plane."""
    if not poly:
        return []
    out: list[_Pt] = []
    prev = poly[-1]
    prev_in = inside(prev)
    for cur in poly:
        cur_in = inside(cur)
        if cur_in:
            if not prev_in:
                out.append(intersect(prev, cur))
            out.append(cur)
        elif prev_in:
            out.append(intersect(prev, cur))
        prev, prev_in = cur, cur_in
    return out


def _intersect_x(a: _Pt, b: _Pt, xc: float) -> _Pt:
    """Intersection of segment a-b with the vertical line x = xc."""
    ax, ay = a
    bx, by = b
    t = (xc - ax) / (bx - ax) if bx != ax else 0.0
    return (xc, ay + t * (by - ay))


def _intersect_y(a: _Pt, b: _Pt, yc: float) -> _Pt:
    """Intersection of segment a-b with the horizontal line y = yc."""
    ax, ay = a
    bx, by = b
    t = (yc - ay) / (by - ay) if by != ay else 0.0
    return (ax + t * (bx - ax), yc)


def clip_ring(
    ring: list[_Pt],
    west: float,
    south: float,
    east: float,
    north: float,
) -> list[_Pt]:
    """Clip a polygon ring to the axis-aligned rectangle [W,E] x [S,N].

    Sutherland-Hodgman against the four viewport edges. ``ring`` is a
    list of ``(lng, lat)`` points. Returns the clipped ring (>= 3
    points) or an empty list if nothing of the ring lies inside.
    """
    poly = _clip_edge(ring, lambda p: p[0] >= west, lambda a, b: _intersect_x(a, b, west))
    poly = _clip_edge(poly, lambda p: p[0] <= east, lambda a, b: _intersect_x(a, b, east))
    poly = _clip_edge(
        poly, lambda p: p[1] >= south, lambda a, b: _intersect_y(a, b, south)
    )
    poly = _clip_edge(
        poly, lambda p: p[1] <= north, lambda a, b: _intersect_y(a, b, north)
    )
    return poly if len(poly) >= 3 else []


def polygon_area_centroid(ring: list[_Pt]) -> tuple[float, float, float]:
    """Return ``(area, cx, cy)`` for a polygon ring via the shoelace formula.

    ``area`` is the absolute area; ``(cx, cy)`` is the area-weighted
    centroid. A degenerate (near-zero-area) ring falls back to the
    vertex mean so a label still gets *some* position.
    """
    n = len(ring)
    if n < 3:
        return (0.0, 0.0, 0.0)
    a2 = 0.0  # twice the signed area
    cx = 0.0
    cy = 0.0
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        a2 += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(a2) < 1e-14:
        return (
            0.0,
            sum(p[0] for p in ring) / n,
            sum(p[1] for p in ring) / n,
        )
    return (abs(a2) / 2.0, cx / (3.0 * a2), cy / (3.0 * a2))


# --- Boundary feature loading ------------------------------------------------


@dataclass
class _BoundaryFeature:
    """One named boundary polygon, prepared for fast label placement.

    ``rings`` holds exterior rings only — interior holes are dropped,
    as they don't materially affect where a label reads best. A
    MultiPolygon contributes one ring per part. ``bbox`` is the
    combined extent, used as a cheap viewport reject test.
    """

    name: str
    rings: list[list[_Pt]]
    bbox: tuple[float, float, float, float]  # minlng, minlat, maxlng, maxlat


def _exterior_rings(geometry: dict) -> list[list[_Pt]]:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if gtype == "Polygon":
        return [[(float(x), float(y)) for x, y in coords[0]]] if coords else []
    if gtype == "MultiPolygon":
        return [
            [(float(x), float(y)) for x, y in part[0]] for part in coords if part
        ]
    return []


def _load_features(filename: str) -> list[_BoundaryFeature]:
    """Load boundary features from a committed GeoJSON file in assets/."""
    path = _ASSETS_DIR / filename
    if not path.exists():
        logger.warning(
            "Boundary file %s not found; its overlay will render without labels. "
            "Run scripts/fetch_water_mgmt_boundaries.py to populate.",
            path,
        )
        return []
    with path.open(encoding="utf-8") as fp:
        collection = json.load(fp)

    features: list[_BoundaryFeature] = []
    for feat in collection.get("features", []):
        name = (feat.get("properties") or {}).get("name")
        rings = _exterior_rings(feat.get("geometry", {}))
        if not name or not rings:
            continue
        xs = [x for ring in rings for x, _ in ring]
        ys = [y for ring in rings for _, y in ring]
        features.append(
            _BoundaryFeature(
                name=str(name),
                rings=rings,
                bbox=(min(xs), min(ys), max(xs), max(ys)),
            )
        )
    return features


# Loaded once at import — a few hundred KB of geometry, immutable for
# the process lifetime.
_WMD_FEATURES: Final[list[_BoundaryFeature]] = _load_features("wmd_boundaries.geojson")
_WMP_FEATURES: Final[list[_BoundaryFeature]] = _load_features("wmp_boundaries.geojson")


# --- Label placement ---------------------------------------------------------


def _label_point(
    feature: _BoundaryFeature,
    west: float,
    south: float,
    east: float,
    north: float,
) -> _Pt | None:
    """Return the ``(lat, lng)`` label anchor for a feature, or ``None``.

    The anchor is the area-weighted centroid of the largest piece of
    the feature still visible in the viewport. ``None`` when the
    feature is off-screen or its visible sliver is too small to be
    worth a label.
    """
    viewport_area = (east - west) * (north - south)
    if viewport_area <= 0:
        return None
    minx, miny, maxx, maxy = feature.bbox
    if maxx < west or minx > east or maxy < south or miny > north:
        return None  # bbox entirely outside the viewport

    best_area = 0.0
    best_lat_lng: _Pt | None = None
    for ring in feature.rings:
        clipped = clip_ring(ring, west, south, east, north)
        if not clipped:
            continue
        area, cx, cy = polygon_area_centroid(clipped)
        if area > best_area:
            best_area = area
            best_lat_lng = (cy, cx)  # (lat, lng)

    if best_lat_lng is None or best_area < _MIN_VIEWPORT_COVERAGE * viewport_area:
        return None
    return best_lat_lng


def _label_marker(name: str, lat_lng: _Pt, css_class: str) -> dl.CircleMarker:
    """An effectively-invisible marker carrying a permanent name tooltip.

    The marker glyph itself is transparent and non-interactive (so it
    never intercepts a setup-map click meant to place the pumping
    point); the centred permanent tooltip is the visible label.
    """
    lat, lng = lat_lng
    return dl.CircleMarker(
        center=[lat, lng],
        radius=0.001,
        opacity=0,
        fillOpacity=0,
        interactive=False,
        children=[
            dl.Tooltip(name, permanent=True, direction="center", className=css_class),
        ],
    )


def build_boundary_label_markers(
    bounds: list | None,
    *,
    show_wmd: bool,
    show_wmp: bool,
) -> list[dl.CircleMarker]:
    """Build viewport-anchored label markers for the visible boundaries.

    ``bounds`` is the dash-leaflet Map ``bounds`` value as delivered on
    moveend: ``[[south, west], [north, east]]``. ``show_wmd`` /
    ``show_wmp`` gate each layer's labels on whether its overlay is
    currently toggled on. Returns the markers for a ``LayerGroup``.
    """
    if not bounds or not (show_wmd or show_wmp):
        return []
    try:
        (south, west), (north, east) = bounds
    except (ValueError, TypeError):
        return []

    markers: list[dl.CircleMarker] = []
    if show_wmd:
        for feature in _WMD_FEATURES:
            point = _label_point(feature, west, south, east, north)
            if point is not None:
                markers.append(_label_marker(feature.name, point, "wm-dyn-label-district"))
    if show_wmp:
        for feature in _WMP_FEATURES:
            point = _label_point(feature, west, south, east, north)
            if point is not None:
                markers.append(_label_marker(feature.name, point, "wm-dyn-label-precinct"))
    return markers
