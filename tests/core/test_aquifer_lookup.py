"""Tests for core/aquifer_lookup.py."""

from __future__ import annotations

import pytest

from gwdrawdown.core import aquifer_lookup


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    aquifer_lookup.load_ts_lookup.cache_clear()


def test_lookup_1a_returns_known_values() -> None:
    """Subtype 1a: T = 4500 m²/d, S = 0.3 (data/ts_lookup.csv)."""
    props = aquifer_lookup.lookup("1a")
    assert props is not None
    assert props.subtype_code == "1a"
    assert props.T_m2_per_day == pytest.approx(4500.0)
    assert props.S == pytest.approx(0.3)


def test_lookup_4b_confined_glacial() -> None:
    props = aquifer_lookup.lookup("4b")
    assert props is not None
    assert props.T_m2_per_day == pytest.approx(250.0)
    assert props.S == pytest.approx(0.005)


def test_lookup_5b_karstic_returns_none() -> None:
    """Karstic limestone is in the table but flagged valid=no."""
    assert aquifer_lookup.lookup("5b") is None


def test_lookup_unknown_code_returns_none() -> None:
    assert aquifer_lookup.lookup("UNK") is None
    assert aquifer_lookup.lookup("not-a-code") is None


def test_lookup_none_or_empty_returns_none() -> None:
    assert aquifer_lookup.lookup(None) is None
    assert aquifer_lookup.lookup("") is None


def test_load_ts_lookup_excludes_invalid_rows() -> None:
    table = aquifer_lookup.load_ts_lookup()
    assert "5b" not in table
    # All 11 valid subtypes from the CSV (12 rows minus 5b).
    assert len(table) == 11


def test_all_loaded_subtypes_have_positive_T_and_S() -> None:
    for code, props in aquifer_lookup.load_ts_lookup().items():
        assert props.T_m2_per_day > 0, code
        assert props.S > 0, code
