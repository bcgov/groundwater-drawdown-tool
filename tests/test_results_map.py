"""Tests for the results-map well pop-up content.

The pop-up is the fourth surface carrying a well's aquifer number
(after the table, the PDF and the KML) and the one an officer reaches
by clicking the well they are actually looking at, so the
not-delineated marker has to reach it too.
"""

from __future__ import annotations

from gwdrawdown.analysis import WellResult, _compute_well_result
from gwdrawdown.ui.components.results_map import _well_popup_children

PX, PY = 1_170_000.0, 418_000.0


def _row(**overrides) -> dict:
    base = {
        "WELL_TAG_NUMBER": 12345,
        "AQUIFER_ID": 186,
        "FINISHED_WELL_DEPTH": 100.0,
        "TOTAL_DEPTH_DRILLED": None,
        "BEDROCK_DEPTH": None,
        "STATIC_WATER_LEVEL": 30.0,
        "YIELD": 30.0,
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


def _compute(row: dict, **kwargs) -> WellResult:
    return _compute_well_result(
        row,
        pumping_x=PX,
        pumping_y=PY,
        transmissivity_m2_per_day=1300.0,
        storativity=0.005,
        Q_m3_per_day=343.008,
        duration_days=100.0,
        u_threshold=0.01,
        at_risk_fraction=0.30,
        **kwargs,
    )


def _popup_value(well: WellResult, label: str) -> str:
    """Pull the value rendered next to ``label`` in the pop-up.

    Each row is a Div of two Spans — label, then value.
    """
    for child in _well_popup_children(well):
        spans = getattr(child, "children", None)
        if isinstance(spans, list) and len(spans) == 2:
            if getattr(spans[0], "children", None) == label:
                return spans[1].children
    raise AssertionError(f"no {label!r} row in the pop-up")


def test_popup_marks_an_undelineated_aquifer() -> None:
    well = _compute(
        _row(AQUIFER_ID=1143), undelineated_aquifer_ids=frozenset({1143})
    )
    assert _popup_value(well, "Aquifer:") == "Aquifer 1143 (not delineated)"


def test_popup_leaves_a_delineated_aquifer_unmarked() -> None:
    assert _popup_value(_compute(_row(AQUIFER_ID=186)), "Aquifer:") == "Aquifer 186"


def test_popup_shows_a_dash_when_the_well_has_no_aquifer() -> None:
    assert _popup_value(_compute(_row(AQUIFER_ID=None)), "Aquifer:") == "—"
