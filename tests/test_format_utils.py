"""Tests for the shared display-formatting helpers.

`format_float` exists to keep small storativity values (e.g. 0.00003)
out of scientific notation in the officer-facing UI, the results page,
and the PDF. These cases pin that behaviour.

`format_source_aquifer` is shared by the results-page run summary and
the PDF input-parameters table, so a drift between the two surfaces
would be a real defect; these cases pin the shape of both branches.
"""

from __future__ import annotations

import pytest

from gwdrawdown.analysis import AnalysisInputs
from gwdrawdown.ui.format_utils import (
    format_float,
    format_licence_status,
    format_source_aquifer,
    is_licensed,
)


def _inputs(**overrides) -> AnalysisInputs:
    base = {
        "pumping_lon": -123.6,
        "pumping_lat": 48.7,
        "pumping_x_albers": 1_170_000.0,
        "pumping_y_albers": 418_000.0,
        "source_aquifer_id": 199,
        "source_aquifer_name": "Cowichan Valley",
        "source_aquifer_material": "Sand and Gravel",
        "source_subtype_code": "1a",
        "transmissivity_m2_per_day": 1300.0,
        "storativity": 0.005,
        "ts_overridden": False,
        "Q_value": 3.97,
        "Q_unit": "L/s",
        "Q_m3_per_day": 343.008,
        "duration_days": 90.0,
        "buffer_radius_m": 1000.0,
        "same_aquifer_filter": False,
        "u_threshold": 0.01,
        "at_risk_fraction": 0.30,
    }
    base.update(overrides)
    return AnalysisInputs(**base)


def test_small_storativity_avoids_scientific_notation():
    # The bug report: str(0.00003) / f"{0.00003:g}" both give "3e-05".
    assert format_float(0.00003) == "0.00003"
    assert format_float(0.00064) == "0.00064"


def test_typical_values_round_trip_cleanly():
    assert format_float(0.005) == "0.005"
    assert format_float(0.1) == "0.1"


def test_whole_numbers_drop_trailing_zero():
    assert format_float(250.0) == "250"
    assert format_float(1234.5) == "1234.5"


def test_zero_and_none():
    assert format_float(0.0) == "0"
    assert format_float(None) == ""


def test_mapped_aquifer_leads_with_the_number_and_material():
    # Officers refer to aquifers by number, so the number leads and the
    # material sits in brackets right behind it.
    text = format_source_aquifer(_inputs())
    assert text.startswith("Aquifer 199 (Sand and Gravel)")
    assert "Cowichan Valley" in text
    assert "subtype 1a" in text


def test_mapped_aquifer_without_material_says_so():
    # BCGW MATERIAL is nullable; an empty bracket would read as a bug.
    text = format_source_aquifer(_inputs(source_aquifer_material=None))
    assert "(material not recorded)" in text


def test_manual_mode_names_the_nearest_mapped_aquifer():
    # The whole point of the "Other" option: show that mapped polygons
    # were present and the officer deliberately passed over them.
    text = format_source_aquifer(
        _inputs(
            source_aquifer_id=None,
            source_aquifer_name="Other — aquifer not delineated",
            source_aquifer_material=None,
            source_subtype_code=None,
            manual_material="Unconsolidated",
            nearest_mapped_aquifer="Aquifer 199 (Sand and Gravel), 120 m away",
        )
    )
    assert text.startswith("Other — aquifer not delineated (Unconsolidated)")
    assert "nearest mapped: Aquifer 199 (Sand and Gravel), 120 m away" in text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Licensed", "Licensed"),
        ("Unlicensed", "Unlicensed"),
        ("Historical", "Historical"),
        ("  Licensed  ", "Licensed"),
        (None, "Unknown"),
        ("", "Unknown"),
        ("   ", "Unknown"),
    ],
)
def test_licence_status_display(raw, expected):
    """NULL becomes "Unknown", never "Unlicensed".

    A blank cell in a printed report reads as "not licensed", which is
    an assertion GWELLS did not make.
    """
    assert format_licence_status(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Licensed", True),
        ("licensed", True),  # defensive: BCGW casing is not guaranteed
        ("Unlicensed", False),
        # A lapsed licence is not a current one — no ring.
        ("Historical", False),
        (None, False),
        ("", False),
    ],
)
def test_is_licensed_drives_the_map_ring(raw, expected):
    assert is_licensed(raw) is expected


def test_unlicensed_is_not_matched_by_a_substring_check():
    """Guard against a naive `"licensed" in value` implementation.

    "Unlicensed" contains "licensed"; a substring test would ring every
    unlicensed well on the map — the exact opposite of the intent.
    """
    assert is_licensed("Unlicensed") is False


def test_manual_mode_with_no_nearby_aquifer():
    text = format_source_aquifer(
        _inputs(
            source_aquifer_id=None,
            source_aquifer_name="Other — aquifer not delineated",
            source_aquifer_material=None,
            source_subtype_code=None,
            manual_material="Bedrock",
            nearest_mapped_aquifer=None,
        )
    )
    assert "no mapped aquifer nearby" in text
