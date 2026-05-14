"""Stat-card row for the results page.

Seven tiles: Total wells, OK, At risk, Insufficient data, Suspect data,
Outside C-J validity, Max drawdown. Colour-coded so the officer can
take in the analysis at a glance before scrolling to tables.
"""

from __future__ import annotations

from dash import html

from gwdrawdown.analysis import AnalysisResult
from gwdrawdown.core.flagging import WellStatus
from gwdrawdown.ui.components.palette import STATUS_PALETTE

# Tile palette: status tiles re-use the shared status palette so the
# stat cards, table cells, and map markers can't drift apart. Two
# non-status keys ("neutral" for Total wells, "drawdown" for Max
# drawdown) are local to the cards.
_COLOURS: dict[str, tuple[str, str]] = {
    "neutral": ("#eceff1", "#263238"),
    "ok": STATUS_PALETTE[WellStatus.OK],
    "at_risk": STATUS_PALETTE[WellStatus.AT_RISK],
    "insufficient": STATUS_PALETTE[WellStatus.INSUFFICIENT_DATA],
    "suspect": STATUS_PALETTE[WellStatus.SUSPECT_DATA],
    "outside": STATUS_PALETTE[WellStatus.OUTSIDE_VALIDITY],
    "drawdown": ("#e3f2fd", "#1565c0"),
}

_CARD_STYLE = {
    "padding": "0.75rem 1rem",
    "borderRadius": "4px",
    "minWidth": "150px",
    "flex": "1 1 150px",
}
_LABEL_STYLE = {
    "fontSize": "0.75rem",
    "textTransform": "uppercase",
    "letterSpacing": "0.05em",
    "marginBottom": "0.25rem",
}
_VALUE_STYLE = {
    "fontSize": "1.6rem",
    "fontWeight": "bold",
    "lineHeight": 1.0,
}


def _card(label: str, value: str, palette_key: str) -> html.Div:
    bg, fg = _COLOURS[palette_key]
    return html.Div(
        [
            html.Div(label, style={**_LABEL_STYLE, "color": fg}),
            html.Div(value, style={**_VALUE_STYLE, "color": fg}),
        ],
        style={**_CARD_STYLE, "backgroundColor": bg},
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
            "gap": "0.75rem",
            "marginBottom": "1.5rem",
        },
    )
