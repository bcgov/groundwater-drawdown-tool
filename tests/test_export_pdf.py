"""Tests for `ui.components.export_pdf.build_pdf`.

The PDF layout itself is hard to assert on without a parser; these
tests pin the contract that matters: `build_pdf` returns a non-empty
PDF byte string for every input shape it must handle — with and
without chart images, with overrides, in manual-entry mode, and with
an empty well set.
"""

from __future__ import annotations

import base64

from reportlab.pdfbase.pdfmetrics import stringWidth

from gwdrawdown.analysis import AnalysisInputs, AnalysisResult, _compute_well_result
from gwdrawdown.core.flagging import WellStatus
from gwdrawdown.ui.components.export_pdf import (
    _AT_RISK_COLUMNS,
    _AT_RISK_WEIGHTS,
    _CONTENT_WIDTH,
    _PER_WELL_COLUMNS,
    _PER_WELL_WEIGHTS,
    _scaled_widths,
    _well_cell,
    build_pdf,
)
from gwdrawdown.ui.format_utils import NOT_DELINEATED_SUFFIX

PX, PY = 1_170_000.0, 418_000.0

# Smallest valid PNG — a 1x1 transparent pixel. Enough for reportlab's
# ImageReader to size and embed without pulling a real chart render in.
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0l"
    "EQVR42mNgAAIAAAUAAen63NgAAAAASUVORK5CYII="
)


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


def _compute(row: dict, **kwargs):
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
        **kwargs,
    )


def _inputs(*, manual: bool = False) -> AnalysisInputs:
    return AnalysisInputs(
        pumping_lon=-123.6,
        pumping_lat=48.7,
        pumping_x_albers=PX,
        pumping_y_albers=PY,
        source_aquifer_id=None if manual else 186,
        source_aquifer_name="Manual entry (Bedrock)" if manual else "Test Aquifer",
        source_subtype_code=None if manual else "4b",
        transmissivity_m2_per_day=1300.0,
        storativity=0.005,
        ts_overridden=manual,
        Q_value=3.97,
        Q_unit="L/s",
        Q_m3_per_day=343.008,
        duration_days=100.0,
        buffer_radius_m=1000.0,
        same_aquifer_filter=False,
        u_threshold=0.01,
        at_risk_fraction=0.30,
        manual_material="Bedrock" if manual else None,
    )


def _result(rows: list[dict], *, manual: bool = False, **kwargs) -> AnalysisResult:
    wells = [_compute(r, **kwargs) for r in rows]
    counts = {s: 0 for s in WellStatus}
    for w in wells:
        counts[w.well_status] += 1
    return AnalysisResult(
        inputs=_inputs(manual=manual),
        wells=wells,
        n_total=len(wells),
        n_at_risk=counts[WellStatus.AT_RISK],
        n_ok=counts[WellStatus.OK],
        n_insufficient_data=counts[WellStatus.INSUFFICIENT_DATA],
        n_suspect_data=counts[WellStatus.SUSPECT_DATA],
        n_outside_validity=counts[WellStatus.OUTSIDE_VALIDITY],
        max_drawdown_m=None,
    )


def _assert_is_pdf(data: object) -> None:
    assert isinstance(data, bytes)
    assert data.startswith(b"%PDF")
    assert len(data) > 1000  # a real document, not an empty shell


def test_per_well_column_weights_match_the_column_list() -> None:
    """Column spec and width weights must stay in lockstep.

    Adding a column without adding a weight (or vice versa) produces a
    colWidths list of the wrong length. The build tests below would
    catch it eventually, but with a far less obvious failure than this.
    """
    assert len(_PER_WELL_COLUMNS) == len(_PER_WELL_WEIGHTS)
    assert len(_AT_RISK_COLUMNS) == len(_AT_RISK_WEIGHTS)


def test_per_well_table_includes_licence_status() -> None:
    """Licence status reaches the filed report, not just the screen."""
    assert any(key == "licence_status" for _, key, _ in _PER_WELL_COLUMNS)


def test_aquifer_cell_marks_an_undelineated_aquifer() -> None:
    """The filed report says so too, not just the screen."""
    well = _compute(
        _row(AQUIFER_ID=1143), undelineated_aquifer_ids=frozenset({1143})
    )
    assert _well_cell(well, "aquifer_id", "") == "1143 (not delineated)"
    plain = _compute(_row(AQUIFER_ID=186))
    assert _well_cell(plain, "aquifer_id", "") == "186"


def test_aquifer_column_is_wide_enough_for_the_flag() -> None:
    """The Aq ID column has to fit the longest word of the marker.

    The per-well table is a fixed-width landscape grid, so a column
    narrower than its longest unbreakable word overflows into its
    neighbour rather than wrapping. This is the check behind the
    weights: Aq ID was widened at the expense of Use, whose values
    wrap anyway.
    """
    widths = _scaled_widths(_PER_WELL_WEIGHTS, _CONTENT_WIDTH)
    by_key = {
        key: w for (_, key, _), w in zip(_PER_WELL_COLUMNS, widths, strict=True)
    }
    # LEFTPADDING + RIGHTPADDING on every cell (see `_result_table`).
    padding = 6.0
    longest = max(
        NOT_DELINEATED_SUFFIX.split(),
        key=lambda word: stringWidth(word, "Helvetica", 5.5),
    )
    assert stringWidth(longest, "Helvetica", 5.5) < by_key["aquifer_id"] - padding
    # The column the width came out of still fits its own longest word.
    assert stringWidth("Industrial", "Helvetica", 5.5) < by_key[
        "intended_water_use"
    ] - padding


def test_build_pdf_with_an_undelineated_aquifer() -> None:
    """The wrapped marker must not break the document build."""
    pdf = build_pdf(
        _result(
            [_row(AQUIFER_ID=1143)],
            undelineated_aquifer_ids=frozenset({1143}),
        ),
        user="ANALYST1",
        version="0.4.0",
    )
    _assert_is_pdf(pdf)


def test_build_pdf_with_charts_returns_pdf_bytes() -> None:
    pdf = build_pdf(
        _result([_row(WELL_TAG_NUMBER=1), _row(WELL_TAG_NUMBER=2)]),
        user="ANALYST1",
        version="0.4.0",
        dd_chart_png=_TINY_PNG,
        impact_chart_png=_TINY_PNG,
    )
    _assert_is_pdf(pdf)


def test_build_pdf_without_charts_falls_back_cleanly() -> None:
    pdf = build_pdf(
        _result([_row()]),
        user="ANALYST1",
        version="0.4.0",
        dd_chart_png=None,
        impact_chart_png=None,
    )
    _assert_is_pdf(pdf)


def test_build_pdf_with_overrides() -> None:
    pdf = build_pdf(
        _result([_row()]),
        user="ANALYST1",
        version="0.4.0",
        overrides_by_wtn={12345: {"stickup_m": 1.0, "static_water_level_m": 8.0}},
    )
    _assert_is_pdf(pdf)


def test_build_pdf_in_manual_mode() -> None:
    pdf = build_pdf(
        _result([_row()], manual=True),
        user="ANALYST1",
        version="0.4.0",
    )
    _assert_is_pdf(pdf)


def test_build_pdf_with_empty_well_set() -> None:
    pdf = build_pdf(
        _result([]),
        user="ANALYST1",
        version="0.4.0",
    )
    _assert_is_pdf(pdf)
