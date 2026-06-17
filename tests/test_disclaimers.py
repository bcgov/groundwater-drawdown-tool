"""Disclaimer placement rules (client direction, 2026-06).

Two invariants the client cares about:

- The **interpretation** disclaimer (results must be interpreted by a
  hydrogeologist / Qualified Professional) appears on every exported
  artifact AND on the tool UI.
- The **internal-use** notice (the tool itself must not be shared
  outside the organization) appears on the tool UI ONLY — never on an
  exported artifact, because a screening output may legitimately leave
  the org as part of a licence file.

These tests pin both so a future edit can't silently leak the
internal-use line into an export or drop the interpretation caveat.
"""

from __future__ import annotations

from typing import Any

from gwdrawdown.analysis import AnalysisInputs, AnalysisResult, _compute_well_result
from gwdrawdown.core.flagging import WellStatus
from gwdrawdown.ui import disclaimers
from gwdrawdown.ui.components.export_html_map import build_html_map
from gwdrawdown.ui.components.export_kml import build_kml
from gwdrawdown.ui.components.export_pdf import build_pdf
from gwdrawdown.ui.components.footer import make_footer

PX, PY = 1_170_000.0, 418_000.0

# A fragment of the interpretation wording distinctive enough that its
# presence proves the full disclaimer made it onto the surface.
_INTERPRETATION_FRAGMENT = "Qualified Professional"


def _row() -> dict:
    return {
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


def _result() -> AnalysisResult:
    well = _compute_well_result(
        _row(),
        pumping_x=PX,
        pumping_y=PY,
        transmissivity_m2_per_day=1300.0,
        storativity=0.005,
        Q_m3_per_day=343.008,
        duration_days=100.0,
        u_threshold=0.01,
        at_risk_fraction=0.30,
    )
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
    counts = {s: 0 for s in WellStatus}
    counts[well.well_status] += 1
    return AnalysisResult(
        inputs=inputs,
        wells=[well],
        n_total=1,
        n_at_risk=counts[WellStatus.AT_RISK],
        n_ok=counts[WellStatus.OK],
        n_insufficient_data=counts[WellStatus.INSUFFICIENT_DATA],
        n_suspect_data=counts[WellStatus.SUSPECT_DATA],
        n_outside_validity=counts[WellStatus.OUTSIDE_VALIDITY],
        max_drawdown_m=well.drawdown_m,
    )


def test_constants_are_distinct_and_nonempty() -> None:
    assert _INTERPRETATION_FRAGMENT in disclaimers.INTERPRETATION_FULL
    assert _INTERPRETATION_FRAGMENT in disclaimers.INTERPRETATION_BANNER
    assert "internal use only" in disclaimers.INTERNAL_USE
    # The internal-use line shares no distinctive phrase with the
    # interpretation text, so a substring test can't confuse them.
    assert _INTERPRETATION_FRAGMENT not in disclaimers.INTERNAL_USE


def test_kml_carries_interpretation_not_internal_use() -> None:
    kml = build_kml(_result())
    assert _INTERPRETATION_FRAGMENT in kml
    assert disclaimers.INTERNAL_USE not in kml


def test_html_map_carries_interpretation_not_internal_use() -> None:
    html_doc = build_html_map(_result())
    assert _INTERPRETATION_FRAGMENT in html_doc
    assert disclaimers.INTERNAL_USE not in html_doc


def test_pdf_does_not_carry_internal_use() -> None:
    """Negative-only: PDF text streams may be compressed, so absence is
    the reliable assertion (a present string could be hidden by zlib,
    but an absent one is genuinely absent)."""
    pdf_bytes = build_pdf(
        _result(),
        user="tester",
        version="0.0.0-test",
        overrides_by_wtn={},
        dd_chart_png=None,
        impact_chart_png=None,
    )
    assert disclaimers.INTERNAL_USE.encode("utf-8") not in pdf_bytes


def _all_strings(component: Any) -> list[str]:
    """Collect every string in a Dash component's children tree."""
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            found.append(node)
            return
        if isinstance(node, (list, tuple)):
            for child in node:
                walk(child)
            return
        children = getattr(node, "children", None)
        if children is not None:
            walk(children)

    walk(component)
    return found


def test_footer_carries_both_disclaimers() -> None:
    strings = _all_strings(make_footer())
    assert disclaimers.INTERPRETATION_BANNER in strings
    assert disclaimers.INTERNAL_USE in strings
