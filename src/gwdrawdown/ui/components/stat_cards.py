"""Stat-card row for the results page.

Seven tiles: Total wells, OK, At risk, Insufficient data, Suspect data,
Outside C-J validity, Max drawdown. Colour-coded so the officer can
take in the analysis at a glance before scrolling to tables.

Visual treatment: white card with a 4 px coloured left-edge bar, a
muted uppercase label, and a large status-coloured number. The
coloured bar carries the status hue without bleaching the tile into
the page background — pastel fills disappeared against the new BC
light-grey page bg, so the colour migrated from background to edge.
"""

from __future__ import annotations

from dash import html

from gwdrawdown.analysis import AnalysisResult
from gwdrawdown.core.flagging import WellStatus
from gwdrawdown.ui.components.palette import STATUS_PALETTE

# Foreground (accent + number colour) per tile. Re-uses the shared
# status palette so the cards stay in sync with table cells and map
# markers. The non-status keys are local:
#  - "neutral" (Total wells): BC brand navy. Differentiates from the
#    grey of Insufficient data and ties the leading tile to the
#    page's primary brand colour.
#  - "drawdown" (Max drawdown): bright Material blue. Distinct from
#    BC navy (Total wells), the OK green, and every status hue, so
#    the measurement tile reads as its own category at a glance.
_ACCENT: dict[str, str] = {
    "neutral": "#003366",
    "ok": STATUS_PALETTE[WellStatus.OK][1],
    "at_risk": STATUS_PALETTE[WellStatus.AT_RISK][1],
    "insufficient": STATUS_PALETTE[WellStatus.INSUFFICIENT_DATA][1],
    "suspect": STATUS_PALETTE[WellStatus.SUSPECT_DATA][1],
    "outside": STATUS_PALETTE[WellStatus.OUTSIDE_VALIDITY][1],
    "drawdown": "#1565c0",
}

# Card sizing: 7 tiles need to fit in a single row at a typical
# 1000–1100 px viewport. inner content area at 1000 px viewport is
# ~952 px (24 px padding each side). 7 × 110 + 6 × 8 = 818 px, well
# under that, with room to grow to ~130 px each.
_CARD_STYLE = {
    "backgroundColor": "var(--bc-surface, #FFFFFF)",
    "border": "1px solid var(--bc-border, #D9D9D9)",
    "borderRadius": "var(--bc-radius, 4px)",
    "padding": "0.65rem 0.85rem",
    "minWidth": "110px",
    "flex": "1 1 110px",
    "boxShadow": "var(--bc-shadow-sm, 0 1px 2px rgba(0,0,0,0.06))",
}
_LABEL_STYLE = {
    "fontSize": "0.7rem",
    "textTransform": "uppercase",
    "letterSpacing": "0.05em",
    "fontWeight": 600,
    "color": "var(--bc-text-muted, #606060)",
    "marginBottom": "0.35rem",
    "lineHeight": 1.2,
}
_VALUE_STYLE = {
    "fontSize": "1.7rem",
    "fontWeight": 700,
    "lineHeight": 1.0,
    "letterSpacing": "-0.01em",
}


def _card(label: str, value: str, palette_key: str) -> html.Div:
    accent = _ACCENT[palette_key]
    return html.Div(
        [
            html.Div(label, style=_LABEL_STYLE),
            html.Div(value, style={**_VALUE_STYLE, "color": accent}),
        ],
        style={**_CARD_STYLE, "borderLeft": f"4px solid {accent}"},
    )


def make_stat_cards(result: AnalysisResult) -> html.Div:
    """Render the row of stat cards for an `AnalysisResult`.

    The "Outside validity" card counts wells whose per-source
    ``u_max`` reaches ``inputs.u_threshold`` — the same advisory rule
    that drives the per-well table's purple row tint. We deliberately
    do not use ``result.n_outside_validity`` here: that field counts
    wells with ``WellStatus.OUTSIDE_VALIDITY``, which the pipeline
    no longer emits (Cooper-Jacob's u-check is advisory-only). Using
    the field would always show 0 alongside visibly-purple rows in
    the table, which is confusing.
    """
    max_dd = (
        f"{result.max_drawdown_m:.3f} m"
        if result.max_drawdown_m is not None
        else "—"
    )
    u_threshold = result.inputs.u_threshold
    advisory_count = sum(1 for w in result.wells if w.u_max >= u_threshold)
    cards = [
        _card("Total wells", str(result.n_total), "neutral"),
        _card("At risk", str(result.n_at_risk), "at_risk"),
        _card("OK", str(result.n_ok), "ok"),
        _card("Insufficient data", str(result.n_insufficient_data), "insufficient"),
        _card("Suspect data", str(result.n_suspect_data), "suspect"),
        _card("Outside validity (advisory)", str(advisory_count), "outside"),
        _card("Max drawdown", max_dd, "drawdown"),
    ]
    return html.Div(
        cards,
        style={
            "display": "flex",
            "flexWrap": "wrap",
            "gap": "0.5rem",
            "marginBottom": "1.5rem",
        },
    )
