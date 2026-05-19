"""Unit conversions between BCGW source units and SI.

BCGW reports depths and water levels in **feet**, casing diameters and
stickup in **inches**, and well yield in **US gallons per minute**. The
tool's math (Cooper-Jacob in `core/drawdown.py`) operates in SI throughout
(metres, m³/day). All unit conversion is centralised here so unit bugs
have one place to hide.

The pumping-rate dropdown shown on the setup page is driven by
`data/unit_conversions.csv`. The list is a curated subset of the
legacy Excel `Lookup_DB!B3:I10`: GPM units (Imperial and US) were
removed in Phase 5a.2 because BC officers don't use them outside
the BCGW YIELD column (which still routes through
`us_gpm_to_m3_per_day` separately); m³/yr was added so multi-year
licence-volume estimates can be entered directly. Default is m³/d.
See DATA_REFERENCE.md §11 for the full unit list and provenance.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final

from gwdrawdown import config

# --- Exact BCGW field conversion factors -------------------------------------

# International foot, defined exactly as 0.3048 m (NIST SP 811).
_FEET_TO_METRES: Final[float] = 0.3048
# International inch = 1/12 of an international foot.
_INCHES_TO_METRES: Final[float] = _FEET_TO_METRES / 12.0
# US liquid gallon, defined exactly as 3.785411784 L.
_US_GALLON_TO_LITRE: Final[float] = 3.785411784
# Convert US GPM to m^3/day: gal/min * L/gal * min/day / L/m^3
_US_GPM_TO_M3_PER_DAY: Final[float] = _US_GALLON_TO_LITRE * 1440.0 / 1000.0


def feet_to_metres(value_ft: float) -> float:
    """Convert feet to metres (exact, 1 ft = 0.3048 m)."""
    return value_ft * _FEET_TO_METRES


def metres_to_feet(value_m: float) -> float:
    """Convert metres to feet (exact, 1 ft = 0.3048 m)."""
    return value_m / _FEET_TO_METRES


def inches_to_metres(value_in: float) -> float:
    """Convert inches to metres (exact, 1 in = 0.0254 m)."""
    return value_in * _INCHES_TO_METRES


def metres_to_inches(value_m: float) -> float:
    """Convert metres to inches (exact, 1 in = 0.0254 m)."""
    return value_m / _INCHES_TO_METRES


def us_gpm_to_m3_per_day(value_gpm: float) -> float:
    """Convert US gallons per minute to cubic metres per day.

    Used for BCGW well yield (`YIELD` column, US GPM) when promoting to
    SI for drawdown calculations.
    """
    return value_gpm * _US_GPM_TO_M3_PER_DAY


def m3_per_day_to_us_gpm(value_m3_per_day: float) -> float:
    """Convert cubic metres per day to US gallons per minute."""
    return value_m3_per_day / _US_GPM_TO_M3_PER_DAY


# --- Pumping-rate units (driven by data/unit_conversions.csv) ----------------


@dataclass(frozen=True)
class PumpingRateUnit:
    """A pumping-rate unit option for the setup page Q dropdown.

    Fields mirror the columns of `data/unit_conversions.csv`. The
    `m3_per_day` field is the multiplier that converts a value expressed
    in this unit to cubic metres per day.
    """

    unit: str
    m3_per_day: float
    description: str
    is_default: bool


@lru_cache(maxsize=1)
def load_pumping_rate_units(
    csv_path: Path | None = None,
) -> tuple[PumpingRateUnit, ...]:
    """Load the pumping-rate unit table from CSV.

    Cached on first call. Pass an explicit `csv_path` only in tests; the
    production path comes from `config.UNIT_CONVERSIONS_PATH`.

    Source: `data/unit_conversions.csv`, derived from legacy Excel
    `Lookup_DB!B3:I10`. See DATA_REFERENCE.md §11.
    """
    path = csv_path if csv_path is not None else config.UNIT_CONVERSIONS_PATH
    units: list[PumpingRateUnit] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            units.append(
                PumpingRateUnit(
                    unit=row["unit"],
                    m3_per_day=float(row["m3_per_day"]),
                    description=row["description"],
                    is_default=row["is_default"].strip().lower() == "true",
                )
            )
    if not units:
        raise ValueError(f"No pumping-rate units loaded from {path}")
    return tuple(units)


def default_pumping_rate_unit() -> PumpingRateUnit:
    """Return the unit flagged as default in the CSV (Water Officer canonical: L/s)."""
    for u in load_pumping_rate_units():
        if u.is_default:
            return u
    raise ValueError("No pumping-rate unit is flagged as default in unit_conversions.csv")


def pumping_rate_to_m3_per_day(value: float, unit: str) -> float:
    """Convert a pumping rate in any supported unit to m³/day.

    `unit` must match the `unit` column of `data/unit_conversions.csv`
    exactly (case-sensitive, e.g. ``"m³/d"``, ``"L/s"``).
    """
    for u in load_pumping_rate_units():
        if u.unit == unit:
            return value * u.m3_per_day
    known = ", ".join(u.unit for u in load_pumping_rate_units())
    raise ValueError(f"Unknown pumping-rate unit {unit!r}; known units: {known}")
