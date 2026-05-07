"""Tests for core/flagging.py."""

from __future__ import annotations

import pytest

from gwdrawdown.core.drawdown import DrawdownResult, DrawdownStatus
from gwdrawdown.core.flagging import WellStatus, flag
from gwdrawdown.core.sad import SADResult, SADStatus

THRESHOLD = 0.30


def _drawdown(value: float, status: DrawdownStatus = DrawdownStatus.VALID) -> DrawdownResult:
    return DrawdownResult(drawdown_m=value, status=status, u_max=0.001, r_used_m=100.0)


def _sad(value: float | None, status: SADStatus = SADStatus.OK) -> SADResult:
    return SADResult(
        value_m=value,
        status=status,
        available_drawdown_m=(value / 0.7) if value is not None else None,
    )


# --- OK branch ---------------------------------------------------------------


def test_ok_when_drawdown_well_below_threshold() -> None:
    # impact = 0.5 / 10 = 5% < 30%
    assert flag(_drawdown(0.5), _sad(10.0), THRESHOLD) == WellStatus.OK


def test_boundary_just_below_threshold_is_ok() -> None:
    # impact = 0.299999 / 1.0 = 29.9999% < 30%
    assert flag(_drawdown(0.299999), _sad(1.0), THRESHOLD) == WellStatus.OK


# --- AT_RISK branch ----------------------------------------------------------


def test_at_risk_at_exact_threshold() -> None:
    # impact == 30%, threshold is >= per spec
    assert flag(_drawdown(0.3), _sad(1.0), THRESHOLD) == WellStatus.AT_RISK


def test_at_risk_above_threshold() -> None:
    assert flag(_drawdown(2.0), _sad(1.0), THRESHOLD) == WellStatus.AT_RISK


def test_suspect_data_when_sad_is_zero() -> None:
    """SAD = 0 implies NPL == well bottom — a data anomaly, not an at-risk well."""
    assert flag(_drawdown(0.001), _sad(0.0), THRESHOLD) == WellStatus.SUSPECT_DATA


def test_suspect_data_when_sad_is_negative() -> None:
    """SAD < 0 means NPL deeper than well bottom (impossible) -> review driller's log."""
    assert flag(_drawdown(0.001), _sad(-1.0), THRESHOLD) == WellStatus.SUSPECT_DATA


def test_suspect_data_priority_over_at_risk() -> None:
    """Even a large drawdown should not turn a SUSPECT well into AT_RISK."""
    assert flag(_drawdown(100.0), _sad(-5.0), THRESHOLD) == WellStatus.SUSPECT_DATA


# --- INSUFFICIENT_DATA branch ------------------------------------------------


def test_insufficient_data_when_no_npl() -> None:
    sad = _sad(None, status=SADStatus.NO_NPL)
    assert flag(_drawdown(1.0), sad, THRESHOLD) == WellStatus.INSUFFICIENT_DATA


def test_insufficient_data_when_no_well_depth() -> None:
    sad = _sad(None, status=SADStatus.NO_WELL_DEPTH)
    assert flag(_drawdown(1.0), sad, THRESHOLD) == WellStatus.INSUFFICIENT_DATA


# --- OUTSIDE_VALIDITY branch -------------------------------------------------


def test_outside_validity_takes_priority_over_insufficient_data() -> None:
    """Per precedence rule, OUTSIDE_VALIDITY wins over missing SAD."""
    drawdown = _drawdown(1.0, status=DrawdownStatus.OUTSIDE_VALIDITY)
    sad = _sad(None, status=SADStatus.NO_NPL)
    assert flag(drawdown, sad, THRESHOLD) == WellStatus.OUTSIDE_VALIDITY


def test_outside_validity_takes_priority_over_at_risk() -> None:
    drawdown = _drawdown(2.0, status=DrawdownStatus.OUTSIDE_VALIDITY)
    sad = _sad(1.0)
    assert flag(drawdown, sad, THRESHOLD) == WellStatus.OUTSIDE_VALIDITY


def test_outside_validity_takes_priority_over_ok() -> None:
    drawdown = _drawdown(0.01, status=DrawdownStatus.OUTSIDE_VALIDITY)
    sad = _sad(10.0)
    assert flag(drawdown, sad, THRESHOLD) == WellStatus.OUTSIDE_VALIDITY


# --- Custom thresholds -------------------------------------------------------


@pytest.mark.parametrize(
    ("threshold", "drawdown", "sad", "expected"),
    [
        (0.50, 0.4, 1.0, WellStatus.OK),  # 40% < 50%
        (0.50, 0.5, 1.0, WellStatus.AT_RISK),  # 50% == 50%
        (0.10, 0.05, 1.0, WellStatus.OK),  # 5% < 10%
        (0.10, 0.1, 1.0, WellStatus.AT_RISK),  # 10% == 10%
    ],
)
def test_custom_threshold(
    threshold: float, drawdown: float, sad: float, expected: WellStatus
) -> None:
    assert flag(_drawdown(drawdown), _sad(sad), threshold) == expected
