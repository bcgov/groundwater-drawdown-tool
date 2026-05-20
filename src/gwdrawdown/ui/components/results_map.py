"""Colour-coded results map for the per-well details.

A dash-leaflet `Map` showing:

- the pumping well as a distinct dark-blue triangle (`DivMarker`),
  visually echoing the chart's pumping triangle and deliberately
  *not* red so it doesn't compete with AT_RISK observation wells;
- a translucent buffer-radius circle for context;
- one `CircleMarker` per observation well, coloured by `WellStatus`
  (shared palette with the stat cards and table cells) and sized
  by the predicted impact magnitude. Each marker carries a
  permanent WTN label and an on-click `Popup` with the full
  per-well summary.

Cross-linked to the distance-drawdown chart via a memory-scoped
``selected-well`` store on the results page. The marker's id is a
dict ``{type, wtn, status}`` so that an override edit which flips a
well's status forces a fresh React mount of the marker (dash-leaflet
1.x's `CircleMarker` doesn't propagate prop changes to the
underlying Leaflet layer for ``color`` / ``fillColor`` after the
layer has been created; baking the status into the id sidesteps
that limitation).

The map is mounted once as a thin skeleton from the results-page
``layout()``; the render callback only updates the children of the
named `LayerGroup`s and the `viewport`. Rebuilding the `Map` on every
render caused noticeable flicker and reset the pan/zoom state.
"""

from __future__ import annotations

import math
from typing import Any

import dash_leaflet as dl
from dash import html

from gwdrawdown.analysis import AnalysisResult, WellResult
from gwdrawdown.core import crs_utils
from gwdrawdown.ui.components.basemaps import make_layers_control, make_wms_legend
from gwdrawdown.ui.components.palette import (
    BUFFER_COLOR,
    PUMPING_COLOR,
    SELECTION_COLOR,
    STATUS_COLOR,
)

# Padding fraction applied when computing the viewport zoom so the
# buffer circle has some breathing room around it, not flush
# against the map edges.
_BUFFER_PADDING = 1.15

# Web-mercator metres-per-pixel at zoom 0 and the equator. The
# longitude dimension scales by cos(latitude); the latitude
# dimension is what we use here because the map is fixed at 480 px
# tall and the height dimension is the binding constraint for
# fitting a circular buffer.
_METRES_PER_PIXEL_Z0 = 156543.03

# Approximate map height in pixels — matches the inline style on
# `build_map_skeleton()`. If you resize the map, update this so the
# initial zoom keeps fitting the buffer.
_MAP_HEIGHT_PX = 480

# Leaflet caps zoom at 19 for OSM tiles.
_MAX_ZOOM = 19
_MIN_ZOOM = 0

# Marker radius bounds (pixels). Wells with no computable
# ``impact_fraction`` (INSUFFICIENT_DATA, SUSPECT_DATA) render at
# the minimum size so they're still visible but don't claim to
# carry magnitude information.
_MIN_RADIUS_PX = 6.0
_MAX_RADIUS_PX = 18.0

# Inline CSS for the pumping-well DivMarker. An upward-pointing
# triangle drawn with CSS borders + a white outline triangle behind
# it for contrast against dark basemap tiles. Anchored at the
# bottom-centre so the tip of the triangle lands on the actual
# pumping coordinate.
_PUMP_TRIANGLE_HTML = (
    '<div style="position:relative;width:24px;height:22px;">'
    # outline triangle (white, slightly bigger)
    '<div style="position:absolute;left:0;top:0;width:0;height:0;'
    "border-left:12px solid transparent;"
    "border-right:12px solid transparent;"
    'border-bottom:22px solid white;"></div>'
    # filled triangle
    '<div style="position:absolute;left:2px;top:2px;width:0;height:0;'
    "border-left:10px solid transparent;"
    "border-right:10px solid transparent;"
    f'border-bottom:18px solid {PUMPING_COLOR};"></div>'
    "</div>"
)

# Fallback when there's no result yet (page first mount).
_FALLBACK_CENTER = [48.8, -123.5]
_FALLBACK_ZOOM = 7


def _radius_for_well(w: WellResult, max_impact: float) -> float:
    """Marker radius scaled to impact magnitude.

    Linear in ``impact_fraction``, clamped to [min, max]. Wells with
    no impact fraction (SAD couldn't be computed) sit at the minimum.
    """
    if w.impact_fraction is None or max_impact <= 0:
        return _MIN_RADIUS_PX
    fraction = max(0.0, min(1.0, w.impact_fraction / max_impact))
    return _MIN_RADIUS_PX + fraction * (_MAX_RADIUS_PX - _MIN_RADIUS_PX)


_POPUP_LABEL_STYLE = {
    "display": "inline-block",
    "minWidth": "5.5rem",
    "color": "#555",
}
_POPUP_ROW_STYLE = {"marginBottom": "0.15rem"}
_POPUP_HEADER_STYLE = {
    "marginBottom": "0.4rem",
    "fontSize": "0.95rem",
    "fontWeight": 600,
    "color": "#0d47a1",
}


def _popup_row(label: str, value: str) -> html.Div:
    return html.Div(
        [
            html.Span(label, style=_POPUP_LABEL_STYLE),
            html.Span(value, style={"fontWeight": 500}),
        ],
        style=_POPUP_ROW_STYLE,
    )


def _well_popup_children(w: WellResult) -> list[Any]:
    """Formatted Dash children for the well-marker click popup."""
    sad_txt = f"{w.sad_m:.3f} m" if w.sad_m is not None else "—"
    impact_txt = (
        f"{w.impact_fraction * 100:.1f}%" if w.impact_fraction is not None else "—"
    )
    drilldown = w.well_details_url
    children: list[Any] = [
        html.Div(f"WTN {w.well_tag_number}", style=_POPUP_HEADER_STYLE),
        _popup_row("Status:", w.well_status.value),
        _popup_row("Distance:", f"{w.distance_m:.1f} m"),
        _popup_row("Drawdown:", f"{w.drawdown_m:.3f} m"),
        _popup_row("SAD:", sad_txt),
        _popup_row("Impact:", impact_txt),
        _popup_row("Material:", w.reassigned_material or "—"),
    ]
    if drilldown:
        children.append(
            html.Div(
                html.A(
                    "Open in GWELLS",
                    href=drilldown,
                    target="_blank",
                    style={"color": "#1565c0"},
                ),
                style={"marginTop": "0.35rem", "fontSize": "0.85rem"},
            )
        )
    return children


def _well_label(w: WellResult) -> Any:
    """Permanent WTN-only label rendered above each marker.

    Only ONE tooltip is bound per marker. Leaflet's ``bindTooltip``
    is single-tooltip-per-layer — if we attach a permanent label
    *and* a hover tooltip, the second one replaces the first and
    interactions (popup open/close, map click) leave the marker
    with no visible label. So the permanent label is the only
    tooltip; the rich click-popup (`dl.Popup`) handles the
    "tell me more about this well" case.

    The label deliberately carries just the well-tag number — no
    "WTN" prefix, no status — and styled-transparent via the
    ``.well-label`` rule in ``assets/styles.css`` so a buffer-full
    of wells doesn't drown the basemap in chrome.
    """
    return dl.Tooltip(
        children=str(w.well_tag_number),
        permanent=True,
        direction="top",
        offset=[0, -4],
        className="well-label",
    )


def make_well_markers(
    result: AnalysisResult,
    *,
    selected_wtn: int | None = None,
) -> list[Any]:
    """One `dl.CircleMarker` per observation well.

    The marker id is a dict ``{"type": "well-marker", "wtn": <int>,
    "status": <str>}``. Including ``status`` is deliberate: dash-leaflet
    1.x's CircleMarker doesn't push ``color`` / ``fillColor`` prop
    changes through to the underlying Leaflet layer once the layer
    has been created, so an override that flips a well from OK to
    AT_RISK would leave the marker its old colour. Baking the status
    into the id changes the React key on a status flip, forcing a
    fresh mount of the marker with the correct colour.

    `select_from_map` on the results page matches on ``{type, wtn,
    status}`` with ALL and still extracts the integer WTN from
    ``ctx.triggered_id``.
    """
    impacts = [
        w.impact_fraction for w in result.wells if w.impact_fraction is not None
    ]
    max_impact = max(impacts) if impacts else 1.0

    markers: list[Any] = []
    for w in result.wells:
        lon, lat = crs_utils.to_wgs84(w.x_albers, w.y_albers)
        color = STATUS_COLOR.get(w.well_status, "#666")
        radius = _radius_for_well(w, max_impact)
        is_selected = selected_wtn is not None and selected_wtn == w.well_tag_number
        markers.append(
            dl.CircleMarker(
                center=[lat, lon],
                radius=radius,
                color=SELECTION_COLOR if is_selected else color,
                weight=3 if is_selected else 1,
                fillColor=color,
                fillOpacity=0.75,
                children=[
                    _well_label(w),
                    dl.Popup(_well_popup_children(w), maxWidth=260),
                ],
                id={
                    "type": "well-marker",
                    "wtn": int(w.well_tag_number),
                    "status": w.well_status.value,
                },
                n_clicks=0,
            )
        )
    return markers


def make_pumping_layer(result: AnalysisResult) -> list[Any]:
    """Pumping-well triangle + buffer-radius circle for orientation.

    The pumping marker is a `DivMarker` with a CSS triangle so it
    visually echoes the chart's pumping triangle. Anchored at
    `[10, 18]` so the tip of the triangle lines up with the actual
    pumping coordinate.
    """
    inputs = result.inputs
    return [
        dl.Circle(
            center=[inputs.pumping_lat, inputs.pumping_lon],
            radius=inputs.buffer_radius_m,
            color=BUFFER_COLOR,
            weight=1,
            fillOpacity=0.05,
        ),
        dl.DivMarker(
            position=[inputs.pumping_lat, inputs.pumping_lon],
            iconOptions={
                "html": _PUMP_TRIANGLE_HTML,
                "className": "pump-marker",
                "iconSize": [24, 22],
                "iconAnchor": [12, 22],
            },
            children=[
                dl.Tooltip(
                    "Pumping well",
                    permanent=True,
                    direction="top",
                    offset=[0, -22],
                    className="pump-label",
                ),
            ],
        ),
    ]


def _zoom_for_buffer(pump_lat: float, buffer_m: float) -> int:
    """Pick a Leaflet zoom that fits the buffer circle in the viewport.

    Inverts the Web-Mercator metres-per-pixel formula at the given
    latitude. The map height (`_MAP_HEIGHT_PX`) is the binding
    constraint for fitting a circular buffer — width is typically
    larger. `_BUFFER_PADDING` leaves a little air around the circle
    so it doesn't sit flush against the map edges.

    Earlier attempts used `viewport.bounds` to let Leaflet do the
    fitting itself, but dash-leaflet 1.x's viewport handler didn't
    apply bounds-only payloads cleanly and the map snapped to its
    world view. Computing the zoom ourselves and sending plain
    ``center`` + ``zoom`` is reliable.
    """
    if buffer_m <= 0:
        return 13
    metres_per_pixel_z0 = _METRES_PER_PIXEL_Z0 * math.cos(math.radians(pump_lat))
    if metres_per_pixel_z0 <= 0:
        return 13
    required_metres = 2 * buffer_m * _BUFFER_PADDING
    target = _MAP_HEIGHT_PX * metres_per_pixel_z0 / required_metres
    if target <= 0:
        return 13
    # floor so we slightly underfit — the buffer fits with room to
    # spare rather than spilling off a sub-pixel. `math.floor`
    # already returns `int` in Python 3.x.
    z = math.floor(math.log2(target))
    return max(_MIN_ZOOM, min(_MAX_ZOOM, z))


def map_viewport_for(result: AnalysisResult) -> dict[str, Any]:
    """Viewport centred on the pumping well, zoomed to fit the buffer.

    Computes the zoom level explicitly so dash-leaflet's viewport
    handler has everything it needs in plain ``center`` + ``zoom``
    form. Fires only on `analysis-result` changes (see
    `centre_map_on_new_result` in the results page) — any pan/zoom
    the officer applies in-session stays put through override edits
    and selection changes.
    """
    inputs = result.inputs
    return {
        "center": [inputs.pumping_lat, inputs.pumping_lon],
        "zoom": _zoom_for_buffer(inputs.pumping_lat, inputs.buffer_radius_m),
        "transition": "flyTo",
    }


def build_map_skeleton() -> html.Div:
    """Static map block mounted once by the results page.

    The `dl.Map` is wrapped in a relative-positioned `html.Div` so the
    WMS legend panel can be absolutely positioned over the bottom-right
    corner. Named `LayerGroup`s carry the dynamic content — pumping
    marker, well markers, and the viewport-anchored boundary labels;
    the render callbacks write to their ``children`` rather than
    rebuilding the Map, which avoids the tile-flicker and pan-reset
    that came with full re-renders. ``results-map-labels`` is fed by
    the boundary-label callback on the results page.
    """
    return html.Div(
        [
            dl.Map(
                id="results-map",
                center=_FALLBACK_CENTER,
                zoom=_FALLBACK_ZOOM,
                style={"height": "480px", "width": "100%"},
                children=[
                    make_layers_control(
                        mode="results", control_id="results-layers-control"
                    ),
                    dl.LayerGroup(id="results-map-pumping", children=[]),
                    dl.LayerGroup(id="results-map-wells", children=[]),
                    dl.LayerGroup(id="results-map-labels", children=[]),
                ],
            ),
            # Wells overlay isn't offered on the results map, so the
            # legend only ever carries the aquifer entry — and that
            # overlay defaults off here.
            make_wms_legend("results-wms-legend", aquifers_on=False),
        ],
        style={"position": "relative", "marginBottom": "0.5rem"},
    )
