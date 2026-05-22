"""Safe Available Drawdown (SAD) computation.

SAD is the operational threshold the legacy Excel uses to flag wells as
at-risk. Defined as 70% of the available drawdown (deck slide 7,
`Impact!U`):

    SAD = available_drawdown * 0.7

Available drawdown depends on aquifer type:

- **Unconfined sand and gravel:** measured to bottom of well.
  ``available_drawdown = well_bottom - NPL + stickup``
- **Confined aquifer:** measured to top of aquifer (over-pumping a
  confined aquifer below its top causes dewatering).
- **Fractured bedrock:** measured to the uppermost major water-bearing
  fracture, read from the driller's log.

For v1, this module ports the legacy Excel `Impact!U` formula
verbatim — a single nested-IF that uses ``finished_well_depth_m`` as
the unconfined fallback and accepts a per-well user override for
``top_of_fracture_or_aquifer_or_screen_m``. For confined and bedrock
wells the unconfined-style formula over-estimates SAD; the UI flags
those wells with a "manual review of driller's log recommended" note
and the user can supply the correct top via the override field.
Client-confirmed: v1 keeps this manual-override approach; automated
SAD for confined cases is deferred to a future version.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

# Fraction of available drawdown that constitutes SAD. Matches legacy
# Excel `Impact!U` (0.7). Not exposed via config: this is a hydrogeology
# convention from the deck (slide 7), not an operational tuning knob.
SAD_FRACTION: Final[float] = 0.70


class SADStatus(StrEnum):
    """Outcome of a SAD computation, matching legacy Excel `Impact!U` branches."""

    OK = "ok"
    NO_NPL = "no NPL"
    NO_WELL_DEPTH = "no Well Depth"


@dataclass(frozen=True)
class SADResult:
    """Result of a SAD computation for one well.

    Attributes:
        value_m: SAD in metres, or None when the inputs were
            insufficient (status is one of the "no ..." variants).
        status: Which branch of the Excel `Impact!U` formula was taken.
        available_drawdown_m: Intermediate value (top - NPL + stickup),
            populated when status is ``OK``. Useful for surfacing the
            70% relationship in the UI without recomputing.
    """

    value_m: float | None
    status: SADStatus
    available_drawdown_m: float | None


def compute_sad(
    *,
    finished_well_depth_m: float | None,
    non_pumping_water_level_m: float | None,
    stickup_m: float | None = None,
    top_of_fracture_or_aquifer_or_screen_m: float | None = None,
) -> SADResult:
    """Compute Safe Available Drawdown for one well.

    Ports `Impact!U` from the legacy Excel:

    .. code-block:: python

        top = top_of_fracture_or_aquifer_or_screen_m  # user override
        if top is None:
            top = finished_well_depth_m  # unconfined fallback

        if top is None:
            return SADResult(None, NO_WELL_DEPTH)
        if non_pumping_water_level_m is None:
            return SADResult(None, NO_NPL)

        stickup = stickup_m if stickup_m is not None else 0.0
        available_drawdown = top - non_pumping_water_level_m + stickup
        sad = available_drawdown * 0.7

    All depths are in metres (already converted from BCGW feet/inches by
    the data-access layer).

    Args:
        finished_well_depth_m: ``FINISHED_WELL_DEPTH`` in metres.
            Unconfined-style fallback for ``top``.
        non_pumping_water_level_m: ``STATIC_WATER_LEVEL`` in metres
            below top of casing. Required.
        stickup_m: Casing height above ground, metres. Treated as 0
            when missing — the Excel does the same.
        top_of_fracture_or_aquifer_or_screen_m: Per-well user override
            from reading the driller's log. When provided, takes
            precedence over the unconfined fallback. This is the field
            Water Officers fill in for confined or bedrock wells.

    Returns:
        A `SADResult` carrying the SAD in metres and a status. SAD
        ``value_m`` is None whenever a required input is missing; the
        UI surfaces this as `INSUFFICIENT_DATA` in the at-risk pipeline.
    """
    top = (
        top_of_fracture_or_aquifer_or_screen_m
        if top_of_fracture_or_aquifer_or_screen_m is not None
        else finished_well_depth_m
    )

    if top is None:
        return SADResult(value_m=None, status=SADStatus.NO_WELL_DEPTH, available_drawdown_m=None)
    if non_pumping_water_level_m is None:
        return SADResult(value_m=None, status=SADStatus.NO_NPL, available_drawdown_m=None)

    stickup = stickup_m if stickup_m is not None else 0.0
    available_drawdown_m = top - non_pumping_water_level_m + stickup
    sad_m = available_drawdown_m * SAD_FRACTION
    return SADResult(
        value_m=sad_m,
        status=SADStatus.OK,
        available_drawdown_m=available_drawdown_m,
    )
