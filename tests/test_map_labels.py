"""Tests for the boundary-label geometry helpers.

Covers the two pure functions that decide where a water management
district/precinct label is drawn: the Sutherland-Hodgman viewport clip
and the shoelace area-weighted centroid. Marker construction itself is
a thin dash-leaflet wrapper and is exercised only as a smoke test.
"""

from __future__ import annotations

import math

from gwdrawdown.ui.components.map_labels import (
    build_boundary_label_markers,
    clip_ring,
    polygon_area_centroid,
)

# A point is (lng, lat).


def test_centroid_of_unit_square() -> None:
    square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    area, cx, cy = polygon_area_centroid(square)
    assert math.isclose(area, 1.0, abs_tol=1e-9)
    assert math.isclose(cx, 0.5, abs_tol=1e-9)
    assert math.isclose(cy, 0.5, abs_tol=1e-9)


def test_centroid_is_orientation_independent() -> None:
    # Same square, clockwise winding — area is still positive.
    cw = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)]
    area, cx, cy = polygon_area_centroid(cw)
    assert math.isclose(area, 1.0, abs_tol=1e-9)
    assert math.isclose(cx, 0.5, abs_tol=1e-9)
    assert math.isclose(cy, 0.5, abs_tol=1e-9)


def test_centroid_degenerate_ring_falls_back_to_vertex_mean() -> None:
    # Collinear points — zero area; should not divide by zero.
    line = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
    area, cx, cy = polygon_area_centroid(line)
    assert area == 0.0
    assert math.isclose(cx, 1.0, abs_tol=1e-9)
    assert math.isclose(cy, 0.0, abs_tol=1e-9)


def test_clip_ring_fully_inside_is_unchanged_in_area() -> None:
    ring = [(2.0, 2.0), (3.0, 2.0), (3.0, 3.0), (2.0, 3.0)]
    clipped = clip_ring(ring, west=0.0, south=0.0, east=10.0, north=10.0)
    assert len(clipped) >= 3
    area, _, _ = polygon_area_centroid(clipped)
    assert math.isclose(area, 1.0, abs_tol=1e-9)


def test_clip_ring_large_polygon_is_cropped_to_viewport() -> None:
    # A 10x10 ring clipped to a 6x6 viewport -> visible area 36.
    ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    clipped = clip_ring(ring, west=2.0, south=2.0, east=8.0, north=8.0)
    area, cx, cy = polygon_area_centroid(clipped)
    assert math.isclose(area, 36.0, abs_tol=1e-9)
    # Centroid of the visible piece is the viewport centre.
    assert math.isclose(cx, 5.0, abs_tol=1e-9)
    assert math.isclose(cy, 5.0, abs_tol=1e-9)


def test_clip_ring_offscreen_polygon_returns_empty() -> None:
    ring = [(20.0, 20.0), (21.0, 20.0), (21.0, 21.0), (20.0, 21.0)]
    assert clip_ring(ring, west=0.0, south=0.0, east=10.0, north=10.0) == []


def test_clip_ring_corner_overlap_keeps_only_the_visible_corner() -> None:
    # Ring spans (5..15) on both axes; viewport is (0..10). Visible
    # piece is the 5x5 corner square (5..10, 5..10).
    ring = [(5.0, 5.0), (15.0, 5.0), (15.0, 15.0), (5.0, 15.0)]
    clipped = clip_ring(ring, west=0.0, south=0.0, east=10.0, north=10.0)
    area, cx, cy = polygon_area_centroid(clipped)
    assert math.isclose(area, 25.0, abs_tol=1e-9)
    assert math.isclose(cx, 7.5, abs_tol=1e-9)
    assert math.isclose(cy, 7.5, abs_tol=1e-9)


def test_build_markers_returns_empty_without_bounds() -> None:
    assert build_boundary_label_markers(None, show_wmd=True, show_wmp=True) == []


def test_build_markers_returns_empty_when_overlays_off() -> None:
    bounds = [[48.0, -124.0], [50.0, -122.0]]
    assert build_boundary_label_markers(bounds, show_wmd=False, show_wmp=False) == []


def test_build_markers_tolerates_malformed_bounds() -> None:
    assert build_boundary_label_markers([1, 2, 3], show_wmd=True, show_wmp=True) == []
