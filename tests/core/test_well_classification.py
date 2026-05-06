"""Tests for core/well_classification.py."""

from __future__ import annotations

from gwdrawdown.core.well_classification import (
    BEDROCK,
    BEDROCK_THRESHOLD_M,
    UNASSIGNED,
    UNCONSOLIDATED,
    classify_aquifer_material,
)


# 5 ft = 1.524 m exactly.
def test_bedrock_threshold_constant_matches_5_feet() -> None:
    assert BEDROCK_THRESHOLD_M == 1.524


# --- Bedrock-depth heuristic branch ------------------------------------------


def test_well_drilled_well_past_bedrock_classified_as_bedrock() -> None:
    # finished depth 30 m, bedrock at 10 m → 20 m below bedrock → Bedrock
    assert (
        classify_aquifer_material(
            finished_well_depth_m=30.0,
            bedrock_depth_m=10.0,
            aquifer_material_from_gwells="unconsolidated",
        )
        == BEDROCK
    )


def test_well_drilled_just_into_bedrock_classified_unconsolidated() -> None:
    # difference 1.0 m < 1.524 m threshold → Unconsolidated
    assert (
        classify_aquifer_material(
            finished_well_depth_m=11.0,
            bedrock_depth_m=10.0,
            aquifer_material_from_gwells=None,
        )
        == UNCONSOLIDATED
    )


def test_well_drilled_just_past_threshold_classified_bedrock() -> None:
    # difference 2.0 m > 1.524 m threshold → Bedrock
    assert (
        classify_aquifer_material(
            finished_well_depth_m=12.0,
            bedrock_depth_m=10.0,
            aquifer_material_from_gwells=None,
        )
        == BEDROCK
    )


def test_well_above_bedrock_classified_unconsolidated() -> None:
    # finished depth shallower than bedrock → Unconsolidated
    assert (
        classify_aquifer_material(
            finished_well_depth_m=8.0,
            bedrock_depth_m=10.0,
            aquifer_material_from_gwells=None,
        )
        == UNCONSOLIDATED
    )


# --- GWELLS fallback branch --------------------------------------------------


def test_no_bedrock_depth_falls_through_to_gwells_material() -> None:
    assert (
        classify_aquifer_material(
            finished_well_depth_m=50.0,
            bedrock_depth_m=None,
            aquifer_material_from_gwells="bedrock",
        )
        == "bedrock"
    )


def test_no_finished_depth_with_bedrock_falls_through_to_gwells() -> None:
    """Heuristic can't fire without both depths; fall through to GWELLS."""
    assert (
        classify_aquifer_material(
            finished_well_depth_m=None,
            bedrock_depth_m=20.0,
            aquifer_material_from_gwells="unconsolidated",
        )
        == "unconsolidated"
    )


# --- Unassigned branch -------------------------------------------------------


def test_all_inputs_missing_returns_unassigned() -> None:
    assert (
        classify_aquifer_material(
            finished_well_depth_m=None,
            bedrock_depth_m=None,
            aquifer_material_from_gwells=None,
        )
        == UNASSIGNED
    )


def test_only_finished_depth_known_returns_unassigned() -> None:
    assert (
        classify_aquifer_material(
            finished_well_depth_m=50.0,
            bedrock_depth_m=None,
            aquifer_material_from_gwells=None,
        )
        == UNASSIGNED
    )


def test_empty_string_gwells_material_treated_as_missing() -> None:
    """An empty GWELLS value should not be returned as the classification."""
    assert (
        classify_aquifer_material(
            finished_well_depth_m=None,
            bedrock_depth_m=None,
            aquifer_material_from_gwells="",
        )
        == UNASSIGNED
    )
