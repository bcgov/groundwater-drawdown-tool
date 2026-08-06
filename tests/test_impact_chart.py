"""Tests for the Impact-% chart's WTN labelling (item 3d).

The reported defect: the chart drew every bar but only some of the
y-axis labels, because Plotly thins category ticks once bars are
squeezed. A bar you cannot name is not much use on a licence file, so
where there is room every WTN is now forced onto the axis, and where
there genuinely is not, the caption says so rather than leaving the
reader to assume the axis is complete.
"""

from __future__ import annotations

import pytest

from gwdrawdown.analysis import AnalysisInputs, AnalysisResult, _compute_well_result
from gwdrawdown.core.flagging import WellStatus
from gwdrawdown.ui.components.impact_chart import (
    _CHART_CHROME_PX,
    _MAX_CHART_HEIGHT,
    _MIN_LABELLED_BAR_PX,
    _chart_height,
    _wtn_axis_settings,
    make_impact_chart,
)

PX, PY = 1_170_000.0, 418_000.0

# Wells past this count cannot all be labelled at the height cap.
_LABEL_CAPACITY = int((_MAX_CHART_HEIGHT - _CHART_CHROME_PX) / _MIN_LABELLED_BAR_PX)


def _well(wtn: int, distance_m: float):
    return _compute_well_result(
        {
            "WELL_TAG_NUMBER": wtn,
            "AQUIFER_ID": 186,
            "FINISHED_WELL_DEPTH": 100.0,
            "TOTAL_DEPTH_DRILLED": None,
            "BEDROCK_DEPTH": None,
            "STATIC_WATER_LEVEL": 30.0,
            "YIELD": 30.0,
            "WELL_CLASS": "Water Supply",
            "INTENDED_WATER_USE": "Private Domestic",
            "LICENCE_STATUS": "Unlicensed",
            "WELL_DETAILS_URL": f"https://apps.nrs.gov.bc.ca/gwells/well/{wtn}",
            "AQUIFER_MATERIAL": "Unconsolidated",
            "X_ALBERS": PX + distance_m,
            "Y_ALBERS": PY,
        },
        pumping_x=PX,
        pumping_y=PY,
        transmissivity_m2_per_day=1300.0,
        storativity=0.005,
        Q_m3_per_day=343.008,
        duration_days=100.0,
        u_threshold=0.01,
        at_risk_fraction=0.30,
    )


def _result(well_count: int) -> AnalysisResult:
    # Spread across a fixed 100-900 m band whatever the count: past
    # ~1019 m these parameters trip the Cooper-Jacob advisory, and an
    # OUTSIDE_VALIDITY well has no impact fraction, so it would be
    # excluded from this chart entirely and the fixture would silently
    # test the empty figure.
    span = 800.0 / max(well_count - 1, 1)
    wells = [_well(1000 + i, 100.0 + i * span) for i in range(well_count)]
    counts = {s: 0 for s in WellStatus}
    for w in wells:
        counts[w.well_status] += 1
    return AnalysisResult(
        inputs=AnalysisInputs(
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
        ),
        wells=wells,
        n_total=len(wells),
        n_at_risk=counts[WellStatus.AT_RISK],
        n_ok=counts[WellStatus.OK],
        n_insufficient_data=counts[WellStatus.INSUFFICIENT_DATA],
        n_suspect_data=counts[WellStatus.SUSPECT_DATA],
        n_outside_validity=counts[WellStatus.OUTSIDE_VALIDITY],
        max_drawdown_m=None,
    )


def test_every_wtn_is_forced_onto_the_axis_at_a_typical_well_count():
    """40 wells used to hit the old 720 px cap and lose labels."""
    fig = make_impact_chart(_result(40))
    assert fig.layout.yaxis.dtick == 1


def test_a_small_buffer_keeps_the_comfortable_tick_font():
    fig = make_impact_chart(_result(5))
    assert fig.layout.yaxis.dtick == 1
    assert fig.layout.yaxis.tickfont.size == 10


def test_ticks_shrink_before_they_are_dropped():
    """Between comfortable and illegible, labels get smaller, not fewer."""
    settings, labelled = _wtn_axis_settings(_MAX_CHART_HEIGHT, 70)
    assert labelled is True
    assert settings["dtick"] == 1
    assert settings["tickfont"]["size"] == 8


def test_chart_height_is_capped():
    """Height is bounded: the PDF box-fits this chart onto one page."""
    assert _chart_height(500) == _MAX_CHART_HEIGHT
    assert _chart_height(1) < _chart_height(30) <= _MAX_CHART_HEIGHT


def test_an_unlabellable_buffer_says_so_instead_of_pretending():
    """Past capacity the thinning stands — but the caption admits it."""
    count = _LABEL_CAPACITY + 20
    settings, labelled = _wtn_axis_settings(_chart_height(count), count)
    assert labelled is False
    assert settings == {}
    fig = make_impact_chart(_result(count))
    assert "Too many wells to label every bar" in fig.layout.title.text


def test_a_labellable_buffer_carries_no_apology_in_the_caption():
    fig = make_impact_chart(_result(20))
    assert "Too many wells" not in fig.layout.title.text


@pytest.mark.parametrize("count", [1, 2, 26, 46, 90])
def test_labelled_charts_never_squeeze_bars_below_legibility(count):
    """The invariant behind the whole fix.

    Whenever the axis claims to label every bar, each bar must have at
    least `_MIN_LABELLED_BAR_PX` of vertical space — otherwise the
    labels are drawn but unreadable, which is worse than thinning.
    """
    height = _chart_height(count)
    _settings, labelled = _wtn_axis_settings(height, count)
    if labelled:
        assert (height - _CHART_CHROME_PX) / count >= _MIN_LABELLED_BAR_PX
