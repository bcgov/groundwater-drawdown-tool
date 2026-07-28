"""Disclaimer and guidance placement rules (client direction).

Invariants the client cares about:

- The **interpretation** disclaimer (results must be interpreted by a
  hydrogeologist / Qualified Professional) appears on every exported
  artifact AND on the tool UI.
- The **internal-use** notice (the tool itself must not be shared
  outside the organization) appears on the tool UI ONLY — never on an
  exported artifact, because a screening output may legitimately leave
  the org as part of a licence file.
- The **method guidance** (2026-07) is split up on the tool UI so each
  paragraph sits next to the control it is about, but the PDF carries
  all of it in one section — that artifact has to stand alone for a
  reader who never saw the screen.

These tests pin all three so a future edit can't silently leak the
internal-use line into an export, drop the interpretation caveat, or
define a guidance paragraph that never reaches a surface.
"""

from __future__ import annotations

from typing import Any

import pytest

from gwdrawdown.analysis import AnalysisInputs, AnalysisResult, _compute_well_result
from gwdrawdown.app import create_app
from gwdrawdown.core.flagging import WellStatus
from gwdrawdown.ui import disclaimers
from gwdrawdown.ui.components import export_pdf
from gwdrawdown.ui.components.export_html_map import build_html_map
from gwdrawdown.ui.components.export_kml import build_kml
from gwdrawdown.ui.components.export_pdf import build_pdf
from gwdrawdown.ui.components.footer import make_footer
from gwdrawdown.ui.components.results_table import build_per_well_section

PX, PY = 1_170_000.0, 418_000.0


@pytest.fixture(scope="module")
def results_page():
    """Import the page module via ``create_app``.

    Page modules call ``dash.register_page`` at import time, which needs
    a pages-enabled Dash app to exist first — same pattern as
    ``test_results_page_cache``.
    """
    create_app()
    from gwdrawdown.ui.pages import results_page as rp

    return rp


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


# --- Method guidance (client wording, 2026-07) ------------------------------


def test_method_guidance_covers_every_paragraph() -> None:
    """`METHOD_GUIDANCE` is what the PDF and the results panel iterate.

    A paragraph defined but left out of the tuple would silently never
    be shown anywhere.
    """
    assert disclaimers.METHOD_GUIDANCE == (
        disclaimers.ANALYTICAL_SOLUTION,
        disclaimers.AQUIFER_DEFAULTS,
        disclaimers.SENSITIVITY_ANALYSIS,
        disclaimers.VERIFY_SOURCES,
        disclaimers.CONTACT_HYDROGEOLOGIST,
    )
    assert all(len(p) > 80 for p in disclaimers.METHOD_GUIDANCE)


def test_threshold_explanation_tracks_the_configured_fraction() -> None:
    """The wording quotes the real threshold, not a hardcoded 30%."""
    text = disclaimers.at_risk_threshold_explanation(0.30)
    assert "30% threshold" in text
    assert "equal to 30% of the calculated Safe Available Drawdown" in text

    # If the threshold is ever retuned, the sentence follows it.
    retuned = disclaimers.at_risk_threshold_explanation(0.25)
    assert "25% threshold" in retuned
    assert "30%" not in retuned


def test_results_page_method_panel_carries_all_guidance(results_page) -> None:
    """The on-screen panel shows the guidance not tied to one control."""
    strings = _all_strings(results_page._method_panel())
    assert disclaimers.ANALYTICAL_SOLUTION in strings
    assert disclaimers.SENSITIVITY_ANALYSIS in strings
    assert disclaimers.CONTACT_HYDROGEOLOGIST in strings
    assert any("threshold indicates" in s for s in strings)


def test_per_well_table_carries_the_verify_sources_guidance() -> None:
    """`VERIFY_SOURCES` sits with the GWELLS links, not in the panel."""
    strings = _all_strings(build_per_well_section())
    assert disclaimers.VERIFY_SOURCES in strings


def test_pdf_method_section_includes_every_guidance_paragraph() -> None:
    """The PDF stands alone for a reader who never saw the screen.

    Asserted on `_method_text` rather than the rendered bytes because
    PDF text streams are compressed — see
    `test_pdf_does_not_carry_internal_use`.
    """
    paragraphs = export_pdf._method_text(0.01, 0.30)
    for guidance in disclaimers.METHOD_GUIDANCE:
        assert guidance in paragraphs
    assert any("threshold indicates" in p for p in paragraphs)
