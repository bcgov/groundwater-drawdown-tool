"""Reassigned aquifer-material classification (legacy `Impact!R` rule).

GWELLS reports ``AQUIFER_MATERIAL`` for many wells, but the legacy Excel
tool computes a parallel "reassigned" classification used to inform SAD
interpretation. The rule, ported verbatim from `Impact!R`:

    if BEDROCK_DEPTH is populated:
        if (FINISHED_WELL_DEPTH - BEDROCK_DEPTH) > 5 ft (~1.524 m):
            return "Bedrock"
        else:
            return "Unconsolidated"
    elif AQUIFER_MATERIAL from GWELLS is populated:
        return AQUIFER_MATERIAL
    else:
        return "Unassigned"

Both the GWELLS-reported value and this reassigned value are shown in
the results table; downstream interpretation (SAD flagging) uses the
reassigned value.

Client-confirmed: the legacy Excel's `> 5 ft` bedrock-depth threshold
is kept for v1.
"""

from __future__ import annotations

from typing import Final

from gwdrawdown.core.units import feet_to_metres

# 5 ft expressed in metres. The threshold lives in feet in the legacy
# Excel because the underlying BCGW values are in feet there. Compute
# from the exact ft→m factor rather than hard-coding 1.524 to avoid
# rounding drift if anyone ever revisits the conversion.
BEDROCK_THRESHOLD_M: Final[float] = feet_to_metres(5.0)

BEDROCK: Final[str] = "Bedrock"
UNCONSOLIDATED: Final[str] = "Unconsolidated"
UNASSIGNED: Final[str] = "Unassigned"


def classify_aquifer_material(
    finished_well_depth_m: float | None,
    bedrock_depth_m: float | None,
    aquifer_material_from_gwells: str | None,
) -> str:
    """Classify a well's aquifer material per the legacy `Impact!R` rule.

    All depth inputs are in metres (already converted from BCGW feet by
    the data-access layer; this function never sees raw BCGW units).

    Args:
        finished_well_depth_m: ``FINISHED_WELL_DEPTH`` in metres, or None.
        bedrock_depth_m: ``BEDROCK_DEPTH`` in metres, or None.
        aquifer_material_from_gwells: ``AQUIFER_MATERIAL`` (e.g.
            ``"bedrock"``, ``"unconsolidated"``), or None.

    Returns:
        ``"Bedrock"`` / ``"Unconsolidated"`` when the bedrock-depth
        heuristic applies; the GWELLS-reported material when it does
        not but GWELLS supplied a value; ``"Unassigned"`` otherwise.

        When ``bedrock_depth_m`` is populated but ``finished_well_depth_m``
        is not, the depth heuristic cannot fire — the function falls
        through to the GWELLS material as if bedrock depth were also
        missing. This matches the Excel behaviour, which checks for the
        difference being computable before applying the threshold.
    """
    if bedrock_depth_m is not None and finished_well_depth_m is not None:
        if (finished_well_depth_m - bedrock_depth_m) > BEDROCK_THRESHOLD_M:
            return BEDROCK
        return UNCONSOLIDATED

    if aquifer_material_from_gwells:
        return aquifer_material_from_gwells

    return UNASSIGNED
