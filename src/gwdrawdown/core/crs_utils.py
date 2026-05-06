"""Coordinate reference system conversions.

The tool moves between two CRSs:

- **WGS84 (EPSG:4326)** — user input from the map click or manual lat/lon
  entry, and map rendering (Leaflet expects WGS84).
- **BC Albers (EPSG:3005)** — all spatial processing: distance buffers,
  Euclidean well-to-well distance, Oracle SDO_GEOMETRY parameters.

Conversion happens at exactly two points (DATA_REFERENCE.md §5):

1. Inbound: lat/lon → BC Albers immediately on input.
2. Outbound: BC Albers → lat/lon when assembling map markers.

Transformer instances are constructed once at module load with
``always_xy=True`` and reused. Constructing a `Transformer` per call
costs measurable time and is not safe inside tight loops.
"""

from __future__ import annotations

from typing import Final

from pyproj import Transformer

WGS84_EPSG: Final[int] = 4326
BC_ALBERS_EPSG: Final[int] = 3005

# always_xy=True forces (longitude, latitude) / (easting, northing) order
# for both inputs and outputs, regardless of axis-order metadata in the
# CRS definition. Without it, EPSG:4326 returns (lat, lon), which is the
# leading source of CRS bugs.
_TO_ALBERS: Final[Transformer] = Transformer.from_crs(
    WGS84_EPSG, BC_ALBERS_EPSG, always_xy=True
)
_TO_WGS84: Final[Transformer] = Transformer.from_crs(
    BC_ALBERS_EPSG, WGS84_EPSG, always_xy=True
)


def to_albers(lon: float, lat: float) -> tuple[float, float]:
    """Convert WGS84 (lon, lat) in degrees to BC Albers (x, y) in metres."""
    x, y = _TO_ALBERS.transform(lon, lat)
    return float(x), float(y)


def to_wgs84(x: float, y: float) -> tuple[float, float]:
    """Convert BC Albers (x, y) in metres to WGS84 (lon, lat) in degrees."""
    lon, lat = _TO_WGS84.transform(x, y)
    return float(lon), float(lat)
