"""Shared map-layer configuration for the setup and results maps.

Both maps offer the same three basemaps via a `dl.LayersControl` widget
in the top-right corner: OpenStreetMap (default), an ESRI World
Topographic tileset for relief context, and ESRI World Imagery for
satellite. Centralising the URLs and attributions here keeps the two
maps consistent and makes it a one-line change to swap a provider.

The same widget carries overlays for visual context:

- **Aquifers** and **All BC Wells** — BCGW WMS tile layers
  (`openmaps.gov.bc.ca/geo/pub/...`). These datasets are far too large
  to ship client-side (thousands of aquifer polygons; ~150k wells), so
  they stay server-rendered. Both carry a ``minZoom`` floor and an
  inline "(zoom ≥ N)" hint on the layer name.
- **Water Management Districts / Precincts** — shipped as simplified
  GeoJSON in the assets directory and rendered client-side as
  `dl.GeoJSON` vector overlays. These two layers are small and static
  (regulation-derived administrative boundaries), so a committed
  snapshot is the right call: full styling control and no per-tile
  WMS round-trips. Regenerate the snapshot with
  ``scripts/fetch_water_mgmt_boundaries.py`` if BC re-delineates.

All BC-sourced layers follow the Open Government Licence - British
Columbia (OGL-BC).

Defaults differ per map:

- Setup map (``mode="setup"``) — aquifers ON by default (the picker
  workflow is grounded in seeing aquifer polygons); WMD, WMP, Wells
  OFF.
- Results map (``mode="results"``) — all overlays OFF, and the Wells
  overlay is omitted entirely because the page already renders the
  observation-well set as colour-coded markers and layering the full
  BCGW well point cloud underneath would be visually redundant.
"""

from __future__ import annotations

from typing import Final, Literal

import dash_leaflet as dl
from dash import html

# --- Basemap URLs and attributions ------------------------------------------

# OpenStreetMap. The default `dl.TileLayer()` already points here, but
# we set the URL explicitly so all three basemaps follow the same
# pattern and the attribution string is in one place.
_OSM_URL: Final[str] = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
_OSM_ATTRIBUTION: Final[str] = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">'
    "OpenStreetMap</a> contributors"
)

# ESRI World Topographic Map. Free for low-volume use with attribution
# per ESRI's terms; no API key required. URL pattern is {z}/{y}/{x}
# (Y before X — different from OSM).
_TOPO_URL: Final[str] = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
)
_TOPO_ATTRIBUTION: Final[str] = (
    "Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ, TomTom, Intermap, "
    "iPC, USGS, FAO, NPS, NRCAN, GeoBase, Kadaster NL, Ordnance Survey, "
    "Esri Japan, METI, Esri China (Hong Kong), and the GIS User Community"
)

# ESRI World Imagery (satellite / aerial). Same terms as Topographic.
_IMAGERY_URL: Final[str] = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
_IMAGERY_ATTRIBUTION: Final[str] = (
    "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, "
    "GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community"
)


# --- BC-sourced overlay configuration ---------------------------------------

# All BC-sourced layers share this attribution line (OGL-BC). Rendered
# once per map by Leaflet's attribution control — duplicates are
# de-duped automatically.
_OGL_BC_ATTRIBUTION: Final[str] = (
    "Contains information licensed under the "
    '<a href="https://www2.gov.bc.ca/gov/content/data/'
    'open-data/open-government-licence-bc">'
    "Open Government Licence &ndash; British Columbia</a>"
)

# WMS protocol version. 1.3.0 is the current OGC standard and what
# BC's openmaps endpoint is configured for. Older 1.1.1 still works
# but swaps lat/lon axis order, which has burned plenty of teams.
_WMS_VERSION: Final[str] = "1.3.0"

# WMS layer-scoped endpoints (one virtual service per layer). The
# global `/geo/pub/ows` works too but the layer-scoped URLs are what
# the BC Data Catalogue publishes.
_AQUIFERS_URL: Final[str] = (
    "https://openmaps.gov.bc.ca/geo/pub/"
    "WHSE_WATER_MANAGEMENT.GW_AQUIFERS_CLASSIFICATION_SVW/ows"
)
_AQUIFERS_LAYER: Final[str] = "pub:WHSE_WATER_MANAGEMENT.GW_AQUIFERS_CLASSIFICATION_SVW"
# Default style "Aquifers_All" — categorical fill. None of the
# published styles are outline-only; we dim the fill with Leaflet
# opacity instead so the basemap reads through.
_AQUIFERS_OPACITY: Final[float] = 0.55

_WELLS_URL: Final[str] = (
    "https://openmaps.gov.bc.ca/geo/pub/"
    "WHSE_WATER_MANAGEMENT.GW_WATER_WELLS_WRBC_SVW/ows"
)
_WELLS_LAYER: Final[str] = "pub:WHSE_WATER_MANAGEMENT.GW_WATER_WELLS_WRBC_SVW"
# Default style "Groundwater_Wells_All" — simple point symbology.

# GetLegendGraphic URLs — the WMS symbology swatch for the aquifer and
# well layers, shown in the on-map legend panel. The images are tiny
# (~1 KB) and browser-cached after first load.
_AQUIFERS_LEGEND_URL: Final[str] = (
    f"{_AQUIFERS_URL}?service=WMS&version={_WMS_VERSION}"
    f"&request=GetLegendGraphic&format=image/png&layer={_AQUIFERS_LAYER}"
)
_WELLS_LEGEND_URL: Final[str] = (
    f"{_WELLS_URL}?service=WMS&version={_WMS_VERSION}"
    f"&request=GetLegendGraphic&format=image/png&layer={_WELLS_LAYER}"
)

# Water management boundary GeoJSON — committed, pre-simplified
# snapshots served from the Dash assets directory. Generated by
# ``scripts/fetch_water_mgmt_boundaries.py``.
_WMD_GEOJSON_URL: Final[str] = "/assets/wmd_boundaries.geojson"
_WMP_GEOJSON_URL: Final[str] = "/assets/wmp_boundaries.geojson"

# Vector styling for the boundary overlays. Slate tones — neutral,
# administrative-looking, and clear of the status palette (green / red
# / orange / purple) and the pumping-blue used elsewhere on the maps.
# Districts read as the primary boundary (darker, heavier, solid);
# precincts as the secondary subdivision (lighter, thinner, dashed).
_WMD_STYLE: Final[dict[str, object]] = {
    "color": "#455a64",
    "weight": 2.5,
    "fillOpacity": 0.0,
}
_WMP_STYLE: Final[dict[str, object]] = {
    "color": "#78909c",
    "weight": 1.5,
    "dashArray": "5 4",
    "fillOpacity": 0.0,
}

# Zoom thresholds for the WMS overlays.
#
# Aquifers — BC's WMS sets ``MaxScaleDenominator=1200000`` on the
# layer, so the server returns blank tiles below ~zoom 9 anyway.
# Matching that on the client side means we don't waste round-trips
# on guaranteed-blank tiles and the layer-control hint reflects
# reality.
#
# Wells — ~150k points; only resolves into something useful around
# zoom 13+. Below that it's a uniform blob.
#
# WMD/WMP have no zoom floor: rendered client-side as vector outlines,
# they cost nothing per pan/zoom and read fine at any scale.
AQUIFERS_MIN_ZOOM: Final[int] = 9
WELLS_MIN_ZOOM: Final[int] = 13


# --- Public API -------------------------------------------------------------

# Display names for the basemap radio entries in the layers-control
# widget. Kept short so the widget doesn't expand to fit the longest
# label.
OSM_NAME: Final[str] = "OpenStreetMap"
TOPO_NAME: Final[str] = "Topographic"
IMAGERY_NAME: Final[str] = "Satellite"

# Overlay display names. These are the exact strings shown in the
# LayersControl widget and reported back through its `overlays` prop,
# so the boundary-label and legend callbacks match against them.
AQUIFERS_OVERLAY_NAME: Final[str] = f"Aquifers (zoom ≥ {AQUIFERS_MIN_ZOOM})"
WELLS_OVERLAY_NAME: Final[str] = f"All BC Wells (zoom ≥ {WELLS_MIN_ZOOM})"
WMD_OVERLAY_NAME: Final[str] = "Water Management Districts"
WMP_OVERLAY_NAME: Final[str] = "Water Management Precincts"

# "setup" — aquifers default ON, all four overlays available.
# "results" — all overlays default OFF, Wells overlay omitted.
MapMode = Literal["setup", "results"]


def make_basemap_layers(default: str = OSM_NAME) -> list[dl.BaseLayer]:
    """Return the three basemap entries for a `dl.LayersControl`.

    Exactly one entry has ``checked=True``; the others render only
    when the user picks them. Default is OpenStreetMap, which matches
    the pre-Phase-5b behaviour.
    """
    return [
        dl.BaseLayer(
            dl.TileLayer(url=_OSM_URL, attribution=_OSM_ATTRIBUTION),
            name=OSM_NAME,
            checked=(default == OSM_NAME),
        ),
        dl.BaseLayer(
            dl.TileLayer(url=_TOPO_URL, attribution=_TOPO_ATTRIBUTION),
            name=TOPO_NAME,
            checked=(default == TOPO_NAME),
        ),
        dl.BaseLayer(
            dl.TileLayer(url=_IMAGERY_URL, attribution=_IMAGERY_ATTRIBUTION),
            name=IMAGERY_NAME,
            checked=(default == IMAGERY_NAME),
        ),
    ]


def _bc_wms(
    url: str,
    layer: str,
    *,
    min_zoom: int = 0,
    opacity: float = 1.0,
) -> dl.WMSTileLayer:
    """Build one `dl.WMSTileLayer` against a BC openmaps endpoint."""
    kwargs: dict[str, object] = {
        "url": url,
        "layers": layer,
        "format": "image/png",
        "transparent": True,
        "version": _WMS_VERSION,
        "attribution": _OGL_BC_ATTRIBUTION,
        "minZoom": min_zoom,
    }
    if opacity != 1.0:
        kwargs["opacity"] = opacity
    return dl.WMSTileLayer(**kwargs)


def _bc_geojson(url: str, style: dict[str, object]) -> dl.GeoJSON:
    """Build a client-side vector overlay for a boundary GeoJSON.

    ``interactive=False`` is deliberate: on the setup map a click is
    how the officer places the pumping point, and an interactive
    polygon would swallow that click before it reached the map.
    """
    return dl.GeoJSON(
        url=url,
        style=style,
        interactive=False,
        zoomToBounds=False,
        attribution=_OGL_BC_ATTRIBUTION,
    )


def _bc_overlays(mode: MapMode) -> list[dl.Overlay]:
    """Build the overlay entries for the given map mode.

    Setup map gets all four overlays with aquifers default-on; results
    map gets three (no wells) and everything default-off so the
    overlays never compete with the colour-coded marker layer until
    the officer asks for them.
    """
    aquifers_default_on = mode == "setup"

    overlays: list[dl.Overlay] = [
        dl.Overlay(
            _bc_wms(
                _AQUIFERS_URL,
                _AQUIFERS_LAYER,
                min_zoom=AQUIFERS_MIN_ZOOM,
                opacity=_AQUIFERS_OPACITY,
            ),
            name=AQUIFERS_OVERLAY_NAME,
            checked=aquifers_default_on,
        ),
        dl.Overlay(
            _bc_geojson(_WMD_GEOJSON_URL, _WMD_STYLE),
            name=WMD_OVERLAY_NAME,
            checked=False,
        ),
        dl.Overlay(
            _bc_geojson(_WMP_GEOJSON_URL, _WMP_STYLE),
            name=WMP_OVERLAY_NAME,
            checked=False,
        ),
    ]

    if mode == "setup":
        overlays.append(
            dl.Overlay(
                _bc_wms(
                    _WELLS_URL,
                    _WELLS_LAYER,
                    min_zoom=WELLS_MIN_ZOOM,
                ),
                name=WELLS_OVERLAY_NAME,
                checked=False,
            )
        )

    return overlays


def make_layers_control(
    *,
    mode: MapMode = "setup",
    default_basemap: str = OSM_NAME,
    control_id: str | None = None,
) -> dl.LayersControl:
    """Return a `dl.LayersControl` with basemaps + overlays.

    Anchored top-right, collapsed by default so the control is a small
    hamburger until the user hovers it. ``mode`` picks the overlay
    set and defaults: setup map has all four overlays with aquifers
    on; results map has three (no Wells) and all default-off.

    ``control_id`` gives the widget a Dash id so a callback can read
    its ``overlays`` prop — that's how the boundary-label callback
    knows whether the WMD / WMP overlays are toggled on.
    """
    children: list[dl.BaseLayer | dl.Overlay] = list(make_basemap_layers(default_basemap))
    children.extend(_bc_overlays(mode))
    kwargs: dict[str, object] = {
        "position": "topright",
        "collapsed": True,
        "children": children,
    }
    if control_id is not None:
        kwargs["id"] = control_id
    return dl.LayersControl(**kwargs)


# --- WMS legend panel --------------------------------------------------------
#
# The aquifer and well WMS layers are server-rendered with their own
# symbology (categorical fills / point symbols). The GeoJSON boundary
# overlays are styled by us and self-explanatory, so they get no
# legend entry. The panel sits bottom-right of the map and only shows
# a block for a layer while that layer's overlay is toggled on — its
# children are refreshed by a per-page callback off the LayersControl
# `overlays` prop.


def _legend_block(title: str, img_url: str) -> html.Div:
    """One legend entry: a caption above the WMS GetLegendGraphic image."""
    return html.Div(
        [
            html.Div(title, className="gw-wms-legend__title"),
            html.Img(
                src=img_url,
                className="gw-wms-legend__img",
                alt=f"{title} symbology legend",
            ),
        ],
        className="gw-wms-legend__block",
    )


def _legend_blocks(*, show_aquifers: bool, show_wells: bool) -> list[html.Div]:
    blocks: list[html.Div] = []
    if show_aquifers:
        blocks.append(_legend_block("Aquifers", _AQUIFERS_LEGEND_URL))
    if show_wells:
        blocks.append(_legend_block("BC Wells", _WELLS_LEGEND_URL))
    return blocks


def wms_legend_children(
    overlays: list[str] | None,
    *,
    include_wells: bool,
) -> list[html.Div]:
    """Legend blocks for the WMS overlays currently toggled on.

    Driven by the LayersControl ``overlays`` prop. ``include_wells``
    is False on the results map, which has no wells overlay.
    """
    active = overlays or []
    return _legend_blocks(
        show_aquifers=AQUIFERS_OVERLAY_NAME in active,
        show_wells=include_wells and WELLS_OVERLAY_NAME in active,
    )


def make_wms_legend(
    legend_id: str,
    *,
    aquifers_on: bool,
) -> html.Div:
    """Build the WMS symbology legend panel for a map.

    A small panel pinned to the bottom-right of the map. Its
    ``children`` are refreshed by a per-page callback as overlays are
    toggled; the initial children set here match the map's default
    overlay state so the legend is correct on first paint without
    depending on the callback's initial call. (Wells default off on
    both maps, so only ``aquifers_on`` varies.)
    """
    return html.Div(
        id=legend_id,
        className="gw-wms-legend",
        children=_legend_blocks(show_aquifers=aquifers_on, show_wells=False),
    )
