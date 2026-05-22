"""Cooper-Jacob distance-drawdown calculation.

Implements the Cooper & Jacob (1946) straight-line approximation to the
Theis (1935) non-equilibrium well equation:

    s(r, t) = (Q / (4 π T)) * ln(2.25 * T * t / (r² * S))

equivalently, in log10 form (used by the legacy Excel tool at `Impact!Q`):

    s = (2.303 * Q) / (4 π T) * log10(2.25 * T * t / (S * r²))

Inputs (all SI):

- ``Q`` — pumping rate in m³/day
- ``T`` — transmissivity in m²/day
- ``S`` — storativity, dimensionless
- ``r`` — radial distance from the pumping well to the observation
  point in metres
- ``t`` — elapsed pumping time in days

Output:

- ``s`` — drawdown at the observation point in metres

The function accepts a list of pumping sources and sums their drawdown
contributions linearly at each observation point. Cooper-Jacob is linear
in ``Q``, so superposition is mathematically free; v1 of the UI exposes
only single-well input (multi-well superposition is a deliberate
future scope — Q5), but this signature removes a later refactor.

Two important behaviours match the legacy Excel tool:

1. **r → 0 fallback.** When the observation well is at the same point
   as a pumping source (``r == 0``), the equation is undefined. Substitute
   ``r = 0.1 m`` so the pumping well itself returns a finite, large
   drawdown rather than an error or NaN. Documented at `Impact!Q2`.
2. **Validity check.** Cooper-Jacob is only valid when
   ``u = r² S / (4 T t) < 0.01``. If any pumping source's ``u`` exceeds
   the threshold for the given (r, t), the result is flagged
   ``OUTSIDE_VALIDITY`` and the UI displays it separately from valid
   results.

References:
- Cooper, H. H. & Jacob, C. E. (1946). A generalized graphical method
  for evaluating formation constants and summarizing well-field history.
  *Trans. AGU*, 27(4), 526-534.
- Theis, C. V. (1935). The relation between the lowering of the
  piezometric surface and the rate and duration of discharge of a well
  using ground-water storage. *Trans. AGU*, 16(2), 519-524.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from gwdrawdown import config

# r → 0 fallback distance, in metres. Matches legacy Excel `Impact!Q2`.
R_FALLBACK_M: Final[float] = 0.1


class DrawdownStatus(StrEnum):
    """Validity classification for a drawdown computation."""

    VALID = "VALID"
    OUTSIDE_VALIDITY = "OUTSIDE_VALIDITY"


@dataclass(frozen=True)
class PumpingSource:
    """A single pumping well contributing drawdown via Cooper-Jacob.

    Attributes:
        Q_m3_per_day: Pumping rate, m³/day. Positive = withdrawal.
        T_m2_per_day: Aquifer transmissivity, m²/day.
        S: Storativity, dimensionless.
        r_m: Radial distance from this source to the observation point,
            metres. ``0`` is allowed and triggers the r→0.1 m fallback.
    """

    Q_m3_per_day: float
    T_m2_per_day: float
    S: float
    r_m: float


@dataclass(frozen=True)
class DrawdownResult:
    """Result of a Cooper-Jacob computation at one observation point.

    Attributes:
        drawdown_m: Total drawdown in metres (sum across all sources).
            Always populated, even when status is ``OUTSIDE_VALIDITY`` —
            the value is the formal Cooper-Jacob result, but the caller
            should not present it as a reliable estimate in that case.
        status: ``VALID`` if every contributing source satisfies
            u < threshold; ``OUTSIDE_VALIDITY`` if any does not.
        u_max: The largest ``u = r² S / (4 T t)`` across contributing
            sources. Useful for diagnostics ("how far outside validity?").
        r_used_m: The radial distance actually used in the computation
            for the single-source case (after r→0.1 m fallback). For
            multi-source computations this is the minimum r used; the
            caller can recompute per-source if a finer breakdown is
            needed.
    """

    drawdown_m: float
    status: DrawdownStatus
    u_max: float
    r_used_m: float


def cooper_jacob(
    sources: list[PumpingSource],
    t_days: float,
    *,
    u_threshold: float | None = None,
) -> DrawdownResult:
    """Compute total Cooper-Jacob drawdown at one observation point.

    The drawdown contributions of all ``sources`` are summed linearly
    (Cooper-Jacob is linear in Q, so superposition is exact for
    identical T, S, t — the standard hydrogeology convention).

    Args:
        sources: One or more pumping sources, each with its own r, Q,
            T, S. r=0 is rewritten to r=0.1 m (legacy Excel behaviour,
            `Impact!Q2`).
        t_days: Elapsed pumping time, days. Must be > 0.
        u_threshold: Override for the Cooper-Jacob validity threshold
            (default: ``config.COOPER_JACOB_U_THRESHOLD``, 0.01). The
            literature commonly uses 0.01; some sources allow 0.05.

    Returns:
        A `DrawdownResult` with summed drawdown in metres and a status
        flag. Status is ``OUTSIDE_VALIDITY`` if any source's
        ``u = r² S / (4 T t)`` meets or exceeds the threshold.

    Raises:
        ValueError: if ``sources`` is empty, ``t_days`` is non-positive,
            or any source has non-positive T or S.
    """
    if not sources:
        raise ValueError("cooper_jacob requires at least one pumping source")
    if t_days <= 0:
        raise ValueError(f"t_days must be positive, got {t_days}")

    threshold = u_threshold if u_threshold is not None else config.COOPER_JACOB_U_THRESHOLD

    total_drawdown_m = 0.0
    u_max = 0.0
    r_min_used = math.inf

    for src in sources:
        if src.T_m2_per_day <= 0:
            raise ValueError(f"T_m2_per_day must be positive, got {src.T_m2_per_day}")
        if src.S <= 0:
            raise ValueError(f"S must be positive, got {src.S}")

        r = src.r_m if src.r_m > 0 else R_FALLBACK_M
        r_min_used = min(r_min_used, r)

        u = (r * r * src.S) / (4.0 * src.T_m2_per_day * t_days)
        if u > u_max:
            u_max = u

        # ln form (mathematically identical to the legacy Excel log10 form)
        s = (src.Q_m3_per_day / (4.0 * math.pi * src.T_m2_per_day)) * math.log(
            (2.25 * src.T_m2_per_day * t_days) / (r * r * src.S)
        )
        total_drawdown_m += s

    status = (
        DrawdownStatus.VALID if u_max < threshold else DrawdownStatus.OUTSIDE_VALIDITY
    )

    return DrawdownResult(
        drawdown_m=total_drawdown_m,
        status=status,
        u_max=u_max,
        r_used_m=r_min_used,
    )
