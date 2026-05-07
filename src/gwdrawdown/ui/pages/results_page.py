"""Results page — sub-stage 4a stub.

Sub-stage 4c will replace this layout with the real results dashboard
(at-risk wells summary table, stat cards, distance-drawdown chart per
``references/excel_chart_layout.md``, colour-coded map, full per-well
details table).
"""

from __future__ import annotations

import dash
from dash import dcc, html

from gwdrawdown.ui.components.footer import make_footer
from gwdrawdown.ui.session import is_authenticated

dash.register_page(__name__, path="/results", name="Results")

_PAGE_STYLE = {
    "fontFamily": "sans-serif",
    "padding": "2rem",
    "maxWidth": "1100px",
    "margin": "0 auto",
}


def layout(**_kwargs: object) -> html.Div:
    if not is_authenticated():
        return html.Div(
            dcc.Location(href="/login", id="results-redirect-login", refresh=True)
        )
    return html.Div(
        [
            html.H1("Results"),
            html.P("Sub-stage 4c will turn this into the real results dashboard."),
            make_footer(),
        ],
        style=_PAGE_STYLE,
    )
