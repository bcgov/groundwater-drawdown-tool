"""Tests for the shared display-formatting helpers.

`format_float` exists to keep small storativity values (e.g. 0.00003)
out of scientific notation in the officer-facing UI, the results page,
and the PDF. These cases pin that behaviour.
"""

from __future__ import annotations

from gwdrawdown.ui.format_utils import format_float


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
