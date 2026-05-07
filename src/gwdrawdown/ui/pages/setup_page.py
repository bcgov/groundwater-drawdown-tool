"""Setup page — sub-stage 4a stub.

Sub-stage 4b will replace this layout with the real input form (three
input modes for the pumping point, Q + units, duration presets, buffer
radius, T/S override, same-aquifer filter toggle, source-aquifer
picker, Run Analysis button).

For 4a this page exists only to verify the auth shell — it is reachable
when authenticated and redirects to ``/login`` otherwise.
"""

from __future__ import annotations

import dash
from dash import dcc, html

from gwdrawdown.ui.components.footer import make_footer
from gwdrawdown.ui.session import is_authenticated

dash.register_page(__name__, path="/setup", name="Setup")

_PAGE_STYLE = {
    "fontFamily": "sans-serif",
    "padding": "2rem",
    "maxWidth": "900px",
    "margin": "0 auto",
}


def layout(**_kwargs: object) -> html.Div:
    if not is_authenticated():
        return html.Div(
            dcc.Location(href="/login", id="setup-redirect-login", refresh=True)
        )
    return html.Div(
        [
            html.H1("Setup"),
            html.P(
                "Sub-stage 4b will turn this into the real input page "
                "(map click / lat-lon / WTN, Q with units, duration "
                "presets, buffer radius, T/S override, same-aquifer "
                "filter)."
            ),
            html.P(
                "Use the Logout link in the footer to verify the "
                "session-clear path."
            ),
            make_footer(),
        ],
        style=_PAGE_STYLE,
    )
