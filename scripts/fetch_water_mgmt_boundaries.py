"""One-time fetcher for water management district / precinct boundaries.

Pulls the WMD and WMP polygons from BC's public WFS, simplifies the
geometry, rounds coordinates, and writes compact GeoJSON
FeatureCollections into the app's assets directory.

Why simplify: the full survey-resolution geometry is ~24 MB across the
two layers (~900k vertices) — far more detail than a screening map
needs. A Douglas-Peucker pass at a tolerance invisible at the zoom
levels these overlays display (9-13) collapses that by ~93%, to
roughly 1.4 MB combined. The running app loads the committed GeoJSON,
renders the boundaries as client-side vector overlays, and uses them
for the map-centre district/precinct caption — no runtime BC
dependency.

Re-run this script when BC publishes a boundary update. These
boundaries are regulation-derived and change every several years, so
that is rare.

Requires shapely (a dev-only dependency) for geometry simplification.

Usage::

    uv run python scripts/fetch_water_mgmt_boundaries.py

Outputs (overwritten on each run):
    src/gwdrawdown/assets/wmd_boundaries.geojson   ~26 features
    src/gwdrawdown/assets/wmp_boundaries.geojson   ~136 features
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from shapely.geometry import mapping, shape

logger = logging.getLogger(__name__)

_BASE = "https://openmaps.gov.bc.ca/geo/pub"

# Douglas-Peucker tolerance in degrees (~150-220 m at BC latitudes).
# Visually lossless at zoom 9-13 where these overlays render; drops
# the raw vertex count by ~93%.
_SIMPLIFY_TOLERANCE = 0.002

# Coordinate decimal places kept in the output. 5 dp is ~1 m of
# precision — far finer than the simplified geometry itself.
_COORD_PRECISION = 5

_LAYERS: list[dict[str, str]] = [
    {
        "typename": "WHSE_ADMIN_BOUNDARIES.LWADM_WATMGMT_DIST_AREA_SVW",
        "name_field": "DISTRICT_NAME",
        "output": "src/gwdrawdown/assets/wmd_boundaries.geojson",
    },
    {
        "typename": "WHSE_ADMIN_BOUNDARIES.LWADM_WATMGMT_PREC_AREA_SVW",
        "name_field": "PRECINCT_NAME",
        "output": "src/gwdrawdown/assets/wmp_boundaries.geojson",
    },
]


def _fetch(typename: str) -> dict[str, Any]:
    """Pull every feature in the named WFS layer as GeoJSON (EPSG:4326)."""
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": f"pub:{typename}",
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "propertyName": "*",
    }
    url = f"{_BASE}/{typename}/ows?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.load(r)


def _round_coords(obj: Any) -> Any:
    """Recursively round coordinate floats to ``_COORD_PRECISION`` places.

    ``shapely.geometry.mapping`` returns coordinates as nested tuples;
    this also normalises them to lists for compact JSON output.
    """
    if isinstance(obj, float):
        return round(obj, _COORD_PRECISION)
    if isinstance(obj, (list, tuple)):
        return [_round_coords(x) for x in obj]
    return obj


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    repo_root = Path(__file__).resolve().parent.parent
    for layer in _LAYERS:
        logger.info("Fetching %s ...", layer["typename"])
        raw = _fetch(layer["typename"])
        features: list[dict[str, Any]] = []
        for feature in raw.get("features", []):
            name = feature["properties"].get(layer["name_field"])
            if not name:
                continue
            geom = shape(feature["geometry"]).simplify(
                _SIMPLIFY_TOLERANCE, preserve_topology=True
            )
            features.append(
                {
                    "type": "Feature",
                    "properties": {"name": name},
                    "geometry": _round_coords(mapping(geom)),
                }
            )
        # Sort by name for deterministic diffs on re-fetch.
        features.sort(key=lambda f: f["properties"]["name"])
        collection = {"type": "FeatureCollection", "features": features}
        out_path = repo_root / layer["output"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as fp:
            json.dump(collection, fp, separators=(",", ":"), ensure_ascii=False)
        kb = out_path.stat().st_size / 1024
        logger.info("  wrote %d features to %s (%.0f KB)", len(features), out_path, kb)


if __name__ == "__main__":
    main()
