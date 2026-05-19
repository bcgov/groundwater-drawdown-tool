"""Tests for core/units.py."""

from __future__ import annotations

import math

import pytest

from gwdrawdown.core import units

# --- BCGW field conversions ---------------------------------------------------


@pytest.mark.parametrize(
    ("ft", "m"),
    [
        (0.0, 0.0),
        (1.0, 0.3048),
        (100.0, 30.48),
        (-5.0, -1.524),
    ],
)
def test_feet_to_metres_known_values(ft: float, m: float) -> None:
    assert units.feet_to_metres(ft) == pytest.approx(m, abs=1e-12)


def test_feet_metres_round_trip() -> None:
    for ft in [0.0, 1.5, 100.0, 500.123]:
        assert units.metres_to_feet(units.feet_to_metres(ft)) == pytest.approx(ft)


def test_inches_to_metres_known_values() -> None:
    assert units.inches_to_metres(12.0) == pytest.approx(0.3048, abs=1e-12)
    assert units.inches_to_metres(6.0) == pytest.approx(0.1524, abs=1e-12)


def test_inches_metres_round_trip() -> None:
    for inches in [0.0, 6.0, 24.0, 100.5]:
        assert units.metres_to_inches(units.inches_to_metres(inches)) == pytest.approx(inches)


def test_us_gpm_to_m3_per_day_known_value() -> None:
    # 1 US GPM = 5.45099... m³/day. Matches data/unit_conversions.csv (5.45099)
    # to within rounding in the CSV's 6 sig figs.
    assert units.us_gpm_to_m3_per_day(1.0) == pytest.approx(5.45099, abs=1e-4)


def test_us_gpm_round_trip() -> None:
    for gpm in [0.0, 1.0, 50.0, 1000.0]:
        assert units.m3_per_day_to_us_gpm(units.us_gpm_to_m3_per_day(gpm)) == pytest.approx(gpm)


# --- Pumping-rate units (CSV-driven) -----------------------------------------


def test_load_pumping_rate_units_returns_six_units() -> None:
    """Imperial / US GPM were dropped in Phase 5a.2 per client direction
    (BC officers don't use GPM anywhere outside the legacy BCGW YIELD
    column, which still flows through `us_gpm_to_m3_per_day` separately).
    m³/yr was added so multi-year licence-volume estimates can be entered
    directly without the officer pre-converting to daily.
    """
    units.load_pumping_rate_units.cache_clear()
    table = units.load_pumping_rate_units()
    assert len(table) == 6
    expected_units = {"m³/d", "m³/min", "m³/s", "m³/yr", "L/min", "L/s"}
    assert {u.unit for u in table} == expected_units


def test_default_pumping_rate_unit_is_cubic_metres_per_day() -> None:
    units.load_pumping_rate_units.cache_clear()
    assert units.default_pumping_rate_unit().unit == "m³/d"


def test_only_one_default_unit_in_csv() -> None:
    units.load_pumping_rate_units.cache_clear()
    defaults = [u for u in units.load_pumping_rate_units() if u.is_default]
    assert len(defaults) == 1


def test_pumping_rate_to_m3_per_day_canonical_legacy_excel_case() -> None:
    """The legacy Excel example: Q = 3.97 L/s → 343.008 m³/day."""
    units.load_pumping_rate_units.cache_clear()
    assert units.pumping_rate_to_m3_per_day(3.97, "L/s") == pytest.approx(343.008)


@pytest.mark.parametrize(
    ("value", "unit", "expected_m3_per_day"),
    [
        (1.0, "m³/d", 1.0),
        (1.0, "m³/min", 1440.0),
        (1.0, "m³/s", 86400.0),
        # 1 m³/yr = 1/365.25 m³/day ≈ 0.00273785
        (365.25, "m³/yr", 1.0),
        (1.0, "L/s", 86.4),
        (1.0, "L/min", 1.44),
        (60.0, "L/min", 86.4),  # 60 L/min == 1 L/s
    ],
)
def test_pumping_rate_to_m3_per_day_known_conversions(
    value: float, unit: str, expected_m3_per_day: float
) -> None:
    units.load_pumping_rate_units.cache_clear()
    assert units.pumping_rate_to_m3_per_day(value, unit) == pytest.approx(
        expected_m3_per_day
    )


def test_pumping_rate_to_m3_per_day_unknown_unit_raises() -> None:
    units.load_pumping_rate_units.cache_clear()
    with pytest.raises(ValueError, match="Unknown pumping-rate unit"):
        units.pumping_rate_to_m3_per_day(1.0, "furlongs/fortnight")


def test_pumping_rate_consistency_litres_per_second_to_minute() -> None:
    """1 L/s and 60 L/min should give identical m³/day."""
    units.load_pumping_rate_units.cache_clear()
    a = units.pumping_rate_to_m3_per_day(1.0, "L/s")
    b = units.pumping_rate_to_m3_per_day(60.0, "L/min")
    assert math.isclose(a, b, rel_tol=1e-12)
