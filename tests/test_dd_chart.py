"""Tests for the distance-drawdown chart figure.

Pins the inverted Y axis: drawdown grows downward (the hydrogeology
convention). The axis range is set explicitly (descending) rather than
via autorange="reversed" so the modebar "Reset axes" deterministically
restores the inverted view — see `dd_chart` for the tester report that
prompted this.

Also pins the SAD-bar split (orange where headroom remains, red where
predicted drawdown has exceeded SAD) and the presence of the 0 m
reference line, both added after the July 2026 testing round.
"""

from __future__ import annotations

from gwdrawdown.analysis import AnalysisInputs, AnalysisResult, _compute_well_result
from gwdrawdown.ui.components.dd_chart import (
    _sad_segment_arrays,
    make_distance_drawdown_figure,
)

PX, PY = 1_170_000.0, 418_000.0


def _well(**row_overrides):
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
    row.update(row_overrides)
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


def _result() -> AnalysisResult:
    well = _well()
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


def test_y_range_always_contains_zero():
    """The 0 m reference line needs somewhere to sit.

    Every plotted drawdown is positive, so a range derived only from
    the data would put y=0 outside the visible area and `add_hline`
    would silently draw nothing.
    """
    fig = make_distance_drawdown_figure(_result())
    bottom, top = fig.layout.yaxis.range
    assert top <= 0.0 <= bottom


def test_zero_reference_line_is_drawn():
    fig = make_distance_drawdown_figure(_result())
    zero_lines = [
        s for s in fig.layout.shapes if s.type == "line" and s.y0 == 0 and s.y1 == 0
    ]
    assert len(zero_lines) == 1


class _FakeWell:
    """Minimal stand-in — `_sad_segment_arrays` only reads three fields."""

    def __init__(self, distance_m, drawdown_m, sad_m):
        self.distance_m = distance_m
        self.drawdown_m = drawdown_m
        self.sad_m = sad_m


def test_sad_bars_split_by_whether_drawdown_exceeds_sad():
    """Orange = headroom remains, red = over-impacted.

    The two traces must partition the wells: a well belongs to exactly
    one of them, so no bar is drawn twice or dropped.
    """
    headroom = _FakeWell(100.0, 2.0, 10.0)  # SAD deeper -> bar hangs down
    exceeded = _FakeWell(200.0, 15.0, 3.0)  # drawdown deeper -> bar runs up

    ok_x, _ = _sad_segment_arrays([headroom, exceeded], exceeded=False)
    bad_x, _ = _sad_segment_arrays([headroom, exceeded], exceeded=True)

    assert ok_x[0] == 100.0
    assert bad_x[0] == 200.0
    assert len(ok_x) == 3  # two endpoints + None gap
    assert len(bad_x) == 3


def test_sad_bar_exactly_at_sad_counts_as_exceeded():
    """Boundary: drawdown == SAD is 100% impact, i.e. at risk."""
    at_limit = _FakeWell(50.0, 7.0, 7.0)
    assert _sad_segment_arrays([at_limit], exceeded=True)[0] == [50.0, 50.0, None]
    assert _sad_segment_arrays([at_limit], exceeded=False)[0] == []


def test_wells_without_usable_sad_are_skipped_by_both_traces():
    """No SAD (or a non-positive one) means there is no bar to draw."""
    no_sad = _FakeWell(10.0, 1.0, None)
    bad_sad = _FakeWell(20.0, 1.0, -4.0)
    wells = [no_sad, bad_sad]
    assert _sad_segment_arrays(wells, exceeded=False)[0] == []
    assert _sad_segment_arrays(wells, exceeded=True)[0] == []
