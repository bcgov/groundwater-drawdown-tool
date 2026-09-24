"""The results map, drawn for the PDF report.

Client request (2026-09): the PDF should carry the map, not only the
charts and tables.

The live results map cannot simply be photographed. It is a Leaflet map
in the browser, and reading its basemap tiles back into an image runs
into the browser's cross-origin rules, so the clientside capture that
brings the charts into the PDF is not reliable for the map. The map is
drawn here instead, server-side, from the same `AnalysisResult` as the
rest of the report:

- the basemap is a mosaic of Esri raster tiles, fetched at export time
  and stitched with Pillow (`fetch_basemap`);
- the buffer circle, well markers, licence rings, pumping well, well
  tag numbers, north arrow and scale bar are drawn over it as reportlab
  vectors (`ResultsMap`), so they stay sharp in print.

The map is framed on the analysis buffer, the extent the results map
opens on, rather than wherever the officer last panned, so every report
shows the whole buffer. The basemap follows the officer's choice on the
results map, except that OpenStreetMap prints as Esri Streets: OSM's
tile usage policy rules out server-side fetching (see `tile_sources`).

If the tiles cannot be fetched (no internet, Esri down), the map is
still drawn on a plain background and its caption says why. The report
never fails for want of a basemap.

Fetching is the only I/O. The export callback calls `fetch_basemap` and
hands the result to `build_pdf`, which therefore stays pure. The tile
getter is injectable for tests.
"""

from __future__ import annotations

import html
import io
import logging
import math
import urllib.request
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Final

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Flowable

from gwdrawdown.analysis import AnalysisResult, WellResult
from gwdrawdown.core.crs_utils import to_wgs84
from gwdrawdown.core.flagging import WellStatus
from gwdrawdown.ui.components.export_html_map import marker_radius_px
from gwdrawdown.ui.components.palette import (
    BUFFER_COLOR,
    PUMPING_COLOR,
    STATUS_COLOR,
)
from gwdrawdown.ui.components.tile_sources import (
    ESRI_IMAGERY,
    ESRI_STREETS,
    ESRI_TOPO,
    TileSource,
)
from gwdrawdown.ui.format_utils import is_licensed

logger = logging.getLogger(__name__)

# --- Framing -----------------------------------------------------------------

# Width / height of the printed map box. The PDF lays the map out at
# this aspect and the basemap is fetched for a frame of the same
# aspect, so the two always line up.
MAP_ASPECT: Final[float] = 1.75

# Map height as a multiple of the buffer diameter, leaving some air
# around the circle. Height is the binding dimension of a landscape box.
_BUFFER_PADDING: Final[float] = 1.12

# Aim for a basemap about this many pixels tall; the zoom is a whole
# number, so the real height lands within a factor of √2 either side.
# That is roughly 1.5 image pixels per printed point: sharp enough to
# print, while the basemap's own place names, which are drawn for
# screens, still print at a readable size.
_TARGET_HEIGHT_PX: Final[float] = 640.0

_TILE_PX: Final[int] = 256
# Ground metres per pixel at zoom 0 on the equator (Web Mercator).
_METRES_PER_PX_Z0: Final[float] = 156_543.03392
_MIN_ZOOM: Final[int] = 1
# Esri's street and topographic tiles run out of detail past this.
_MAX_ZOOM: Final[int] = 18


def _world_px(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    """Web Mercator pixel position at ``zoom``, from the world's top-left."""
    scale = _TILE_PX * 2**zoom
    sin_lat = math.sin(math.radians(lat))
    x = (lon + 180.0) / 360.0 * scale
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * scale
    return x, y


@dataclass(frozen=True)
class MapFrame:
    """The printed map's extent, in Web Mercator pixels at ``zoom``."""

    zoom: int
    left: float
    top: float
    width: float
    height: float
    # Ground metres per pixel at the pumping well's latitude.
    metres_per_px: float

    def to_frame(self, lon: float, lat: float) -> tuple[float, float]:
        """A point's position in the frame, in pixels from its top-left."""
        x, y = _world_px(lon, lat, self.zoom)
        return x - self.left, y - self.top


def map_frame(result: AnalysisResult) -> MapFrame:
    """The frame the PDF map shows: the buffer, centred on the pumping well.

    The zoom is the whole number that brings the frame height closest
    to `_TARGET_HEIGHT_PX`, so a small buffer and a large one print at
    the same sharpness.
    """
    inputs = result.inputs
    lat = inputs.pumping_lat
    span_m = 2 * max(inputs.buffer_radius_m, 1.0) * _BUFFER_PADDING
    mpp_z0 = _METRES_PER_PX_Z0 * math.cos(math.radians(lat))
    zoom = round(math.log2(_TARGET_HEIGHT_PX * mpp_z0 / span_m))
    zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, zoom))
    mpp = mpp_z0 / 2**zoom
    height = span_m / mpp
    width = height * MAP_ASPECT
    cx, cy = _world_px(inputs.pumping_lon, lat, zoom)
    return MapFrame(
        zoom=zoom,
        left=cx - width / 2,
        top=cy - height / 2,
        width=width,
        height=height,
        metres_per_px=mpp,
    )


# --- Basemap fetch -----------------------------------------------------------

# Name a real app, as tile services ask, rather than Python's default.
_USER_AGENT: Final[str] = (
    "gwdrawdown (BC groundwater drawdown screening tool; "
    "https://github.com/bcgov/groundwater-drawdown-tool)"
)
_TILE_TIMEOUT_S: Final[float] = 6.0
# Hard cap on the whole fetch, so a stalled network delays the PDF by
# seconds rather than hanging the export.
_FETCH_DEADLINE_S: Final[float] = 20.0
_FETCH_WORKERS: Final[int] = 8
_JPEG_QUALITY: Final[int] = 88

TileGetter = Callable[[str], bytes]


@dataclass(frozen=True)
class Basemap:
    """A basemap image covering exactly `map_frame(result)`."""

    jpeg: bytes
    source: TileSource


def basemap_source_for(base_layer: str | None) -> TileSource:
    """The basemap to print, given the one picked on the results map.

    ``base_layer`` is the name the results map's layer control reports:
    ``None`` until the officer switches basemap. Topographic and
    Satellite print as themselves. OpenStreetMap, the default, prints
    as Esri Streets, the closest look that may be fetched server-side.
    """
    printable = {s.name: s for s in (ESRI_TOPO, ESRI_IMAGERY)}
    return printable.get(base_layer or "", ESRI_STREETS)


def _http_get(url: str) -> bytes:
    """GET one tile.

    Standard-library ``urllib`` rather than ``requests`` on purpose: on
    Windows it trusts the certificates in the Windows store and picks up
    the system proxy, which is what a managed government network needs.
    """
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=_TILE_TIMEOUT_S) as response:
        return response.read()


def fetch_basemap(
    result: AnalysisResult,
    source: TileSource,
    *,
    get: TileGetter = _http_get,
) -> Basemap | None:
    """Fetch and stitch the basemap tiles under `map_frame(result)`.

    Tiles are fetched in parallel, each retried once. The basemap is
    all or nothing: if any tile still fails, or the whole fetch runs
    past `_FETCH_DEADLINE_S`, this returns ``None`` and the map prints
    without one. A map with holes in it would look broken, not partial.
    """
    frame = map_frame(result)
    n_tiles = 2**frame.zoom
    x0 = math.floor(frame.left / _TILE_PX)
    x1 = math.floor((frame.left + frame.width) / _TILE_PX)
    y0 = max(0, math.floor(frame.top / _TILE_PX))
    y1 = min(n_tiles - 1, math.floor((frame.top + frame.height) / _TILE_PX))
    tiles = [(tx, ty) for ty in range(y0, y1 + 1) for tx in range(x0, x1 + 1)]

    def fetch_one(tx: int, ty: int) -> PILImage.Image:
        url = source.tile_url(frame.zoom, tx % n_tiles, ty)
        try:
            data = get(url)
        except OSError:
            data = get(url)
        with PILImage.open(io.BytesIO(data)) as tile:
            return tile.convert("RGB")

    mosaic = PILImage.new(
        "RGB", ((x1 - x0 + 1) * _TILE_PX, (y1 - y0 + 1) * _TILE_PX), "white"
    )
    pool = ThreadPoolExecutor(max_workers=_FETCH_WORKERS)
    futures = {pool.submit(fetch_one, tx, ty): (tx, ty) for tx, ty in tiles}
    done, pending = wait(futures, timeout=_FETCH_DEADLINE_S)
    pool.shutdown(wait=False, cancel_futures=True)
    failed = len(pending)
    for future in done:
        tx, ty = futures[future]
        try:
            tile = future.result()
        except Exception:
            failed += 1
            continue
        mosaic.paste(tile, ((tx - x0) * _TILE_PX, (ty - y0) * _TILE_PX))
    if failed:
        logger.warning(
            "PDF map: %d of %d %s basemap tiles unavailable; "
            "printing the map without a basemap",
            failed,
            len(tiles),
            source.name,
        )
        return None

    left = round(frame.left - x0 * _TILE_PX)
    top = round(frame.top - y0 * _TILE_PX)
    image = mosaic.crop(
        (left, top, left + round(frame.width), top + round(frame.height))
    )
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=_JPEG_QUALITY)
    return Basemap(jpeg=buffer.getvalue(), source=source)


# --- Label placement ---------------------------------------------------------


@dataclass(frozen=True)
class Box:
    """An axis-aligned rectangle in points, ``y`` up."""

    x0: float
    y0: float
    x1: float
    y1: float

    def overlap(self, other: Box) -> float:
        """Area shared with ``other``."""
        w = min(self.x1, other.x1) - max(self.x0, other.x0)
        h = min(self.y1, other.y1) - max(self.y0, other.y0)
        return w * h if w > 0 and h > 0 else 0.0

    @property
    def area(self) -> float:
        return (self.x1 - self.x0) * (self.y1 - self.y0)


# Space between a marker's edge and its label.
_LABEL_GAP_PT: Final[float] = 1.5


def place_labels(
    marks: Sequence[tuple[float, float, float]],
    sizes: Sequence[tuple[float, float]],
    *,
    obstacles: Sequence[Box] = (),
    bounds: Box | None = None,
) -> list[Box]:
    """Choose a box for each marker's label, steering clear of collisions.

    ``marks`` are ``(x, y, radius)`` and ``sizes`` ``(width, height)``,
    in points. Each label tries above, below, right and left of its
    marker, in that order, and takes the first spot that touches no
    label placed before it, no other marker, no obstacle, and stays in
    ``bounds``. When every spot collides it takes the least-bad one.

    A label is never dropped: client feedback on the charts was that a
    missing well tag number is worse than a crowded one. Markers are
    placed in the order given, so pass the most important first.
    """
    marker_boxes = [Box(x - r, y - r, x + r, y + r) for x, y, r in marks]
    placed: list[Box] = []
    for i, ((x, y, r), (w, h)) in enumerate(zip(marks, sizes, strict=True)):
        d = r + _LABEL_GAP_PT
        candidates = [
            Box(x - w / 2, y + d, x + w / 2, y + d + h),
            Box(x - w / 2, y - d - h, x + w / 2, y - d),
            Box(x + d, y - h / 2, x + d + w, y + h / 2),
            Box(x - d - w, y - h / 2, x - d, y + h / 2),
        ]
        others = [
            *obstacles,
            *placed,
            *(b for j, b in enumerate(marker_boxes) if j != i),
        ]

        def cost(box: Box, others: list[Box] = others) -> float:
            clash = sum(box.overlap(o) for o in others)
            if bounds is not None:
                clash += box.area - box.overlap(bounds)
            return clash

        # `min` keeps the first of equals, so the preference order holds.
        placed.append(min(candidates, key=cost))
    return placed


# --- Drawing -----------------------------------------------------------------

# Marker sizes are screen pixels on the live map; print them at the
# same physical size (96 px to the inch, 72 pt to the inch).
_PT_PER_SCREEN_PX: Final[float] = 0.75

# Mirror `results_map`: the licensed-well ring and the marker styling.
_LICENSED_RING_COLOUR: Final = colors.HexColor("#212121")
_LICENSED_RING_GAP_PX: Final[float] = 3.0
_LICENSED_RING_WEIGHT_PX: Final[float] = 2.0
_MARKER_FILL_ALPHA: Final[float] = 0.75
_BUFFER_FILL_ALPHA: Final[float] = 0.05

# The pumping-well triangle, in screen pixels: a white outline triangle
# with the blue one inset 2 px, base centred on the well — as drawn by
# `results_map._PUMP_TRIANGLE_HTML`.
_PUMP_W_PX: Final[float] = 24.0
_PUMP_H_PX: Final[float] = 22.0
_PUMP_INSET_PX: Final[float] = 2.0

# Well tag numbers: dark with a white halo, like the live map's
# ``.well-label``.
_LABEL_FONT: Final[str] = "Helvetica-Bold"
_LABEL_SIZE: Final[float] = 6.5
_LABEL_COLOUR: Final = colors.HexColor("#222222")
_HALO_PT: Final[float] = 0.8
# Digits have no descenders, so a label is about cap height tall.
_LABEL_HEIGHT: Final[float] = _LABEL_SIZE * 0.72

_NO_BASEMAP_BG: Final = colors.HexColor("#f3f3f1")
_BORDER_COLOUR: Final = colors.HexColor("#999999")
_INSET_PT: Final[float] = 8.0  # north arrow / scale bar from the map edge
_PANEL_BG: Final = colors.Color(1, 1, 1, alpha=0.85)


def _hex(colour: str) -> colors.Color:
    return colors.HexColor(colour)


def _halo_text(canvas, x: float, y: float, text: str, fill) -> None:
    """Draw ``text`` with a white halo, so it reads on any basemap."""
    canvas.saveState()
    # The halo is the text stroked wide in white. It gets a graphics
    # state of its own: the text render mode belongs to that state, and
    # reportlab does not reset it for the next text object, so without
    # the restore the fill pass would come out stroked white too.
    canvas.saveState()
    canvas.setStrokeColor(colors.white)
    canvas.setLineWidth(2 * _HALO_PT)
    canvas.setLineJoin(1)
    halo = canvas.beginText(x, y)
    halo.setFont(_LABEL_FONT, _LABEL_SIZE)
    halo.setTextRenderMode(1)
    halo.textOut(text)
    canvas.drawText(halo)
    canvas.restoreState()
    canvas.setFillColor(fill)
    canvas.setFont(_LABEL_FONT, _LABEL_SIZE)
    canvas.drawString(x, y, text)
    canvas.restoreState()


def _nice_length(max_m: float) -> float:
    """The largest 1, 2 or 5 times 10^k metres that is at most ``max_m``."""
    step = 10 ** math.floor(math.log10(max_m))
    for multiple in (5, 2, 1):
        if multiple * step <= max_m:
            return multiple * step
    return step


def _format_distance(metres: float) -> str:
    return f"{metres / 1000:g} km" if metres >= 1000 else f"{metres:g} m"


def _label_order(w: WellResult) -> tuple[bool, float]:
    """At-risk wells first, then by impact: they get first pick of spots."""
    return (w.well_status != WellStatus.AT_RISK, -(w.impact_fraction or 0.0))


class ResultsMap(Flowable):
    """The results map, ``width`` wide and ``width / MAP_ASPECT`` tall."""

    def __init__(
        self,
        result: AnalysisResult,
        basemap: Basemap | None,
        *,
        width: float,
    ) -> None:
        super().__init__()
        self.result = result
        self.basemap = basemap
        self.width = width
        self.height = width / MAP_ASPECT

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        return self.width, self.height

    def draw(self) -> None:
        canvas = self.canv
        frame = map_frame(self.result)
        scale = self.width / frame.width  # points per frame pixel

        def to_pt(lon: float, lat: float) -> tuple[float, float]:
            fx, fy = frame.to_frame(lon, lat)
            return fx * scale, self.height - fy * scale

        canvas.saveState()
        clip = canvas.beginPath()
        clip.rect(0, 0, self.width, self.height)
        canvas.clipPath(clip, stroke=0, fill=0)

        if self.basemap is not None:
            canvas.drawImage(
                ImageReader(io.BytesIO(self.basemap.jpeg)),
                0,
                0,
                self.width,
                self.height,
            )
        else:
            canvas.setFillColor(_NO_BASEMAP_BG)
            canvas.rect(0, 0, self.width, self.height, stroke=0, fill=1)

        inputs = self.result.inputs
        px, py = to_pt(inputs.pumping_lon, inputs.pumping_lat)
        self._draw_buffer(px, py, inputs.buffer_radius_m / frame.metres_per_px * scale)
        marks = self._draw_wells(to_pt)
        pump_boxes = self._draw_pumping_well(px, py)
        self._draw_labels(marks, pump_boxes)
        self._draw_north_arrow()
        self._draw_scale_bar(frame.metres_per_px / scale)
        canvas.restoreState()

        canvas.setStrokeColor(_BORDER_COLOUR)
        canvas.setLineWidth(0.5)
        canvas.rect(0, 0, self.width, self.height, stroke=1, fill=0)

    def _draw_buffer(self, x: float, y: float, radius: float) -> None:
        canvas = self.canv
        canvas.saveState()
        colour = _hex(BUFFER_COLOR)
        canvas.setStrokeColor(colour)
        canvas.setLineWidth(1 * _PT_PER_SCREEN_PX)
        canvas.setFillColor(colour)
        canvas.setFillAlpha(_BUFFER_FILL_ALPHA)
        canvas.circle(x, y, radius, stroke=1, fill=1)
        canvas.restoreState()

    def _draw_wells(
        self, to_pt: Callable[[float, float], tuple[float, float]]
    ) -> list[tuple[WellResult, float, float, float]]:
        """Draw every well marker; return ``(well, x, y, radius)`` for each.

        Largest markers first, so a small marker sitting on a big one
        stays visible on top of it.
        """
        wells = self.result.wells
        impacts = [w.impact_fraction for w in wells if w.impact_fraction is not None]
        max_impact = max(impacts) if impacts else 1.0
        marks = []
        for w in wells:
            lon, lat = to_wgs84(w.x_albers, w.y_albers)
            x, y = to_pt(lon, lat)
            radius = marker_radius_px(w, max_impact) * _PT_PER_SCREEN_PX
            marks.append((w, x, y, radius))

        canvas = self.canv
        for w, x, y, radius in sorted(marks, key=lambda m: -m[3]):
            if is_licensed(w.licence_status):
                canvas.saveState()
                canvas.setStrokeColor(_LICENSED_RING_COLOUR)
                canvas.setLineWidth(_LICENSED_RING_WEIGHT_PX * _PT_PER_SCREEN_PX)
                canvas.circle(
                    x,
                    y,
                    radius + _LICENSED_RING_GAP_PX * _PT_PER_SCREEN_PX,
                    stroke=1,
                    fill=0,
                )
                canvas.restoreState()
            colour = _hex(STATUS_COLOR.get(w.well_status, "#666666"))
            canvas.saveState()
            canvas.setStrokeColor(colour)
            canvas.setLineWidth(1 * _PT_PER_SCREEN_PX)
            canvas.setFillColor(colour)
            canvas.setFillAlpha(_MARKER_FILL_ALPHA)
            canvas.circle(x, y, radius, stroke=1, fill=1)
            canvas.restoreState()
        return marks

    def _draw_pumping_well(self, x: float, y: float) -> list[Box]:
        """Draw the pumping triangle and its label; return both boxes."""
        canvas = self.canv
        half_w = _PUMP_W_PX / 2 * _PT_PER_SCREEN_PX
        tall = _PUMP_H_PX * _PT_PER_SCREEN_PX
        inset = _PUMP_INSET_PX * _PT_PER_SCREEN_PX

        def triangle(left: float, right: float, bottom: float, top: float, fill) -> None:
            path = canvas.beginPath()
            path.moveTo(left, bottom)
            path.lineTo(right, bottom)
            path.lineTo((left + right) / 2, top)
            path.close()
            canvas.setFillColor(fill)
            canvas.drawPath(path, stroke=0, fill=1)

        canvas.saveState()
        triangle(x - half_w, x + half_w, y, y + tall, colors.white)
        triangle(
            x - half_w + inset,
            x + half_w - inset,
            y + inset,
            y + tall - inset,
            _hex(PUMPING_COLOR),
        )

        # "Pumping well" in a blue pill above the triangle, like the
        # live map's ``.pump-label``.
        text = "Pumping well"
        text_w = stringWidth(text, _LABEL_FONT, _LABEL_SIZE)
        pad_x, pad_y = 3.0, 2.0
        label = Box(
            x - text_w / 2 - pad_x,
            y + tall + 2,
            x + text_w / 2 + pad_x,
            y + tall + 2 + _LABEL_HEIGHT + 2 * pad_y,
        )
        canvas.setFillColor(_hex(PUMPING_COLOR))
        canvas.setFillAlpha(0.92)
        canvas.roundRect(
            label.x0,
            label.y0,
            label.x1 - label.x0,
            label.y1 - label.y0,
            2,
            stroke=0,
            fill=1,
        )
        canvas.setFillAlpha(1)
        canvas.setFillColor(colors.white)
        canvas.setFont(_LABEL_FONT, _LABEL_SIZE)
        canvas.drawString(label.x0 + pad_x, label.y0 + pad_y, text)
        canvas.restoreState()
        return [Box(x - half_w, y, x + half_w, y + tall), label]

    def _draw_labels(
        self,
        marks: list[tuple[WellResult, float, float, float]],
        obstacles: list[Box],
    ) -> None:
        """Well tag number beside every marker, placed by `place_labels`."""
        ordered = sorted(marks, key=lambda m: _label_order(m[0]))
        texts = [str(w.well_tag_number) for w, *_ in ordered]
        sizes = [
            (
                stringWidth(t, _LABEL_FONT, _LABEL_SIZE) + 2 * _HALO_PT,
                _LABEL_HEIGHT + 2 * _HALO_PT,
            )
            for t in texts
        ]
        boxes = place_labels(
            [(x, y, r) for _, x, y, r in ordered],
            sizes,
            obstacles=obstacles,
            bounds=Box(0, 0, self.width, self.height),
        )
        for text, box in zip(texts, boxes, strict=True):
            _halo_text(
                self.canv, box.x0 + _HALO_PT, box.y0 + _HALO_PT, text, _LABEL_COLOUR
            )

    def _draw_north_arrow(self) -> None:
        """A small north arrow in the top-left corner (Web Mercator: north is up)."""
        canvas = self.canv
        w, h = 14.0, 22.0
        x0, y0 = _INSET_PT, self.height - _INSET_PT - h
        canvas.saveState()
        canvas.setFillColor(_PANEL_BG)
        canvas.roundRect(x0, y0, w, h, 2, stroke=0, fill=1)
        cx = x0 + w / 2
        path = canvas.beginPath()
        path.moveTo(cx, y0 + h - 3)
        path.lineTo(cx + 4, y0 + h - 12)
        path.lineTo(cx, y0 + h - 10)
        path.lineTo(cx - 4, y0 + h - 12)
        path.close()
        canvas.setFillColor(colors.black)
        canvas.drawPath(path, stroke=0, fill=1)
        canvas.setFont("Helvetica-Bold", 6.5)
        canvas.drawCentredString(cx, y0 + 3, "N")
        canvas.restoreState()

    def _draw_scale_bar(self, metres_per_pt: float) -> None:
        """A two-segment scale bar in the bottom-left corner."""
        canvas = self.canv
        metres = _nice_length(0.2 * self.width * metres_per_pt)
        bar_w = metres / metres_per_pt
        bar_h = 3.0
        label = _format_distance(metres)
        x0, y0 = _INSET_PT, _INSET_PT
        pad = 4.0
        canvas.saveState()
        canvas.setFillColor(_PANEL_BG)
        canvas.roundRect(
            x0, y0, bar_w + 2 * pad, bar_h + 14, 2, stroke=0, fill=1
        )
        bx, by = x0 + pad, y0 + pad
        half = bar_w / 2
        canvas.setLineWidth(0.5)
        canvas.setStrokeColor(colors.black)
        canvas.setFillColor(colors.black)
        canvas.rect(bx, by, half, bar_h, stroke=1, fill=1)
        canvas.setFillColor(colors.white)
        canvas.rect(bx + half, by, half, bar_h, stroke=1, fill=1)
        canvas.setFillColor(colors.black)
        canvas.setFont("Helvetica", 6)
        text_y = by + bar_h + 2.5
        canvas.drawString(bx, text_y, "0")
        canvas.drawRightString(bx + bar_w, text_y, label)
        canvas.restoreState()


# --- Legend and caption --------------------------------------------------------

_STATUS_LABELS: Final[dict[WellStatus, str]] = {
    WellStatus.AT_RISK: "At risk",
    WellStatus.OK: "OK",
    WellStatus.INSUFFICIENT_DATA: "Insufficient data",
    WellStatus.SUSPECT_DATA: "Suspect data",
    WellStatus.OUTSIDE_VALIDITY: "Outside validity",
}
_LEGEND_FONT: Final[str] = "Helvetica"
_LEGEND_SIZE: Final[float] = 7.0
_LEGEND_TEXT: Final = colors.HexColor("#333333")
_LEGEND_SYMBOL_R: Final[float] = 3.5


class MapLegend(Flowable):
    """One-line key under the map: statuses, licence ring, pumping well, buffer."""

    _HEIGHT: Final[float] = 12.0

    def __init__(self, result: AnalysisResult, *, width: float) -> None:
        super().__init__()
        self.result = result
        self.width = width

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        return self.width, self._HEIGHT

    def _statuses(self) -> list[WellStatus]:
        # OUTSIDE_VALIDITY is not emitted by the pipeline today, so it
        # only earns a key entry when a well actually carries it.
        present = {w.well_status for w in self.result.wells}
        return [
            s
            for s in _STATUS_LABELS
            if s != WellStatus.OUTSIDE_VALIDITY or s in present
        ]

    def draw(self) -> None:
        canvas = self.canv
        r = _LEGEND_SYMBOL_R
        cy = self._HEIGHT / 2
        x = r

        def label(text: str) -> None:
            nonlocal x
            canvas.setFillColor(_LEGEND_TEXT)
            canvas.setFont(_LEGEND_FONT, _LEGEND_SIZE)
            canvas.drawString(x, cy - _LEGEND_SIZE * 0.35, text)
            x += stringWidth(text, _LEGEND_FONT, _LEGEND_SIZE) + 12 + r

        canvas.saveState()
        for status in self._statuses():
            colour = _hex(STATUS_COLOR[status])
            canvas.setStrokeColor(colour)
            canvas.setFillColor(colour)
            canvas.setFillAlpha(_MARKER_FILL_ALPHA)
            canvas.circle(x, cy, r, stroke=1, fill=1)
            canvas.setFillAlpha(1)
            x += r + 3
            label(_STATUS_LABELS[status])

        canvas.setStrokeColor(_LICENSED_RING_COLOUR)
        canvas.setLineWidth(1.2)
        canvas.circle(x, cy, r + 1.5, stroke=1, fill=0)
        x += r + 4
        label("Licensed well (dark ring)")

        pump = _hex(PUMPING_COLOR)
        path = canvas.beginPath()
        path.moveTo(x - r, cy - r)
        path.lineTo(x + r, cy - r)
        path.lineTo(x, cy + r)
        path.close()
        canvas.setFillColor(pump)
        canvas.drawPath(path, stroke=0, fill=1)
        x += r + 3
        label("Proposed pumping well")

        buffer_colour = _hex(BUFFER_COLOR)
        canvas.setStrokeColor(buffer_colour)
        canvas.setLineWidth(0.75)
        canvas.setFillColor(buffer_colour)
        canvas.setFillAlpha(0.1)
        canvas.circle(x, cy, r + 1, stroke=1, fill=1)
        canvas.setFillAlpha(1)
        x += r + 4
        label(f"Search buffer ({self.result.inputs.buffer_radius_m:,g} m)")
        canvas.restoreState()


def map_caption(result: AnalysisResult, basemap: Basemap | None) -> str:
    """Paragraph markup for the note under the map.

    The basemap credit is not part of it — see `basemap_credit`.
    """
    buffer_m = f"{result.inputs.buffer_radius_m:,g}"
    text = (
        f"Framed on the {buffer_m} m search buffer around the proposed "
        "pumping well. Marker colour shows each well's status and marker "
        "size its predicted impact; a dark ring marks a currently licensed "
        "well. Where well tag numbers would collide, they are moved beside "
        "their marker rather than left out."
    )
    if basemap is None:
        return text + (
            " <b>No basemap:</b> the background map could not be downloaded "
            "when this report was made, so the wells are drawn on a plain "
            "background. Their positions, the buffer and the scale bar are "
            "unaffected."
        )
    return text


def basemap_credit(basemap: Basemap | None) -> str | None:
    """Paragraph markup crediting the basemap, or ``None`` without one.

    Its own paragraph, set smaller and in italics by the PDF, so the
    attribution reads as a credit line rather than part of the note
    above it.
    """
    if basemap is None:
        return None
    source = basemap.source
    return html.escape(f"Basemap: Esri {source.name}. {source.attribution_text}")
