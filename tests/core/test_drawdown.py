"""Tests for core/drawdown.py."""

from __future__ import annotations

import math

import pytest

from gwdrawdown.core.drawdown import (
    R_FALLBACK_M,
    DrawdownStatus,
    PumpingSource,
    cooper_jacob,
)


def _expected_drawdown_m(Q: float, T: float, S: float, r: float, t: float) -> float:
    """Reference Cooper-Jacob computation (ln form), independent of the SUT."""
    return (Q / (4.0 * math.pi * T)) * math.log((2.25 * T * t) / (r * r * S))


# --- Legacy Excel canonical case ---------------------------------------------


def test_legacy_excel_canonical_case() -> None:
    """Legacy Excel canonical example — the validation case for the
    Cooper-Jacob port (spec/PROJECT_PLAN.md §6, build phase 2).

    Inputs: Q = 3.97 L/s = 343.008 m³/day, T = 250 m²/d, S = 0.005,
    t = 180 days, r = 100 m. The Excel uses the log10 form
    (s = 2.303·Q/(4πT)·log10(...)) which is mathematically identical to
    the ln form. Expected ≈ 0.831 m.
    """
    Q = 343.008  # m^3/day (3.97 L/s * 86.4)
    T, S, r, t = 250.0, 0.005, 100.0, 180.0

    expected = _expected_drawdown_m(Q, T, S, r, t)
    assert expected == pytest.approx(0.8313, abs=1e-3)  # cross-check the reference

    result = cooper_jacob(
        [PumpingSource(Q_m3_per_day=Q, T_m2_per_day=T, S=S, r_m=r)],
        t_days=t,
    )
    assert result.status == DrawdownStatus.VALID
    assert result.drawdown_m == pytest.approx(expected, rel=1e-12)
    assert result.r_used_m == r


# --- r → 0 fallback -----------------------------------------------------------


def test_r_zero_uses_fallback_distance() -> None:
    """r = 0 must be replaced by R_FALLBACK_M to keep the log defined."""
    Q, T, S, t = 343.008, 250.0, 0.005, 180.0
    result = cooper_jacob(
        [PumpingSource(Q_m3_per_day=Q, T_m2_per_day=T, S=S, r_m=0.0)],
        t_days=t,
    )
    expected = _expected_drawdown_m(Q, T, S, R_FALLBACK_M, t)
    assert result.drawdown_m == pytest.approx(expected, rel=1e-12)
    assert result.r_used_m == R_FALLBACK_M


def test_r_zero_drawdown_larger_than_r_100() -> None:
    """The pumping well itself should have larger drawdown than a well 100 m away."""
    Q, T, S, t = 343.008, 250.0, 0.005, 180.0
    near = cooper_jacob(
        [PumpingSource(Q_m3_per_day=Q, T_m2_per_day=T, S=S, r_m=0.0)], t_days=t
    )
    far = cooper_jacob(
        [PumpingSource(Q_m3_per_day=Q, T_m2_per_day=T, S=S, r_m=100.0)], t_days=t
    )
    assert near.drawdown_m > far.drawdown_m


# --- Validity threshold -------------------------------------------------------


def test_outside_validity_when_u_exceeds_threshold() -> None:
    """Large r and small t push u above 0.01."""
    Q, T, S = 343.008, 1.0, 0.5  # tiny T, large S amplifies u
    result = cooper_jacob(
        [PumpingSource(Q_m3_per_day=Q, T_m2_per_day=T, S=S, r_m=200.0)],
        t_days=0.1,
    )
    assert result.status == DrawdownStatus.OUTSIDE_VALIDITY
    assert result.u_max >= 0.01


def test_within_validity_for_typical_inputs() -> None:
    Q, T, S = 343.008, 250.0, 0.005
    result = cooper_jacob(
        [PumpingSource(Q_m3_per_day=Q, T_m2_per_day=T, S=S, r_m=100.0)],
        t_days=180.0,
    )
    assert result.status == DrawdownStatus.VALID
    assert result.u_max < 0.01


def test_custom_u_threshold_relaxes_validity() -> None:
    """A relaxed threshold should accept inputs the default 0.01 rejects.

    Construct inputs so u = 0.05: r=10, S=0.005, T=2.5, t=1
    -> u = (10*10 * 0.005) / (4 * 2.5 * 1) = 0.5 / 10 = 0.05
    """
    src = PumpingSource(Q_m3_per_day=100.0, T_m2_per_day=2.5, S=0.005, r_m=10.0)
    strict = cooper_jacob([src], t_days=1.0, u_threshold=0.01)
    relaxed = cooper_jacob([src], t_days=1.0, u_threshold=0.10)
    assert strict.u_max == pytest.approx(0.05)
    assert strict.status == DrawdownStatus.OUTSIDE_VALIDITY
    assert relaxed.status == DrawdownStatus.VALID


def test_threshold_boundary_strictly_less_than() -> None:
    """u exactly equal to threshold should be classified OUTSIDE_VALIDITY.

    Construct inputs so u == 0.01 exactly: r=10, S=0.0004, T=1, t=1
    -> u = (10*10 * 0.0004) / (4 * 1 * 1) = 0.04 / 4 = 0.01
    """
    src = PumpingSource(Q_m3_per_day=100.0, T_m2_per_day=1.0, S=0.0004, r_m=10.0)
    result = cooper_jacob([src], t_days=1.0, u_threshold=0.01)
    assert result.u_max == pytest.approx(0.01)
    assert result.status == DrawdownStatus.OUTSIDE_VALIDITY


# --- Superposition ------------------------------------------------------------


def test_superposition_two_identical_sources_doubles_drawdown() -> None:
    """Cooper-Jacob is linear in Q; identical sources should sum exactly."""
    src = PumpingSource(Q_m3_per_day=343.008, T_m2_per_day=250.0, S=0.005, r_m=100.0)
    one = cooper_jacob([src], t_days=180.0)
    two = cooper_jacob([src, src], t_days=180.0)
    assert two.drawdown_m == pytest.approx(2.0 * one.drawdown_m, rel=1e-12)


def test_superposition_doubling_q_equals_two_sources() -> None:
    """Doubling Q on one source ≡ adding a second identical source."""
    src1 = PumpingSource(Q_m3_per_day=343.008, T_m2_per_day=250.0, S=0.005, r_m=100.0)
    src_doubled = PumpingSource(
        Q_m3_per_day=686.016, T_m2_per_day=250.0, S=0.005, r_m=100.0
    )
    a = cooper_jacob([src1, src1], t_days=180.0)
    b = cooper_jacob([src_doubled], t_days=180.0)
    assert a.drawdown_m == pytest.approx(b.drawdown_m, rel=1e-12)


def test_superposition_status_outside_if_any_source_outside() -> None:
    """If any source is u>=threshold, the combined result is OUTSIDE_VALIDITY."""
    valid_src = PumpingSource(
        Q_m3_per_day=343.008, T_m2_per_day=250.0, S=0.005, r_m=100.0
    )
    bad_src = PumpingSource(
        Q_m3_per_day=343.008, T_m2_per_day=1.0, S=0.5, r_m=200.0
    )
    result = cooper_jacob([valid_src, bad_src], t_days=0.1)
    assert result.status == DrawdownStatus.OUTSIDE_VALIDITY


# --- Validation ---------------------------------------------------------------


def test_empty_sources_raises() -> None:
    with pytest.raises(ValueError, match="at least one pumping source"):
        cooper_jacob([], t_days=180.0)


def test_zero_or_negative_t_raises() -> None:
    src = PumpingSource(Q_m3_per_day=343.008, T_m2_per_day=250.0, S=0.005, r_m=100.0)
    with pytest.raises(ValueError, match="t_days must be positive"):
        cooper_jacob([src], t_days=0.0)
    with pytest.raises(ValueError, match="t_days must be positive"):
        cooper_jacob([src], t_days=-5.0)


def test_non_positive_T_or_S_raises() -> None:
    with pytest.raises(ValueError, match="T_m2_per_day must be positive"):
        cooper_jacob(
            [PumpingSource(Q_m3_per_day=1.0, T_m2_per_day=0.0, S=0.005, r_m=10.0)],
            t_days=1.0,
        )
    with pytest.raises(ValueError, match="S must be positive"):
        cooper_jacob(
            [PumpingSource(Q_m3_per_day=1.0, T_m2_per_day=250.0, S=0.0, r_m=10.0)],
            t_days=1.0,
        )
