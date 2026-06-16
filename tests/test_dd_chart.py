"""Tests for the distance-drawdown chart figure.

Pins the inverted Y axis: drawdown grows downward (the hydrogeology
convention). The axis range is set explicitly (descending) rather than
via autorange="reversed" so the modebar "Reset axes" deterministically
restores the inverted view — see `dd_chart` for the tester report that
prompted this.
"""

from __future__ import annotations

from gwdrawdown.analysis import AnalysisInputs, AnalysisResult, _compute_well_result
from gwdrawdown.core.flagging import WellStatus
from gwdrawdown.ui.components.dd_chart import make_distance_drawdown_figure

PX, PY = 1_170_000.0, 418_000.0


def _result() -> AnalysisResult:
    row = {
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
    well = _compute_well_result(
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
        wells=[well],
        n_total=1,
        n_at_risk=0,
        n_ok=0,
        n_insufficient_data=0,
        n_suspect_data=0,
        n_outside_validity=0,
        max_drawdown_m=None,
    )


def test_y_axis_is_explicitly_reversed():
    fig = make_distance_drawdown_figure(_result())
    yaxis = fig.layout.yaxis
    # autorange disabled so the explicit range is honoured.
    assert yaxis.autorange is False
    # Descending range == inverted axis: larger drawdown sits lower.
    lo, hi = yaxis.range
    assert lo > hi
