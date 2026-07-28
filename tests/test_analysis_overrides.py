"""Tests for `analysis.recompute_well`, `analysis.apply_overrides`, and
the JSON round-trip on `WellResult` / `AnalysisResult`.

The override path is the heart of sub-stage 4c.2: officers edit cells
in the per-well details table on /results, the values land in a
`dcc.Store` keyed by WTN, and the page-level render callback re-runs
SAD + flagging without re-querying BCGW. These tests pin that math
end-to-end against synthetic `WellResult`s.
"""

from __future__ import annotations

import pytest

from gwdrawdown.analysis import (
    AnalysisInputs,
    AnalysisResult,
    WellResult,
    _compute_well_result,
    apply_overrides,
    recompute_well,
)
from gwdrawdown.core.drawdown import DrawdownStatus
from gwdrawdown.core.flagging import WellStatus
from gwdrawdown.core.sad import SADStatus

PX, PY = 1_170_000.0, 418_000.0
T = 1300.0
S = 0.005
Q = 343.008
DURATION = 100.0
U_THRESH = 0.01
THRESHOLD = 0.30


def _row(**overrides) -> dict:
    base = {
        "WELL_TAG_NUMBER": 12345,
        "AQUIFER_ID": 186,
        "FINISHED_WELL_DEPTH": 100.0,
        "TOTAL_DEPTH_DRILLED": None,
        "BEDROCK_DEPTH": None,
        "STATIC_WATER_LEVEL": 30.0,
        "GROUND_ELEVATION": None,
        "YIELD": 30.0,
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


def _compute(row: dict) -> WellResult:
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


def _recompute(base: WellResult, overrides: dict) -> WellResult:
    return recompute_well(
        base,
        overrides,
        transmissivity_m2_per_day=T,
        storativity=S,
        Q_m3_per_day=Q,
        duration_days=DURATION,
        u_threshold=U_THRESH,
        at_risk_fraction=THRESHOLD,
    )


# --- recompute_well ----------------------------------------------------------


def test_recompute_with_no_overrides_is_a_noop() -> None:
    base = _compute(_row())
    out = _recompute(base, {})
    assert out.drawdown_m == pytest.approx(base.drawdown_m)
    assert out.sad_m == pytest.approx(base.sad_m)
    assert out.well_status == base.well_status
    assert out.static_water_level_m == base.static_water_level_m
    assert out.finished_well_depth_m == base.finished_well_depth_m


def test_override_static_water_level_shifts_sad() -> None:
    base = _compute(_row())
    # Push the NPL 5 m deeper (larger value) -> available drawdown
    # shrinks by 5 m, SAD shrinks by 5 * 0.7 = 3.5 m.
    new_swl = base.static_water_level_m + 5.0
    out = _recompute(base, {"static_water_level_m": new_swl})
    assert out.static_water_level_m == pytest.approx(new_swl)
    assert out.sad_status == SADStatus.OK
    assert out.sad_m == pytest.approx(base.sad_m - 5.0 * 0.7)


def test_override_top_of_fracture_replaces_finished_depth_as_sad_reference() -> None:
    """Override `top_of_fracture_or_aquifer_or_screen_m` and SAD picks
    that up instead of falling through to finished depth."""
    base = _compute(_row())
    finished = base.finished_well_depth_m
    swl = base.static_water_level_m
    # Place the fracture at half the well depth.
    top = finished / 2.0
    out = _recompute(base, {"top_of_fracture_or_aquifer_or_screen_m": top})
    assert out.top_of_fracture_or_aquifer_or_screen_m == pytest.approx(top)
    assert out.sad_m == pytest.approx((top - swl) * 0.70)


def test_override_stickup_lifts_sad_by_stickup_times_fraction() -> None:
    base = _compute(_row())
    base_sad = base.sad_m
    out = _recompute(base, {"stickup_m": 1.0})
    assert out.stickup_m == pytest.approx(1.0)
    # SAD = (top - NPL + stickup) * 0.7 -> +0.7 m for a 1 m stickup.
    assert out.sad_m == pytest.approx(base_sad + 0.7)


def test_override_finished_depth_changes_sad_when_no_top_override() -> None:
    base = _compute(_row())
    swl = base.static_water_level_m
    out = _recompute(base, {"finished_well_depth_m": 50.0})
    assert out.finished_well_depth_m == pytest.approx(50.0)
    assert out.sad_m == pytest.approx((50.0 - swl) * 0.70)


def test_override_npl_below_well_bottom_flags_suspect_data() -> None:
    """SUSPECT_DATA fires when SAD computes to a non-positive value
    (NPL deeper than the well bottom — physically impossible)."""
    base = _compute(_row(FINISHED_WELL_DEPTH=30.0))  # 30 ft = 9.144 m
    out = _recompute(base, {"static_water_level_m": 50.0})  # NPL 50 m, well 9.14 m
    assert out.sad_status == SADStatus.OK  # the math runs
    assert out.sad_m is not None and out.sad_m <= 0
    assert out.well_status == WellStatus.SUSPECT_DATA


def test_override_revert_via_none_restores_base_value() -> None:
    """Passing None for an override key reverts that field to the base value."""
    base = _compute(_row())
    once = _recompute(base, {"static_water_level_m": 5.0})
    assert once.static_water_level_m == pytest.approx(5.0)
    reverted = _recompute(once, {"static_water_level_m": None})
    assert reverted.static_water_level_m == pytest.approx(once.static_water_level_m)


def test_recompute_preserves_metadata_and_distance() -> None:
    base = _compute(_row())
    out = _recompute(base, {"stickup_m": 0.5})
    assert out.well_tag_number == base.well_tag_number
    assert out.aquifer_id == base.aquifer_id
    assert out.distance_m == pytest.approx(base.distance_m)
    assert out.x_albers == base.x_albers
    assert out.y_albers == base.y_albers
    assert out.reassigned_material == base.reassigned_material
    assert out.intended_water_use == base.intended_water_use


# --- apply_overrides totals --------------------------------------------------


def _make_inputs() -> AnalysisInputs:
    return AnalysisInputs(
        pumping_lon=-123.6,
        pumping_lat=48.7,
        pumping_x_albers=PX,
        pumping_y_albers=PY,
        source_aquifer_id=186,
        source_aquifer_name="Test Aquifer",
        source_subtype_code="4b",
        transmissivity_m2_per_day=T,
        storativity=S,
        ts_overridden=False,
        Q_value=3.97,
        Q_unit="L/s",
        Q_m3_per_day=Q,
        duration_days=DURATION,
        buffer_radius_m=1000.0,
        same_aquifer_filter=True,
        u_threshold=U_THRESH,
        at_risk_fraction=THRESHOLD,
    )


def _make_result(wells: list[WellResult]) -> AnalysisResult:
    counts = {s: 0 for s in WellStatus}
    valid = []
    for w in wells:
        counts[w.well_status] += 1
        if w.drawdown_status == DrawdownStatus.VALID:
            valid.append(w.drawdown_m)
    return AnalysisResult(
        inputs=_make_inputs(),
        wells=wells,
        n_total=len(wells),
        n_at_risk=counts[WellStatus.AT_RISK],
        n_ok=counts[WellStatus.OK],
        n_insufficient_data=counts[WellStatus.INSUFFICIENT_DATA],
        n_suspect_data=counts[WellStatus.SUSPECT_DATA],
        n_outside_validity=counts[WellStatus.OUTSIDE_VALIDITY],
        max_drawdown_m=max(valid) if valid else None,
    )


def test_apply_overrides_with_empty_dict_returns_input_unchanged() -> None:
    base_well = _compute(_row())
    base = _make_result([base_well])
    out = apply_overrides(base, {})
    assert out is base


def test_apply_overrides_recounts_status_after_edit() -> None:
    """Editing one well's NPL to push it past well bottom moves it
    from OK to SUSPECT_DATA, and the totals on the rebuilt result
    reflect that."""
    ok_well = _compute(
        _row(
            WELL_TAG_NUMBER=1,
            FINISHED_WELL_DEPTH=200.0,  # 60.96 m
            STATIC_WATER_LEVEL=30.0,  # 9.14 m
            X_ALBERS=PX + 800.0,
            Y_ALBERS=PY,
        )
    )
    assert ok_well.well_status == WellStatus.OK
    base = _make_result([ok_well])
    assert base.n_ok == 1
    assert base.n_suspect_data == 0
    # Push NPL deeper than the well bottom (60.96 m) -> SAD <= 0 ->
    # SUSPECT_DATA.
    out = apply_overrides(base, {1: {"static_water_level_m": 80.0}})
    assert out.n_ok == 0
    assert out.n_suspect_data == 1
    assert out.wells[0].well_status == WellStatus.SUSPECT_DATA


def test_apply_overrides_preserves_run_timestamp() -> None:
    base_well = _compute(_row())
    base = _make_result([base_well])
    out = apply_overrides(base, {12345: {"stickup_m": 1.0}})
    assert out.run_timestamp == base.run_timestamp


# --- JSON round-trip ---------------------------------------------------------


def test_well_result_json_roundtrip_preserves_enum_values() -> None:
    base = _compute(_row())
    payload = base.to_json()
    # Enum fields serialise to their str value.
    assert payload["drawdown_status"] == base.drawdown_status.value
    assert payload["sad_status"] == base.sad_status.value
    assert payload["well_status"] == base.well_status.value
    restored = WellResult.from_json(payload)
    assert restored == base


def test_well_result_json_roundtrip_with_none_fields() -> None:
    base = _compute(_row(STATIC_WATER_LEVEL=None, FINISHED_WELL_DEPTH=None))
    payload = base.to_json()
    restored = WellResult.from_json(payload)
    assert restored == base
    assert restored.static_water_level_m is None
    assert restored.finished_well_depth_m is None


def test_analysis_result_json_roundtrip() -> None:
    wells = [_compute(_row(WELL_TAG_NUMBER=i)) for i in (1, 2, 3)]
    base = _make_result(wells)
    payload = base.to_json()
    restored = AnalysisResult.from_json(payload)
    assert restored.n_total == base.n_total
    assert restored.n_ok == base.n_ok
    assert restored.n_at_risk == base.n_at_risk
    assert restored.run_timestamp == base.run_timestamp
    assert restored.run_id == base.run_id
    assert [w.well_tag_number for w in restored.wells] == [1, 2, 3]
    assert restored.inputs == base.inputs


def test_run_id_is_stable_and_unique() -> None:
    """Each result mints its own run_id; the same result keeps it."""
    a = _make_result([_compute(_row())])
    b = _make_result([_compute(_row())])
    assert a.run_id and b.run_id
    assert a.run_id != b.run_id
    assert a.run_id == a.run_id


def test_apply_overrides_preserves_run_id() -> None:
    base = _make_result([_compute(_row())])
    out = apply_overrides(base, {12345: {"stickup_m": 1.0}})
    assert out.run_id == base.run_id


def test_legacy_result_payload_without_run_id_gets_one() -> None:
    """Pre-5c sessionStorage payloads predate `run_id`.

    `from_json` mints a fresh hex id so a stale tab still deserialises.
    """
    payload = _make_result([_compute(_row())]).to_json()
    payload.pop("run_id", None)
    restored = AnalysisResult.from_json(payload)
    assert restored.run_id
    assert len(restored.run_id) == 32


# --- Manual-entry mode -------------------------------------------------------


def _make_manual_inputs(material: str = "Bedrock") -> AnalysisInputs:
    """Inputs that emulate the manual-aquifer path from setup_page."""
    return AnalysisInputs(
        pumping_lon=-123.6,
        pumping_lat=48.7,
        pumping_x_albers=PX,
        pumping_y_albers=PY,
        source_aquifer_id=None,
        source_aquifer_name=f"Manual entry ({material})",
        source_subtype_code=None,
        transmissivity_m2_per_day=T,
        storativity=S,
        ts_overridden=True,
        Q_value=3.97,
        Q_unit="L/s",
        Q_m3_per_day=Q,
        duration_days=DURATION,
        buffer_radius_m=1000.0,
        same_aquifer_filter=False,
        u_threshold=U_THRESH,
        at_risk_fraction=THRESHOLD,
        manual_material=material,
    )


def test_is_manual_mode_true_when_source_aquifer_id_is_none() -> None:
    inputs = _make_manual_inputs()
    assert inputs.is_manual_mode is True


def test_is_manual_mode_false_for_normal_run() -> None:
    inputs = _make_inputs()
    assert inputs.is_manual_mode is False


def test_manual_inputs_json_roundtrip_preserves_material() -> None:
    inputs = _make_manual_inputs(material="Unconsolidated")
    restored = AnalysisInputs.from_json(inputs.to_json())
    assert restored == inputs
    assert restored.source_aquifer_id is None
    assert restored.manual_material == "Unconsolidated"
    assert restored.is_manual_mode is True


def test_legacy_inputs_payload_without_manual_material_field_loads_cleanly() -> None:
    """Older sessionStorage payloads predate `manual_material`.

    `from_json` defaults the field to None so an existing tab from a
    prior run doesn't crash on deserialisation. Same backward-compat
    posture as ``ts_overridden`` (pre-4c.1).
    """
    payload = _make_inputs().to_json()
    payload.pop("manual_material", None)
    restored = AnalysisInputs.from_json(payload)
    assert restored.manual_material is None
    assert restored.is_manual_mode is False


def test_pumping_well_tag_number_survives_json_roundtrip() -> None:
    """The WTN-mode pumping-point tag is carried for the usage log."""
    inputs = AnalysisInputs.from_json(
        {**_make_inputs().to_json(), "pumping_well_tag_number": 96473}
    )
    restored = AnalysisInputs.from_json(inputs.to_json())
    assert restored.pumping_well_tag_number == 96473


def test_legacy_inputs_payload_without_wtn_field_loads_cleanly() -> None:
    """Payloads predating `pumping_well_tag_number` default it to None."""
    payload = _make_inputs().to_json()
    payload.pop("pumping_well_tag_number", None)
    restored = AnalysisInputs.from_json(payload)
    assert restored.pumping_well_tag_number is None


def test_apply_overrides_works_in_manual_mode() -> None:
    """Overrides on a manual-mode result still recompute SAD + status.

    The override path doesn't care whether `source_aquifer_id` is
    None — it only uses the T/S/Q/duration fields, which are present
    in both modes. This pins that behaviour so a future refactor
    that special-cases manual mode doesn't accidentally break edits.
    """
    base_well = _compute(_row())
    base = AnalysisResult(
        inputs=_make_manual_inputs(),
        wells=[base_well],
        n_total=1,
        n_at_risk=1 if base_well.well_status == WellStatus.AT_RISK else 0,
        n_ok=1 if base_well.well_status == WellStatus.OK else 0,
        n_insufficient_data=0,
        n_suspect_data=0,
        n_outside_validity=0,
        max_drawdown_m=base_well.drawdown_m,
    )
    out = apply_overrides(base, {12345: {"stickup_m": 1.0}})
    assert out.wells[0].stickup_m == pytest.approx(1.0)
    assert out.inputs.is_manual_mode is True
