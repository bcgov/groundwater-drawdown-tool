"""Esri basemap tile sources shared by the maps and the map exports.

Kept free of Dash imports so the export modules — the standalone HTML
map and the PDF report's map page — can use the same URLs and
attributions as the in-app layer control without pulling in
``dash_leaflet``.

Why the exports use Esri and not OpenStreetMap: the OSM tile servers
refuse browser requests that carry no HTTP ``Referer`` header (they
return an "Access blocked" tile instead). A downloaded HTML file opened
from disk is a ``file://`` page, which never sends a Referer, so an OSM
basemap cannot work there. OSM's tile usage policy also rules out
fetching tiles server-side for the PDF. Esri's tile service has neither
restriction. The in-app maps keep OSM, because a page served from
``http://127.0.0.1`` does send a Referer (see `basemaps.py`).

All three services are free for low-volume use with attribution, need
no API key, and use the ``{z}/{y}/{x}`` pattern (Y before X — the
reverse of OSM). Each ``url`` is a Leaflet template, and also a Python
``str.format`` template.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class TileSource:
    """One raster basemap: display name, tile URL template, attribution."""

    name: str
    url: str
    # HTML, as Leaflet's attribution control expects it.
    attribution: str

    def tile_url(self, z: int, x: int, y: int) -> str:
        """The URL of one tile."""
        return self.url.format(z=z, x=x, y=y)

    @property
    def attribution_text(self) -> str:
        """The attribution as plain text, for print."""
        return html.unescape(self.attribution)


_ESRI_ROOT: Final[str] = "https://server.arcgisonline.com/ArcGIS/rest/services/"

# The attribution strings follow each service's own ``copyrightText``
# (``<service>/MapServer?f=json``) where it has been refreshed.
ESRI_STREETS: Final[TileSource] = TileSource(
    name="Streets",
    url=_ESRI_ROOT + "World_Street_Map/MapServer/tile/{z}/{y}/{x}",
    attribution=(
        "Tiles &copy; Esri &mdash; Sources: Esri, HERE, Garmin, USGS, "
        "Intermap, INCREMENT P, NRCan, Esri Japan, METI, Esri China "
        "(Hong Kong), Esri Korea, Esri (Thailand), NGCC, &copy; "
        "OpenStreetMap contributors, and the GIS User Community"
    ),
)

ESRI_TOPO: Final[TileSource] = TileSource(
    name="Topographic",
    url=_ESRI_ROOT + "World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
    attribution=(
        "Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ, TomTom, Intermap, "
        "iPC, USGS, FAO, NPS, NRCAN, GeoBase, Kadaster NL, Ordnance Survey, "
        "Esri Japan, METI, Esri China (Hong Kong), and the GIS User Community"
    ),
)

ESRI_IMAGERY: Final[TileSource] = TileSource(
    name="Satellite",
    url=_ESRI_ROOT + "World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution=(
        "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, "
        "GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User "
        "Community"
    ),
)
