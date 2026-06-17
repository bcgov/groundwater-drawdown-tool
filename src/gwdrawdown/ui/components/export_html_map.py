"""Standalone interactive-map export of an analysis run.

Produces a single self-contained ``.html`` file the officer can open
in any browser: a Leaflet map (loaded from a CDN) showing the pumping
well, its buffer circle, and every observation well as a circle marker
— colour-coded by `WellStatus` and sized by predicted impact, with a
click popup carrying the per-well summary.

This is the export-side counterpart of the live results-page map.
A *static image* snapshot of the live map is not produced: capturing a
Leaflet map with cross-origin basemap tiles taints the browser canvas,
so a reliable image export is not feasible. A self-contained HTML file
is both reliable to generate (pure string templating, no headless
browser) and more useful — it stays interactive.

The module is pure: it takes an (override-applied) `AnalysisResult`
and returns an HTML string. No Dash imports.
"""

from __future__ import annotations

import json

from gwdrawdown.analysis import AnalysisResult, WellResult
from gwdrawdown.core.crs_utils import to_wgs84
from gwdrawdown.ui import disclaimers
from gwdrawdown.ui.components.palette import BUFFER_COLOR, STATUS_COLOR

# Circle-marker radius bounds (pixels) — mirrors
# `results_map._MIN_RADIUS_PX` / `_MAX_RADIUS_PX` so the exported map
# matches the live results map.
_MIN_RADIUS_PX = 6.0
_MAX_RADIUS_PX = 18.0


def _radius(w: WellResult, max_impact: float) -> float:
    """Marker radius scaled linearly to impact magnitude."""
    if w.impact_fraction is None or max_impact <= 0:
        return _MIN_RADIUS_PX
    fraction = max(0.0, min(1.0, w.impact_fraction / max_impact))
    return _MIN_RADIUS_PX + fraction * (_MAX_RADIUS_PX - _MIN_RADIUS_PX)


def _well_payload(result: AnalysisResult) -> list[dict[str, object]]:
    impacts = [
        w.impact_fraction for w in result.wells if w.impact_fraction is not None
    ]
    max_impact = max(impacts) if impacts else 1.0
    wells: list[dict[str, object]] = []
    for w in result.wells:
        lon, lat = to_wgs84(w.x_albers, w.y_albers)
        wells.append(
            {
                "wtn": w.well_tag_number,
                "lat": lat,
                "lon": lon,
                "color": STATUS_COLOR.get(w.well_status, "#666666"),
                "radius": round(_radius(w, max_impact), 1),
                "status": w.well_status.value,
                "distance": round(w.distance_m, 1),
                "drawdown": round(w.drawdown_m, 4),
                "sad": None if w.sad_m is None else round(w.sad_m, 3),
                "impact": (
                    None
                    if w.impact_fraction is None
                    else round(w.impact_fraction * 100, 1)
                ),
                "material": w.reassigned_material or "",
                "url": w.well_details_url or "",
            }
        )
    return wells


# The HTML shell. ``__PAYLOAD__`` is replaced with a JSON literal; the
# inline script then draws the map. Kept dependency-light: Leaflet from
# unpkg, OpenStreetMap + ESRI imagery basemaps, no build step.
_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body { margin: 0; height: 100%; font-family: sans-serif; }
  #map { height: 100%; width: 100%; }
  .banner {
    position: absolute; top: 0; left: 0; right: 0; z-index: 1000;
    background: #b00020; color: #fff; font-size: 12px; font-weight: bold;
    text-align: center; padding: 4px 8px;
  }
  .leaflet-popup-content { font-size: 12px; line-height: 1.5; }
  .leaflet-popup-content b { color: #0d47a1; }
</style>
</head>
<body>
<div class="banner">__BANNER__</div>
<div id="map"></div>
<script>
var DATA = __PAYLOAD__;
var map = L.map('map');
var osm = L.tileLayer(
  'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom: 19, attribution: '&copy; OpenStreetMap contributors'}
);
var imagery = L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/' +
  'World_Imagery/MapServer/tile/{z}/{y}/{x}',
  {maxZoom: 19, attribution: 'Imagery &copy; Esri'}
);
osm.addTo(map);
L.control.layers({'OpenStreetMap': osm, 'Satellite imagery': imagery}).addTo(map);

var bounds = [];

// Pumping well + buffer circle.
var p = DATA.pumping;
L.circle([p.lat, p.lon], {
  radius: p.buffer, color: '__BUFFER__', weight: 1, fillOpacity: 0.05
}).addTo(map);
L.marker([p.lat, p.lon]).addTo(map)
  .bindPopup('<b>Proposed pumping well</b>')
  .bindTooltip('Pumping well', {permanent: true, direction: 'top'});
bounds.push([p.lat, p.lon]);

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                  .replace(/>/g, '&gt;');
}

DATA.wells.forEach(function(w) {
  var m = L.circleMarker([w.lat, w.lon], {
    radius: w.radius, color: w.color, weight: 1,
    fillColor: w.color, fillOpacity: 0.75
  }).addTo(map);
  var rows = [
    '<b>WTN ' + w.wtn + '</b>',
    'Status: ' + esc(w.status),
    'Distance: ' + w.distance + ' m',
    'Drawdown: ' + w.drawdown + ' m',
    'SAD: ' + (w.sad === null ? '\\u2014' : w.sad + ' m'),
    'Impact: ' + (w.impact === null ? '\\u2014' : w.impact + '%'),
    'Material: ' + esc(w.material || '\\u2014')
  ];
  if (w.url) {
    rows.push('<a href="' + esc(w.url) + '" target="_blank">Open in GWELLS</a>');
  }
  m.bindPopup(rows.join('<br>'));
  m.bindTooltip(String(w.wtn), {permanent: true, direction: 'top'});
  bounds.push([w.lat, w.lon]);
});

if (bounds.length > 1) {
  map.fitBounds(bounds, {padding: [40, 40]});
} else {
  map.setView([p.lat, p.lon], 13);
}
</script>
</body>
</html>
"""


def build_html_map(
    result: AnalysisResult,
    *,
    overrides_by_wtn: dict[int, dict[str, float | None]] | None = None,
) -> str:
    """Serialise an `AnalysisResult` to a standalone interactive-map HTML.

    Args:
        result: The analysis result, with per-well overrides already
            applied by `analysis.apply_overrides`.
        overrides_by_wtn: Accepted for signature parity with the other
            exporters; the HTML map shows the (already override-applied)
            values, so the raw map is not needed here.

    Returns:
        A complete, self-contained HTML document as a string.
    """
    del overrides_by_wtn  # values already baked into ``result``
    inputs = result.inputs
    payload = {
        "pumping": {
            "lat": inputs.pumping_lat,
            "lon": inputs.pumping_lon,
            "buffer": inputs.buffer_radius_m,
        },
        "wells": _well_payload(result),
    }
    return (
        _HTML_TEMPLATE.replace("__PAYLOAD__", json.dumps(payload))
        .replace("__BUFFER__", BUFFER_COLOR)
        .replace("__BANNER__", disclaimers.INTERPRETATION_BANNER)
        .replace(
            "__TITLE__",
            f"Drawdown analysis map — {result.run_id[:8]}",
        )
    )
