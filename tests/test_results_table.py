"""Tests for the per-well table's row projection.

`make_per_well_rows` is the single source of the cells the officer
reads on screen *and* of the CSV export (which serialises the table's
own rows), so a wrong cell here is wrong in two places at once. These
cases cover the Aquifer ID cell, whose three states — a plain number,
a number marked as not delineated, and no aquifer at all — must stay
distinguishable.
"""

from __future__ import annotations

from gwdrawdown.analysis import (
    AnalysisInputs,
    AnalysisResult,
    WellResult,
    _compute_well_result,
)
from gwdrawdown.core.flagging import WellStatus
from gwdrawdown.ui.components.results_table import _FULL_COLUMNS, make_per_well_rows

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


def _compute(row: dict, **kwargs) -> WellResult:
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


def _rows_for(wells: list[WellResult]) -> list[dict]:
    counts = {s: 0 for s in WellStatus}
    for w in wells:
        counts[w.well_status] += 1
    result = AnalysisResult(
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
    return make_per_well_rows(
        result,
        base_wells_by_wtn={w.well_tag_number: w for w in wells},
        overrides_by_wtn={},
    )


def test_delineated_aquifer_cell_is_just_the_number() -> None:
    (row,) = _rows_for([_compute(_row(AQUIFER_ID=186))])
    assert row["aquifer_id"] == "186"


def test_undelineated_aquifer_cell_carries_the_marker() -> None:
    (row,) = _rows_for(
        [_compute(_row(AQUIFER_ID=1143), undelineated_aquifer_ids=frozenset({1143}))]
    )
    assert row["aquifer_id"] == "1143 (not delineated)"


def test_well_with_no_aquifer_gets_a_blank_cell() -> None:
    """Blank, not "None" and not "0" — GWELLS assigns it no aquifer."""
    (row,) = _rows_for([_compute(_row(AQUIFER_ID=None))])
    assert row["aquifer_id"] == ""


def test_aquifer_column_is_declared_text() -> None:
    """The marker makes the cell a string, so the column must say so.

    Leaving it ``numeric`` would have dash_table trying to sort and
    filter "1143 (not delineated)" as a number.
    """
    spec = {cid: ctype for cid, _, ctype in _FULL_COLUMNS}
    assert spec["aquifer_id"] == "text"
