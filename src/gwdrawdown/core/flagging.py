"""At-risk classification of an observation well, given drawdown and SAD.

Combines the outcomes of `core.drawdown.cooper_jacob` and
`core.sad.compute_sad` into a single status the UI can colour-code.

Status precedence — when more than one rule could apply, the higher
priority wins:

1. ``OUTSIDE_VALIDITY`` — the drawdown number itself is unreliable
   because Cooper-Jacob's ``u < 0.01`` constraint is violated.
2. ``INSUFFICIENT_DATA`` — drawdown is valid but SAD could not be
   computed because a required input was missing (no NPL or no
   well depth).
3. ``SUSPECT_DATA`` — SAD was computed but the result is non-positive,
   meaning the GWELLS record places the static water level deeper
   than the well bottom (impossible in reality). The pumping impact
   is fine; the *baseline* well record needs review against the
   driller's log.
4. ``AT_RISK`` — drawdown / SAD ≥ ``AT_RISK_DRAWDOWN_FRACTION``
   (default 0.30, client-confirmed; matches legacy Excel `Impact!V`).
5. ``OK`` — everything checks out, well is below the threshold.
"""

from __future__ import annotations

from enum import StrEnum

from gwdrawdown.core.drawdown import DrawdownResult, DrawdownStatus
from gwdrawdown.core.sad import SADResult, SADStatus


class WellStatus(StrEnum):
    """At-risk classification for one observation well."""

    OK = "OK"
    AT_RISK = "AT_RISK"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    SUSPECT_DATA = "SUSPECT_DATA"
    OUTSIDE_VALIDITY = "OUTSIDE_VALIDITY"


def flag(
    drawdown: DrawdownResult,
    sad: SADResult,
    at_risk_fraction: float,
) -> WellStatus:
    """Combine drawdown + SAD into one status.

    Args:
        drawdown: Result of `core.drawdown.cooper_jacob` for this well.
        sad: Result of `core.sad.compute_sad` for this well.
        at_risk_fraction: Threshold ratio of drawdown to SAD above
            which a well is flagged at-risk (default 0.30 matches
            legacy Excel; ``config.AT_RISK_DRAWDOWN_FRACTION``).

    Returns:
        One of `WellStatus` per the precedence rules in the module
        docstring.
    """
    if drawdown.status == DrawdownStatus.OUTSIDE_VALIDITY:
        return WellStatus.OUTSIDE_VALIDITY
    if sad.status != SADStatus.OK or sad.value_m is None:
        return WellStatus.INSUFFICIENT_DATA
    if sad.value_m <= 0:
        # GWELLS reports static water level deeper than the well
        # bottom (e.g. WTN 96473: well 30 ft, SWL 70 ft). The
        # baseline record is wrong, not the proposed pumping; flag
        # for manual review against the driller's log.
        return WellStatus.SUSPECT_DATA
    if drawdown.drawdown_m / sad.value_m >= at_risk_fraction:
        return WellStatus.AT_RISK
    return WellStatus.OK
