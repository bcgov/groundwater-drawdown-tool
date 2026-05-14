"""Shared colour palette for the results page.

Stat cards, per-well table status cells, map markers, and chart well
points all consume these same values so the page reads consistently
at a glance — a yellow cell in the table is the same yellow as the
cell colour on the stat card, and the same yellow as the map
marker for a SUSPECT_DATA well.

Two flavours per status are kept where the lighter shade is used as
a background fill (cards, table cells) and the darker as foreground
text and marker stroke. The map markers use the darker shade as
both stroke and fill (with reduced fillOpacity) so the marker
silhouette reads against the basemap.
"""

from __future__ import annotations

from typing import Final

from gwdrawdown.core.flagging import WellStatus

# (background, foreground) — background for stat-card tiles and
# table-status cells, foreground for marker stroke/fill and table
# status-cell text.
STATUS_PALETTE: Final[dict[WellStatus, tuple[str, str]]] = {
    WellStatus.OK: ("#e8f5e9", "#2e7d32"),
    WellStatus.AT_RISK: ("#ffebee", "#c62828"),
    WellStatus.INSUFFICIENT_DATA: ("#f5f5f5", "#616161"),
    WellStatus.SUSPECT_DATA: ("#fff3e0", "#ef6c00"),
    # OUTSIDE_VALIDITY is wired through the enum and palette for
    # future re-enablement but is not emitted by the pipeline today
    # (advisory-only — see `analysis.effective_u_threshold`).
    WellStatus.OUTSIDE_VALIDITY: ("#f3e5f5", "#7b1fa2"),
}

# Convenience: foreground-only mapping (markers, chart point fill).
STATUS_COLOR: Final[dict[WellStatus, str]] = {
    status: fg for status, (_, fg) in STATUS_PALETTE.items()
}

# Pumping well — deliberately not red so it doesn't collide visually
# with AT_RISK observation wells. Dark blue reads as "this is the
# focal point" without competing for attention with the at-risk
# colour family.
PUMPING_COLOR: Final[str] = "#0d47a1"

# Buffer circle on the map.
BUFFER_COLOR: Final[str] = "#1565c0"

# Selection ring / outline around the currently-selected well on
# both chart and map. Matches the buffer/dash blue family so the
# "this is selected" cue ties back to the page's primary colour.
SELECTION_COLOR: Final[str] = "#1565c0"
