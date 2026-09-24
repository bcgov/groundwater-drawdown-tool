"""Tests for `ui.components.export_pdf_map` — the PDF report's map page.

Pins the framing (centred on the pumping well, the whole buffer in
view, zoom following the buffer size), the basemap fetch (stitched to
exactly the frame, all or nothing, one retry, never a network call in
tests), the basemap choice, and label placement (collisions avoided
where possible, no label ever dropped).
"""

from __future__ import annotations

import io
import math

import pytest
from PIL import Image

from gwdrawdown.analysis import AnalysisInputs, AnalysisResult, _compute_well_result
from gwdrawdown.core.flagging import WellStatus
from gwdrawdown.ui.components import basemaps
from gwdrawdown.ui.components.export_pdf_map import (
    _TARGET_HEIGHT_PX,
    MAP_ASPECT,
    Basemap,
    Box,
    _format_distance,
    _nice_length,
    _world_px,
    basemap_credit,
    basemap_source_for,
    fetch_basemap,
    map_caption,
    map_frame,
    place_labels,
)
from gwdrawdown.ui.components.tile_sources import (
    ESRI_IMAGERY,
    ESRI_STREETS,
    ESRI_TOPO,
)

PX, PY = 1_170_000.0, 418_000.0


def _row(**overrides) -> dict:
    base = {
        "WELL_TAG_NUMBER": 12345,
        "AQUIFER_ID": 186,
        "FINISHED_WELL_DEPTH": 100.0,
        "TOTAL_DEPTH_DRILLED": None,
        "BEDROCK_DEPTH": None,
        "STATIC_WATER_LEVEL": 30.0,
        "YIELD": 30.0,
        "WELL_CLASS": "Water Supply",
        "INTENDED_WATER_USE": "Private Domestic",
        "LICENCE_STATUS": "Unlicensed",
        "WELL_DETAILS_URL": "https://apps.nrs.gov.bc.ca/gwells/well/12345",
        "AQUIFER_MATERIAL": "Unconsolidated",
        "X_ALBERS": 1_170_500.0,
        "Y_ALBERS": 418_500.0,
    }
    base.update(overrides)
    return base


def _result(rows: list[dict], *, buffer_m: float = 1000.0) -> AnalysisResult:
    wells = [
        _compute_well_result(
            r,
            pumping_x=PX,
            pumping_y=PY,
            transmissivity_m2_per_day=1300.0,
            storativity=0.005,
            Q_m3_per_day=343.008,
            duration_days=100.0,
            u_threshold=0.01,
            at_risk_fraction=0.30,
        )
        for r in rows
    ]
    counts = {s: 0 for s in WellStatus}
    for w in wells:
        counts[w.well_status] += 1
    inputs = AnalysisInputs(
        pumping_lon=-123.6,
        pumping_lat=48.7,
        pumping_x_albers=PX,
        pumping_y_albers=PY,
        source_aquifer_id=186,
        source_aquifer_name="Test Aquifer",
        source_subtype_code="4b",
        transmissivity_m2_per_day=1300.0,
        storativity=0.005,
        ts_overridden=False,
        Q_value=3.97,
        Q_unit="L/s",
        Q_m3_per_day=343.008,
        duration_days=100.0,
        buffer_radius_m=buffer_m,
        same_aquifer_filter=False,
        u_threshold=0.01,
        at_risk_fraction=0.30,
    )
    return AnalysisResult(
        inputs=inputs,
        wells=wells,
        n_total=len(wells),
        n_at_risk=counts[WellStatus.AT_RISK],
        n_ok=counts[WellStatus.OK],
        n_insufficient_data=counts[WellStatus.INSUFFICIENT_DATA],
        n_suspect_data=counts[WellStatus.SUSPECT_DATA],
        n_outside_validity=counts[WellStatus.OUTSIDE_VALIDITY],
        max_drawdown_m=None,
    )


def _png_tile(colour: str = "#88aacc") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (256, 256), colour).save(buffer, "PNG")
    return buffer.getvalue()


# --- Framing -------------------------------------------------------------


def test_world_px_matches_web_mercator() -> None:
    """Null Island sits mid-world; the antimeridian at the left edge."""
    assert _world_px(0.0, 0.0, 0) == pytest.approx((128.0, 128.0))
    x, _ = _world_px(-180.0, 0.0, 3)
    assert x == pytest.approx(0.0)
    # Northern latitudes sit in the top half (y grows downward).
    _, y = _world_px(-123.6, 48.7, 0)
    assert y < 128.0


def test_map_frame_is_centred_on_the_pumping_well() -> None:
    frame = map_frame(_result([]))
    fx, fy = frame.to_frame(-123.6, 48.7)
    assert fx == pytest.approx(frame.width / 2)
    assert fy == pytest.approx(frame.height / 2)
    assert frame.width / frame.height == pytest.approx(MAP_ASPECT)


@pytest.mark.parametrize("buffer_m", [150.0, 1000.0, 5000.0, 20000.0])
def test_map_frame_shows_the_whole_buffer(buffer_m: float) -> None:
    frame = map_frame(_result([], buffer_m=buffer_m))
    diameter_px = 2 * buffer_m / frame.metres_per_px
    assert diameter_px < frame.height


def test_map_frame_zoom_follows_the_buffer_size() -> None:
    zooms = [
        map_frame(_result([], buffer_m=b)).zoom for b in (150.0, 1000.0, 5000.0)
    ]
    assert zooms[0] > zooms[1] > zooms[2]


def test_map_frame_resolution_stays_near_target() -> None:
    """A whole-number zoom lands the height within √2 of the target."""
    for buffer_m in (300.0, 1000.0, 2500.0, 8000.0):
        frame = map_frame(_result([], buffer_m=buffer_m))
        assert _TARGET_HEIGHT_PX / math.sqrt(2) <= frame.height
        assert frame.height <= _TARGET_HEIGHT_PX * math.sqrt(2)


def test_map_frame_zoom_is_clamped() -> None:
    assert map_frame(_result([], buffer_m=1.0)).zoom == 18
    assert map_frame(_result([], buffer_m=50_000_000.0)).zoom == 1


# --- Basemap fetch --------------------------------------------------------


def test_esri_tile_url_puts_y_before_x() -> None:
    """Esri's pattern is {z}/{y}/{x} — the reverse of OSM's."""
    url = ESRI_STREETS.tile_url(12, 650, 1405)
    assert url.endswith("/World_Street_Map/MapServer/tile/12/1405/650")
    assert ESRI_STREETS.attribution_text.startswith("Tiles © Esri — ")


def test_fetch_basemap_stitches_exactly_the_frame() -> None:
    result = _result([_row()])
    frame = map_frame(result)
    urls: list[str] = []

    def get(url: str) -> bytes:
        urls.append(url)
        return _png_tile()

    basemap = fetch_basemap(result, ESRI_TOPO, get=get)
    assert basemap is not None
    assert basemap.source is ESRI_TOPO
    image = Image.open(io.BytesIO(basemap.jpeg))
    assert image.format == "JPEG"
    assert image.size == (round(frame.width), round(frame.height))
    # Every tile the frame touches, each fetched once, all at its zoom.
    expected_cols = math.floor((frame.left + frame.width) / 256) - math.floor(
        frame.left / 256
    ) + 1
    expected_rows = math.floor((frame.top + frame.height) / 256) - math.floor(
        frame.top / 256
    ) + 1
    assert len(urls) == len(set(urls)) == expected_cols * expected_rows
    assert all(f"/World_Topo_Map/MapServer/tile/{frame.zoom}/" in u for u in urls)


def test_fetch_basemap_is_all_or_nothing() -> None:
    """One tile that keeps failing means no basemap, not a holed one."""
    result = _result([])
    frame = map_frame(result)
    bad = ESRI_STREETS.tile_url(
        frame.zoom, math.floor(frame.left / 256), math.floor(frame.top / 256)
    )

    def get(url: str) -> bytes:
        if url == bad:
            raise OSError("tile server error")
        return _png_tile()

    assert fetch_basemap(result, ESRI_STREETS, get=get) is None


def test_fetch_basemap_returns_none_when_offline() -> None:
    def get(url: str) -> bytes:
        raise OSError("network unreachable")

    assert fetch_basemap(_result([]), ESRI_STREETS, get=get) is None


def test_fetch_basemap_retries_a_failed_tile_once() -> None:
    seen: set[str] = set()

    def get(url: str) -> bytes:
        if url not in seen:
            seen.add(url)
            raise TimeoutError("first attempt times out")
        return _png_tile()

    assert fetch_basemap(_result([]), ESRI_STREETS, get=get) is not None


def test_basemap_follows_the_results_map_choice() -> None:
    assert basemap_source_for(basemaps.TOPO_NAME) is ESRI_TOPO
    assert basemap_source_for(basemaps.IMAGERY_NAME) is ESRI_IMAGERY
    # OpenStreetMap cannot be fetched server-side; nor is anything
    # picked before the officer first touches the layer control.
    assert basemap_source_for(basemaps.OSM_NAME) is ESRI_STREETS
    assert basemap_source_for(None) is ESRI_STREETS


# --- Labels ---------------------------------------------------------------


def test_lone_label_sits_above_its_marker() -> None:
    [box] = place_labels([(100.0, 100.0, 5.0)], [(20.0, 6.0)])
    assert box.y0 > 105.0
    assert (box.x0 + box.x1) / 2 == pytest.approx(100.0)


def test_labels_of_coincident_wells_do_not_overlap() -> None:
    boxes = place_labels(
        [(100.0, 100.0, 5.0), (100.0, 100.0, 5.0)], [(20.0, 6.0), (20.0, 6.0)]
    )
    assert boxes[0].overlap(boxes[1]) == 0.0


def test_no_label_is_ever_dropped() -> None:
    """Even when every spot collides, each marker keeps its label."""
    marks = [(100.0, 100.0, 5.0)] * 12
    boxes = place_labels(marks, [(20.0, 6.0)] * 12)
    assert len(boxes) == 12


def test_label_stays_inside_the_map() -> None:
    """A marker at the top edge puts its label below instead."""
    [box] = place_labels(
        [(100.0, 198.0, 5.0)], [(20.0, 6.0)], bounds=Box(0, 0, 400, 200)
    )
    assert box.y1 <= 200.0


def test_label_avoids_an_obstacle() -> None:
    [box] = place_labels(
        [(100.0, 100.0, 5.0)], [(20.0, 6.0)], obstacles=[Box(80, 104, 120, 120)]
    )
    assert box.overlap(Box(80, 104, 120, 120)) == 0.0


# --- Scale bar and caption -------------------------------------------------


def test_scale_bar_uses_round_lengths() -> None:
    assert _nice_length(730.0) == 500.0
    assert _nice_length(2100.0) == 2000.0
    assert _nice_length(99.0) == 50.0
    assert _nice_length(1000.0) == 1000.0
    assert _format_distance(500.0) == "500 m"
    assert _format_distance(2000.0) == "2 km"


def test_basemap_credit_is_kept_out_of_the_caption() -> None:
    """The credit is its own line, not mixed into the map note."""
    basemap = Basemap(jpeg=b"", source=ESRI_STREETS)
    caption = map_caption(_result([]), basemap)
    assert "1,000 m" in caption
    assert "Esri" not in caption
    credit = basemap_credit(basemap)
    assert credit is not None
    assert credit.startswith("Basemap: Esri Streets.")
    assert "OpenStreetMap contributors" in credit
    assert "&copy;" not in credit


def test_caption_explains_a_missing_basemap() -> None:
    assert "No basemap" in map_caption(_result([]), None)
    assert basemap_credit(None) is None
