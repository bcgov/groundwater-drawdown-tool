"""Tests for core/crs_utils.py."""

from __future__ import annotations

import pytest

from gwdrawdown.core import crs_utils

# Reference point: Victoria, BC. The expected BC Albers values are
# rough — the precise value depends on the exact pyproj/PROJ datum
# grid in use. The strict correctness test is the round-trip below;
# this one is a coarse sanity check that the result lands in the
# right kilometre.
VICTORIA_WGS84 = (-123.3656, 48.4284)
VICTORIA_ALBERS_APPROX = (1_195_000.0, 383_000.0)


def test_to_albers_victoria_within_tolerance() -> None:
    x, y = crs_utils.to_albers(*VICTORIA_WGS84)
    assert x == pytest.approx(VICTORIA_ALBERS_APPROX[0], abs=2000.0)
    assert y == pytest.approx(VICTORIA_ALBERS_APPROX[1], abs=2000.0)


def test_to_wgs84_round_trips_victoria() -> None:
    x, y = crs_utils.to_albers(*VICTORIA_WGS84)
    lon, lat = crs_utils.to_wgs84(x, y)
    assert lon == pytest.approx(VICTORIA_WGS84[0], abs=1e-7)
    assert lat == pytest.approx(VICTORIA_WGS84[1], abs=1e-7)


@pytest.mark.parametrize(
    "lon_lat",
    [
        (-128.5, 54.0),  # Smithers area
        (-119.5, 49.5),  # Penticton area
        (-130.0, 56.0),  # NW BC
        (-117.7, 49.5),  # Kootenays
    ],
)
def test_round_trip_various_bc_points(lon_lat: tuple[float, float]) -> None:
    x, y = crs_utils.to_albers(*lon_lat)
    lon, lat = crs_utils.to_wgs84(x, y)
    assert lon == pytest.approx(lon_lat[0], abs=1e-7)
    assert lat == pytest.approx(lon_lat[1], abs=1e-7)


def test_always_xy_ordering() -> None:
    """Confirm (lon, lat) input order, not (lat, lon).

    If always_xy=False were ever set on the WGS84 transformer, swapping
    (lon, lat) would be silently accepted but produce nonsense outside
    of the EPSG:4326 valid range.
    """
    # A genuine BC point: easting > northing, easting around 1.2 million.
    x, y = crs_utils.to_albers(-123.0, 49.0)
    assert 1_000_000 < x < 1_500_000
    assert 300_000 < y < 700_000

    # If we accidentally swap (49.0, -123.0), the transform may still
    # succeed but lands far from BC. Confirm the result differs by orders
    # of magnitude — proves the order matters and we picked the right one.
    x_swapped, y_swapped = crs_utils.to_albers(49.0, -123.0)
    assert abs(x_swapped - x) > 100_000 or abs(y_swapped - y) > 100_000
