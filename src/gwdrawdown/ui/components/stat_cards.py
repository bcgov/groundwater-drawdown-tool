"""Stat-card row for the results page.

Seven tiles: Total wells, OK, At risk, Insufficient data, Suspect data,
Outside C-J validity, Max drawdown. Colour-coded so the officer can
take in the analysis at a glance before scrolling to tables.
"""

from __future__ import annotations

from dash import html

from gwdrawdown.analysis import AnalysisResult

# Colour palette aligned with the per-well status cells in
# results_table.py. Tile background is the lighter shade; the value
# uses the darker shade for contrast.
_COLOURS: dict[str, tuple[str, str]] = {
    "neutral": ("#eceff1", "#263238"),
    "ok": ("#e8f5e9", "#2e7d32"),
    "at_risk": ("#ffebee", "#c62828"),
    "insufficient": ("#f5f5f5", "#616161"),
    "suspect": ("#fff3e0", "#ef6c00"),
    "outside": ("#f3e5f5", "#7b1fa2"),
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
    """Render the row of stat cards for an `AnalysisResult`."""
    max_dd = (
        f"{result.max_drawdown_m:.3f} m"
        if result.max_drawdown_m is not None
        else "—"
    )
    cards = [
        _card("Total wells", str(result.n_total), "neutral"),
        _card("At risk", str(result.n_at_risk), "at_risk"),
        _card("OK", str(result.n_ok), "ok"),
        _card("Insufficient data", str(result.n_insufficient_data), "insufficient"),
        _card("Suspect data", str(result.n_suspect_data), "suspect"),
        _card("Outside validity", str(result.n_outside_validity), "outside"),
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
