"""Tests for `ui.components.export_html_map.build_html_map`.

The output is a self-contained HTML file; these tests pin the shape
that matters — a complete document, the Leaflet include, and a JSON
payload carrying the pumping point plus one entry per well.
"""

from __future__ import annotations

import json
import re

from gwdrawdown.analysis import AnalysisInputs, AnalysisResult, _compute_well_result
from gwdrawdown.core.flagging import WellStatus
from gwdrawdown.ui.components.export_html_map import build_html_map

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


def _compute(row: dict):
    return _compute_well_result(
        row,
        pumping_x=PX,
        pumping_y=PY,
        transmissivity_m2_per_day=1300.0,
        storativity=0.005,
        Q_m3_per_day=343.008,
        duration_days=100.0,
        u_threshold=0.01,
        at_risk_fraction=0.30,
    )


def _result(rows: list[dict]) -> AnalysisResult:
    wells = [_compute(r) for r in rows]
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
        buffer_radius_m=1000.0,
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


def _payload(html: str) -> dict:
    """Extract the embedded ``var DATA = {...};`` JSON object."""
    match = re.search(r"var DATA = (\{.*?\});", html, re.DOTALL)
    assert match, "embedded DATA payload not found"
    return json.loads(match.group(1))


def test_build_html_map_is_a_complete_document() -> None:
    html = build_html_map(_result([_row()]))
    assert html.startswith("<!DOCTYPE html>")
    assert "leaflet@1.9.4" in html
    assert "</html>" in html.strip()


def test_html_map_payload_has_pumping_and_one_entry_per_well() -> None:
    html = build_html_map(_result([_row(WELL_TAG_NUMBER=1), _row(WELL_TAG_NUMBER=2)]))
    data = _payload(html)
    assert data["pumping"]["lat"] == 48.7
    assert data["pumping"]["lon"] == -123.6
    assert data["pumping"]["buffer"] == 1000.0
    assert {w["wtn"] for w in data["wells"]} == {1, 2}


def test_html_map_well_entry_carries_status_colour_and_radius() -> None:
    html = build_html_map(_result([_row()]))
    well = _payload(html)["wells"][0]
    assert well["color"].startswith("#")
    assert 6.0 <= well["radius"] <= 18.0
    assert well["status"] in {s.value for s in WellStatus}


def test_html_map_well_coordinates_are_wgs84() -> None:
    html = build_html_map(_result([_row()]))
    well = _payload(html)["wells"][0]
    assert -140.0 < well["lon"] < -114.0
    assert 48.0 < well["lat"] < 60.0


def test_html_map_handles_empty_well_set() -> None:
    html = build_html_map(_result([]))
    data = _payload(html)
    assert data["wells"] == []
    assert html.startswith("<!DOCTYPE html>")
