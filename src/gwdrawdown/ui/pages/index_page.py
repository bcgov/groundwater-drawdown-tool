"""Root page: redirect to /setup if authenticated, else /login.

Dash with ``use_pages=True`` resolves URLs against the page registry,
so a Flask-only ``@server.route('/')`` would be shadowed. We register a
real Dash page whose ``layout`` returns a ``dcc.Location`` redirect — at
render time the browser is told where to go next.
"""

from __future__ import annotations

import dash
from dash import dcc

from gwdrawdown.ui.session import is_authenticated

dash.register_page(__name__, path="/", name="Home")


def layout(**_kwargs: object) -> dcc.Location:
    target = "/setup" if is_authenticated() else "/login"
    return dcc.Location(href=target, id="index-redirect", refresh=True)
