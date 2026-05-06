"""Tests for core/sad.py."""

from __future__ import annotations

import pytest

from gwdrawdown.core.sad import SADStatus, compute_sad

# --- OK branch ---------------------------------------------------------------


def test_unconfined_fallback_uses_finished_well_depth() -> None:
    # top = finished_well_depth = 30 m, NPL = 10 m, stickup = 0.5 m
    # available = 30 - 10 + 0.5 = 20.5 m; SAD = 14.35 m
    result = compute_sad(
        finished_well_depth_m=30.0,
        non_pumping_water_level_m=10.0,
        stickup_m=0.5,
    )
    assert result.status == SADStatus.OK
    assert result.available_drawdown_m == pytest.approx(20.5)
    assert result.value_m == pytest.approx(14.35)


def test_user_override_takes_precedence_over_finished_depth() -> None:
    """top_of_fracture_or_aquifer_or_screen_m overrides the unconfined fallback."""
    result = compute_sad(
        finished_well_depth_m=100.0,
        non_pumping_water_level_m=10.0,
        stickup_m=0.0,
        top_of_fracture_or_aquifer_or_screen_m=40.0,
    )
    assert result.status == SADStatus.OK
    # available = 40 - 10 + 0 = 30; SAD = 21
    assert result.available_drawdown_m == pytest.approx(30.0)
    assert result.value_m == pytest.approx(21.0)


def test_missing_stickup_treated_as_zero() -> None:
    """Excel `Impact!U` treats missing stickup as 0."""
    a = compute_sad(
        finished_well_depth_m=30.0,
        non_pumping_water_level_m=10.0,
        stickup_m=None,
    )
    b = compute_sad(
        finished_well_depth_m=30.0,
        non_pumping_water_level_m=10.0,
        stickup_m=0.0,
    )
    assert a.value_m == b.value_m


def test_seventy_percent_factor() -> None:
    """SAD must be exactly 70% of available drawdown."""
    result = compute_sad(
        finished_well_depth_m=20.0,
        non_pumping_water_level_m=5.0,
        stickup_m=0.0,
    )
    assert result.value_m == pytest.approx(0.7 * result.available_drawdown_m)


# --- no Well Depth branch ----------------------------------------------------


def test_no_well_depth_branch() -> None:
    """No fallback and no override → status = no Well Depth."""
    result = compute_sad(
        finished_well_depth_m=None,
        non_pumping_water_level_m=10.0,
    )
    assert result.status == SADStatus.NO_WELL_DEPTH
    assert result.value_m is None
    assert result.available_drawdown_m is None


def test_no_well_depth_branch_takes_priority_over_no_npl() -> None:
    """When both top and NPL are missing, the Excel reports no Well Depth first."""
    result = compute_sad(
        finished_well_depth_m=None,
        non_pumping_water_level_m=None,
    )
    assert result.status == SADStatus.NO_WELL_DEPTH


# --- no NPL branch ------------------------------------------------------------


def test_no_npl_branch() -> None:
    result = compute_sad(
        finished_well_depth_m=30.0,
        non_pumping_water_level_m=None,
        stickup_m=0.5,
    )
    assert result.status == SADStatus.NO_NPL
    assert result.value_m is None
    assert result.available_drawdown_m is None


def test_no_npl_with_user_override_top() -> None:
    """User-supplied top + missing NPL → still no NPL (top alone isn't enough)."""
    result = compute_sad(
        finished_well_depth_m=None,
        non_pumping_water_level_m=None,
        top_of_fracture_or_aquifer_or_screen_m=40.0,
    )
    assert result.status == SADStatus.NO_NPL
