"""Tests for `ui.components.export_kml.build_kml`.

Pins the KML structure (well-formed XML, one Placemark per well plus
the pumping well, per-status styling, ExtendedData rows) and the two
behaviours easy to get wrong: XML escaping of free-text fields and the
BC-Albers -> WGS84 coordinate conversion.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from gwdrawdown.analysis import AnalysisInputs, AnalysisResult, _compute_well_result
from gwdrawdown.core.flagging import WellStatus
from gwdrawdown.ui.components.export_kml import build_kml

PX, PY = 1_170_000.0, 418_000.0
_KML_NS = "{http://www.opengis.net/kml/2.2}"


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


def _inputs() -> AnalysisInputs:
    return AnalysisInputs(
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


def _result(rows: list[dict]) -> AnalysisResult:
    wells = [_compute(r) for r in rows]
    counts = {s: 0 for s in WellStatus}
    for w in wells:
        counts[w.well_status] += 1
    return AnalysisResult(
        inputs=_inputs(),
        wells=wells,
        n_total=len(wells),
        n_at_risk=counts[WellStatus.AT_RISK],
        n_ok=counts[WellStatus.OK],
        n_insufficient_data=counts[WellStatus.INSUFFICIENT_DATA],
        n_suspect_data=counts[WellStatus.SUSPECT_DATA],
        n_outside_validity=counts[WellStatus.OUTSIDE_VALIDITY],
        max_drawdown_m=None,
    )


def test_build_kml_is_wellformed_xml() -> None:
    kml = build_kml(_result([_row()]))
    # Raises if malformed — the assertion is that this does not throw.
    root = ET.fromstring(kml)
    assert root.tag == f"{_KML_NS}kml"


def test_kml_has_pumping_and_one_placemark_per_well() -> None:
    kml = build_kml(_result([_row(WELL_TAG_NUMBER=1), _row(WELL_TAG_NUMBER=2)]))
    root = ET.fromstring(kml)
    names = [el.text for el in root.iter(f"{_KML_NS}name")]
    assert "Proposed pumping well" in names
    assert "WTN 1" in names
    assert "WTN 2" in names
    placemarks = list(root.iter(f"{_KML_NS}Placemark"))
    assert len(placemarks) == 3  # pumping + two wells


def test_kml_wells_carry_inline_iconstyle() -> None:
    """Pumping + each well get an inline IconStyle with colour + scale."""
    kml = build_kml(_result([_row()]))
    root = ET.fromstring(kml)
    icon_styles = list(root.iter(f"{_KML_NS}IconStyle"))
    assert len(icon_styles) == 2  # pumping + one well
    for st in icon_styles:
        assert st.find(f"{_KML_NS}color") is not None
        assert st.find(f"{_KML_NS}scale") is not None


def test_kml_marker_scale_grows_with_impact() -> None:
    """Marker scale is proportional to predicted impact.

    A well close to the pumping point has a larger drawdown — and so
    a larger impact — than a far one, so it gets a bigger icon scale.
    """
    near = _row(WELL_TAG_NUMBER=1, X_ALBERS=PX + 60.0, Y_ALBERS=PY + 60.0)
    far = _row(WELL_TAG_NUMBER=2, X_ALBERS=PX + 900.0, Y_ALBERS=PY + 900.0)
    kml = build_kml(_result([near, far]))
    root = ET.fromstring(kml)
    # IconStyle order follows placemark order: pumping, then wells
    # sorted ascending by distance — pumping, near (WTN 1), far (WTN 2).
    icon_scales = [
        float(st.find(f"{_KML_NS}scale").text)
        for st in root.iter(f"{_KML_NS}IconStyle")
    ]
    assert icon_scales[1] > icon_scales[2]  # near well bigger than far


def test_kml_placemark_carries_extended_data() -> None:
    kml = build_kml(_result([_row()]))
    root = ET.fromstring(kml)
    data_names = {
        el.get("name") for el in root.iter(f"{_KML_NS}Data")
    }
    assert {"WTN", "Distance (m)", "SAD (m)", "Status"} <= data_names


def test_kml_carries_licence_status_with_null_as_unknown() -> None:
    """Licence status reaches Google Earth, and NULL is not left blank."""
    kml = build_kml(_result([_row(LICENCE_STATUS="Licensed")]))
    root = ET.fromstring(kml)
    values = {
        el.get("name"): (el.findtext(f"{_KML_NS}value") or "")
        for el in root.iter(f"{_KML_NS}Data")
    }
    assert values["Licence Status"] == "Licensed"

    kml = build_kml(_result([_row(LICENCE_STATUS=None)]))
    root = ET.fromstring(kml)
    values = {
        el.get("name"): (el.findtext(f"{_KML_NS}value") or "")
        for el in root.iter(f"{_KML_NS}Data")
    }
    assert values["Licence Status"] == "Unknown"


def test_kml_escapes_free_text_fields() -> None:
    kml = build_kml(_result([_row(INTENDED_WATER_USE="Commercial & Industrial")]))
    assert "Commercial &amp; Industrial" in kml
    assert "Commercial & Industrial" not in kml
    # Still parses.
    ET.fromstring(kml)


def test_kml_pumping_coordinates_are_wgs84_lonlat() -> None:
    kml = build_kml(_result([_row()]))
    root = ET.fromstring(kml)
    coords = [el.text for el in root.iter(f"{_KML_NS}coordinates")]
    # Pumping placemark is emitted first; its coords echo the inputs.
    lon, lat, _alt = coords[0].split(",")
    assert float(lon) == -123.6
    assert float(lat) == 48.7


def test_kml_well_coordinates_fall_in_bc_lonlat_range() -> None:
    kml = build_kml(_result([_row()]))
    root = ET.fromstring(kml)
    # Second coordinate set is the observation well (Albers -> WGS84).
    coords = [el.text for el in root.iter(f"{_KML_NS}coordinates")]
    lon, lat, _alt = coords[1].split(",")
    assert -140.0 < float(lon) < -114.0
    assert 48.0 < float(lat) < 60.0


def test_kml_edited_field_reflects_overrides() -> None:
    result = _result([_row()])
    kml = build_kml(result, overrides_by_wtn={12345: {"stickup_m": 1.5}})
    root = ET.fromstring(kml)
    edited = next(
        el.find(f"{_KML_NS}value").text
        for el in root.iter(f"{_KML_NS}Data")
        if el.get("name") == "Edited"
    )
    assert edited == "Stickup"


def test_kml_handles_empty_well_set() -> None:
    kml = build_kml(_result([]))
    root = ET.fromstring(kml)
    # Pumping placemark still present; no well placemarks.
    assert len(list(root.iter(f"{_KML_NS}Placemark"))) == 1
