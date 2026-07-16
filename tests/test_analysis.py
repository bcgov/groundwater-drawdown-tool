"""Tests for analysis._compute_well_result.

Pure-composition tests with synthetic well rows; no DB. The full
pipeline orchestrator (`run_analysis`) hits BCGW and is verified
end-to-end via `scripts/smoke_test_db.py` and a browser walkthrough.
"""

from __future__ import annotations

import pytest

from gwdrawdown.analysis import _compute_well_result
from gwdrawdown.core.drawdown import DrawdownStatus
from gwdrawdown.core.flagging import WellStatus
from gwdrawdown.core.sad import SADStatus

# Pumping point and analysis params held constant across tests.
# T, S chosen to keep Cooper-Jacob valid out to ~1 km so the fixture can
# place wells at a range of distances without hitting OUTSIDE_VALIDITY
# unless we deliberately want it (validity radius ~ sqrt(0.01 * 4Tt/S)).
PX, PY = 1_170_000.0, 418_000.0
T = 1300.0
S = 0.005
Q = 343.008
DURATION = 100.0
U_THRESH = 0.01
THRESHOLD = 0.30


def _row(**overrides) -> dict:
    """A synthetic BCGW well row with overrideable fields."""
    base = {
        "WELL_TAG_NUMBER": 12345,
        "AQUIFER_ID": 186,
        "FINISHED_WELL_DEPTH": 100.0,  # ft
        "TOTAL_DEPTH_DRILLED": None,
        "BEDROCK_DEPTH": None,
        "STATIC_WATER_LEVEL": 30.0,  # ft below top of casing
        "GROUND_ELEVATION": None,
        "YIELD": 30.0,  # US GPM
        "YIELD_ESTIMATION_DURATION": None,
        "WELL_STATUS": "New",
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


def _compute(row: dict) -> object:
    return _compute_well_result(
        row,
        pumping_x=PX,
        pumping_y=PY,
        transmissivity_m2_per_day=T,
        storativity=S,
        Q_m3_per_day=Q,
        duration_days=DURATION,
        u_threshold=U_THRESH,
        at_risk_fraction=THRESHOLD,
    )


# --- Distance + unit conversion ---------------------------------------------


def test_euclidean_distance_in_albers_metres() -> None:
    # dx=500, dy=500 -> hypot = 707.107 m
    result = _compute(_row())
    assert result.distance_m == pytest.approx(707.10678, rel=1e-5)


def test_feet_to_metres_on_depth_fields() -> None:
    result = _compute(_row(FINISHED_WELL_DEPTH=100.0))
    assert result.finished_well_depth_m == pytest.approx(30.48)


def test_us_gpm_to_m3_per_day_on_yield() -> None:
    result = _compute(_row(YIELD=1.0))
    assert result.yield_m3_per_day == pytest.approx(5.45099, abs=1e-4)


def test_null_bcgw_fields_pass_through_as_none() -> None:
    result = _compute(_row(FINISHED_WELL_DEPTH=None, STATIC_WATER_LEVEL=None, YIELD=None))
    assert result.finished_well_depth_m is None
    assert result.static_water_level_m is None
    assert result.yield_m3_per_day is None


# --- Reassigned material -----------------------------------------------------


def test_reassigned_bedrock_when_drilled_past_threshold() -> None:
    # finished 100 ft = 30.48 m, bedrock 50 ft = 15.24 m -> diff 15.24 > 1.524 m
    result = _compute(_row(FINISHED_WELL_DEPTH=100.0, BEDROCK_DEPTH=50.0))
    assert result.reassigned_material == "Bedrock"


def test_reassigned_falls_through_to_gwells_when_no_bedrock() -> None:
    result = _compute(
        _row(FINISHED_WELL_DEPTH=100.0, BEDROCK_DEPTH=None, AQUIFER_MATERIAL="bedrock")
    )
    assert result.reassigned_material == "bedrock"


# --- Drawdown / SAD / status integration ------------------------------------


def test_typical_well_yields_valid_drawdown() -> None:
    result = _compute(_row())
    assert result.drawdown_status == DrawdownStatus.VALID
    assert result.drawdown_m > 0
    assert result.u_max < U_THRESH


def test_well_with_no_npl_is_insufficient_data() -> None:
    result = _compute(_row(STATIC_WATER_LEVEL=None))
    assert result.sad_status == SADStatus.NO_NPL
    assert result.sad_m is None
    assert result.well_status == WellStatus.INSUFFICIENT_DATA
    assert result.impact_fraction is None


def test_well_with_no_finished_depth_is_insufficient_data() -> None:
    result = _compute(_row(FINISHED_WELL_DEPTH=None))
    assert result.sad_status == SADStatus.NO_WELL_DEPTH
    assert result.well_status == WellStatus.INSUFFICIENT_DATA


def test_well_far_away_is_ok() -> None:
    """A well 800 m away (within validity for T=1300, S=0.005, t=100 d)
    has small drawdown and a normal-depth well -> OK."""
    far_row = _row(X_ALBERS=PX + 800.0, Y_ALBERS=PY)
    result = _compute(far_row)
    assert result.drawdown_status == DrawdownStatus.VALID
    assert result.well_status == WellStatus.OK
    assert result.impact_fraction is not None
    assert result.impact_fraction < THRESHOLD


def test_well_close_with_low_sad_is_at_risk() -> None:
    """Shallow well with deep NPL gives a tiny SAD; close drawdown -> at risk.

    finished 10 ft (3.048 m), NPL 8 ft (2.438 m) -> available 0.610 m,
    SAD = 0.427 m. At 50 m with T=1300, S=0.005, t=100, drawdown ~0.21 m,
    so impact fraction ~50% -> AT_RISK.
    """
    row = _row(
        FINISHED_WELL_DEPTH=10.0,
        STATIC_WATER_LEVEL=8.0,
        X_ALBERS=PX + 50.0,
        Y_ALBERS=PY,
    )
    result = _compute(row)
    assert result.drawdown_status == DrawdownStatus.VALID
    assert result.well_status == WellStatus.AT_RISK
    assert result.impact_fraction is not None
    assert result.impact_fraction >= THRESHOLD


def test_well_outside_validity_when_u_too_large() -> None:
    """Tiny T forces u > threshold even at modest distance."""
    result = _compute_well_result(
        _row(X_ALBERS=PX + 200.0, Y_ALBERS=PY),
        pumping_x=PX,
        pumping_y=PY,
        transmissivity_m2_per_day=1.0,  # tiny T
        storativity=0.5,  # large S
        Q_m3_per_day=Q,
        duration_days=0.1,  # short t
        u_threshold=U_THRESH,
        at_risk_fraction=THRESHOLD,
    )
    assert result.drawdown_status == DrawdownStatus.OUTSIDE_VALIDITY
    assert result.well_status == WellStatus.OUTSIDE_VALIDITY


def test_outside_validity_priority_over_insufficient_data() -> None:
    """Same precedence rule as core/flagging tested in pipeline context."""
    result = _compute_well_result(
        _row(X_ALBERS=PX + 200.0, Y_ALBERS=PY, STATIC_WATER_LEVEL=None),
        pumping_x=PX,
        pumping_y=PY,
        transmissivity_m2_per_day=1.0,
        storativity=0.5,
        Q_m3_per_day=Q,
        duration_days=0.1,
        u_threshold=U_THRESH,
        at_risk_fraction=THRESHOLD,
    )
    assert result.well_status == WellStatus.OUTSIDE_VALIDITY


# --- Pass-through metadata ---------------------------------------------------


def test_metadata_pass_through() -> None:
    result = _compute(_row(WELL_TAG_NUMBER=99999, AQUIFER_ID=42))
    assert result.well_tag_number == 99999
    assert result.aquifer_id == 42
    assert result.well_class == "Water Supply"
    assert result.licence_status == "Unlicensed"
    assert "gwells" in result.well_details_url
