"""Analysis pipeline: setup inputs -> BCGW queries -> per-well math -> result.

This module sits between ``ui/`` and (``core/`` + ``data_access/``). It
imports from both pure layers, but neither layer imports from here, so
the pipeline is testable end-to-end with a mock connection or
unit-tested per-well via the pure ``_compute_well_result`` function.

Per-well composition (`_compute_well_result`):

1. Convert BCGW raw fields to SI: feet -> metres for depths and water
   levels, US GPM -> m³/day for yield. Stickup is missing from the
   queried BCGW columns (DATA_REFERENCE.md §12) so it defaults to 0;
   per-well stickup overrides land in sub-stage 4c if needed.
2. Plain Euclidean distance from the pumping point in BC Albers
   metres (matches legacy Excel).
3. Reassigned aquifer material via ``core.well_classification``.
4. Cooper-Jacob drawdown via ``core.drawdown.cooper_jacob``.
5. Safe Available Drawdown via ``core.sad.compute_sad``.
6. At-risk classification via ``core.flagging.flag``.

The orchestrator (`run_analysis`) issues the same-aquifer-filtered
``nearby_wells`` query and runs the per-well composition over the
returned rows. It assumes ``data_access.init_pool`` has already been
called (UI flow); callers see ``PoolNotInitialisedError`` otherwise.
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from gwdrawdown.core.drawdown import (
    DrawdownStatus,
    PumpingSource,
    cooper_jacob,
)
from gwdrawdown.core.flagging import WellStatus, flag
from gwdrawdown.core.sad import SADStatus, compute_sad
from gwdrawdown.core.units import feet_to_metres, us_gpm_to_m3_per_day
from gwdrawdown.core.well_classification import classify_aquifer_material
from gwdrawdown.data_access import get_connection
from gwdrawdown.data_access import queries as q

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalysisInputs:
    """Everything the setup page collects, in SI where applicable."""

    pumping_lon: float
    pumping_lat: float
    pumping_x_albers: float
    pumping_y_albers: float
    source_aquifer_id: int
    source_aquifer_name: str
    source_subtype_code: str | None
    transmissivity_m2_per_day: float
    storativity: float
    ts_overridden: bool
    Q_value: float
    Q_unit: str
    Q_m3_per_day: float
    duration_days: float
    buffer_radius_m: float
    same_aquifer_filter: bool
    u_threshold: float
    at_risk_fraction: float

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> AnalysisInputs:
        # Older sessionStorage payloads (pre-4c.1) may lack ts_overridden;
        # default to False so existing tabs don't crash.
        data = {**data}
        data.setdefault("ts_overridden", False)
        return cls(**data)


@dataclass(frozen=True)
class WellResult:
    """One observation well, fully classified."""

    well_tag_number: int
    aquifer_id: int | None
    distance_m: float
    finished_well_depth_m: float | None
    total_depth_drilled_m: float | None
    bedrock_depth_m: float | None
    static_water_level_m: float | None
    # Stickup is not in BCGW (DATA_REFERENCE.md §12); always None until
    # 4c.2 exposes a per-well override sourced from the driller's log.
    stickup_m: float | None
    # Per-well override of "top of fracture / aquifer / screen" used by
    # SAD. Always None in 4c.1; 4c.2 turns this into an editable cell.
    top_of_fracture_or_aquifer_or_screen_m: float | None
    yield_m3_per_day: float | None
    well_class: str | None
    intended_water_use: str | None
    licence_status: str | None
    well_details_url: str | None
    aquifer_material_gwells: str | None
    reassigned_material: str
    drawdown_m: float
    drawdown_status: DrawdownStatus
    u_max: float
    sad_m: float | None
    sad_status: SADStatus
    available_drawdown_m: float | None
    impact_fraction: float | None
    well_status: WellStatus
    x_albers: float
    y_albers: float


@dataclass(frozen=True)
class AnalysisResult:
    """Full output of one analysis run."""

    inputs: AnalysisInputs
    wells: list[WellResult] = field(default_factory=list)
    n_total: int = 0
    n_at_risk: int = 0
    n_ok: int = 0
    n_insufficient_data: int = 0
    n_suspect_data: int = 0
    n_outside_validity: int = 0
    max_drawdown_m: float | None = None
    run_timestamp: datetime = field(default_factory=datetime.now)


def _to_si_or_none(value: float | None, converter) -> float | None:
    return None if value is None else converter(value)


def _compute_well_result(
    well_row: dict[str, Any],
    *,
    pumping_x: float,
    pumping_y: float,
    transmissivity_m2_per_day: float,
    storativity: float,
    Q_m3_per_day: float,
    duration_days: float,
    u_threshold: float,
    at_risk_fraction: float,
) -> WellResult:
    """Pure composition: one BCGW well row -> one WellResult.

    Has no DB or UI dependencies — unit-testable with synthetic rows.
    """
    finished_m = _to_si_or_none(well_row.get("FINISHED_WELL_DEPTH"), feet_to_metres)
    total_depth_m = _to_si_or_none(well_row.get("TOTAL_DEPTH_DRILLED"), feet_to_metres)
    bedrock_m = _to_si_or_none(well_row.get("BEDROCK_DEPTH"), feet_to_metres)
    swl_m = _to_si_or_none(well_row.get("STATIC_WATER_LEVEL"), feet_to_metres)
    yield_m3_per_day = _to_si_or_none(well_row.get("YIELD"), us_gpm_to_m3_per_day)

    x = float(well_row["X_ALBERS"])
    y = float(well_row["Y_ALBERS"])
    dx = x - pumping_x
    dy = y - pumping_y
    distance_m = math.hypot(dx, dy)

    reassigned = classify_aquifer_material(
        finished_well_depth_m=finished_m,
        bedrock_depth_m=bedrock_m,
        aquifer_material_from_gwells=well_row.get("AQUIFER_MATERIAL"),
    )

    drawdown_result = cooper_jacob(
        [
            PumpingSource(
                Q_m3_per_day=Q_m3_per_day,
                T_m2_per_day=transmissivity_m2_per_day,
                S=storativity,
                r_m=distance_m,
            )
        ],
        t_days=duration_days,
        u_threshold=u_threshold,
    )

    # CLIENT_TBD: BCGW does not expose a STICKUP column on
    # GW_WATER_WELLS_WRBC_SVW (DATA_REFERENCE.md §12). Stickup defaults
    # to 0; per-well overrides via the results-page table land in 4c.
    sad_result = compute_sad(
        finished_well_depth_m=finished_m,
        non_pumping_water_level_m=swl_m,
        stickup_m=None,
        top_of_fracture_or_aquifer_or_screen_m=None,
    )

    well_status = flag(drawdown_result, sad_result, at_risk_fraction)

    impact_fraction: float | None = None
    if (
        drawdown_result.status == DrawdownStatus.VALID
        and sad_result.value_m is not None
        and sad_result.value_m > 0
    ):
        impact_fraction = drawdown_result.drawdown_m / sad_result.value_m

    return WellResult(
        well_tag_number=int(well_row["WELL_TAG_NUMBER"]),
        aquifer_id=(
            int(well_row["AQUIFER_ID"]) if well_row.get("AQUIFER_ID") is not None else None
        ),
        distance_m=distance_m,
        finished_well_depth_m=finished_m,
        total_depth_drilled_m=total_depth_m,
        bedrock_depth_m=bedrock_m,
        static_water_level_m=swl_m,
        stickup_m=None,
        top_of_fracture_or_aquifer_or_screen_m=None,
        yield_m3_per_day=yield_m3_per_day,
        well_class=well_row.get("WELL_CLASS"),
        intended_water_use=well_row.get("INTENDED_WATER_USE"),
        licence_status=well_row.get("LICENCE_STATUS"),
        well_details_url=well_row.get("WELL_DETAILS_URL"),
        aquifer_material_gwells=well_row.get("AQUIFER_MATERIAL"),
        reassigned_material=reassigned,
        drawdown_m=drawdown_result.drawdown_m,
        drawdown_status=drawdown_result.status,
        u_max=drawdown_result.u_max,
        sad_m=sad_result.value_m,
        sad_status=sad_result.status,
        available_drawdown_m=sad_result.available_drawdown_m,
        impact_fraction=impact_fraction,
        well_status=well_status,
        x_albers=x,
        y_albers=y,
    )


def run_analysis(inputs: AnalysisInputs) -> AnalysisResult:
    """Run the full pipeline against the live BCGW pool.

    The connection pool must already be initialised (login flow).
    """
    aquifer_filter = inputs.source_aquifer_id if inputs.same_aquifer_filter else None
    logger.info(
        "Running analysis: point=(%.6f, %.6f), source aquifer=%s, "
        "buffer=%.0f m, filter=%s",
        inputs.pumping_lon,
        inputs.pumping_lat,
        inputs.source_aquifer_id,
        inputs.buffer_radius_m,
        inputs.same_aquifer_filter,
    )
    with get_connection() as conn:
        rows = q.nearby_wells(
            conn,
            x_albers=inputs.pumping_x_albers,
            y_albers=inputs.pumping_y_albers,
            radius_m=inputs.buffer_radius_m,
            aquifer_id=aquifer_filter,
        )

    # CLIENT_TBD: Cooper-Jacob u < 0.01 validity check is bypassed at
    # the pipeline level pending client confirmation. The check still
    # exists in core.drawdown.cooper_jacob and u_max is preserved on
    # every WellResult for diagnostics, but no well will be flagged
    # OUTSIDE_VALIDITY here. Revert by replacing this with
    # `inputs.u_threshold` to re-enable.
    effective_u_threshold = float("inf")

    wells = [
        _compute_well_result(
            row,
            pumping_x=inputs.pumping_x_albers,
            pumping_y=inputs.pumping_y_albers,
            transmissivity_m2_per_day=inputs.transmissivity_m2_per_day,
            storativity=inputs.storativity,
            Q_m3_per_day=inputs.Q_m3_per_day,
            duration_days=inputs.duration_days,
            u_threshold=effective_u_threshold,
            at_risk_fraction=inputs.at_risk_fraction,
        )
        for row in rows
    ]

    counts: dict[WellStatus, int] = {s: 0 for s in WellStatus}
    valid_drawdowns: list[float] = []
    for w in wells:
        counts[w.well_status] += 1
        if w.drawdown_status == DrawdownStatus.VALID:
            valid_drawdowns.append(w.drawdown_m)
    max_drawdown = max(valid_drawdowns) if valid_drawdowns else None

    logger.info(
        "Analysis complete: %d wells (%d at-risk, %d ok, %d insufficient, "
        "%d suspect, %d outside)",
        len(wells),
        counts[WellStatus.AT_RISK],
        counts[WellStatus.OK],
        counts[WellStatus.INSUFFICIENT_DATA],
        counts[WellStatus.SUSPECT_DATA],
        counts[WellStatus.OUTSIDE_VALIDITY],
    )

    return AnalysisResult(
        inputs=inputs,
        wells=wells,
        n_total=len(wells),
        n_at_risk=counts[WellStatus.AT_RISK],
        n_ok=counts[WellStatus.OK],
        n_insufficient_data=counts[WellStatus.INSUFFICIENT_DATA],
        n_suspect_data=counts[WellStatus.SUSPECT_DATA],
        n_outside_validity=counts[WellStatus.OUTSIDE_VALIDITY],
        max_drawdown_m=max_drawdown,
    )
