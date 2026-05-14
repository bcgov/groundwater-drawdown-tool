"""Top-of-page header chrome — BC Gov visual identity.

A full-width dark-blue band: BC wordmark on the left, app title
beside it (separated by a thin vertical divider), signed-in user
and Logout link on the right when authenticated. A thin gold stripe
sits along the bottom edge of the band — the hallmark of BC Gov web
properties — rendered via ``border-bottom`` on ``.bc-header`` so
the chrome stays a single tag.

The wordmark is plain HTML rather than inline SVG. SVG ``<text>``
inside a data-URI ``<img>`` can't read the page's ``@font-face``
declarations, so BC Sans never reaches it; HTML inherits the font
stack from the rest of the page and renders identically. Each
sub-element uses ``flex-shrink: 0`` + ``white-space: nowrap`` (in
``theme.css``) so the header never wraps even when the viewport
narrows.
"""

from __future__ import annotations

from dash import html

from gwdrawdown.ui.session import current_user


def _wordmark() -> html.Div:
    """Render the BC wordmark as an HTML block.

    Two stacked typographic lines: bold "British Columbia" on top,
    a quieter "Government of B.C." subtitle underneath. A thin gold
    bar on the left edge ties it to the accent stripe under the
    header band.
    """
    return html.Div(
        [
            html.Div("British Columbia", className="bc-wordmark__primary"),
            html.Div("Government of B.C.", className="bc-wordmark__secondary"),
        ],
        className="bc-wordmark",
    )


def make_header(title: str = "Groundwater Drawdown Tool") -> html.Header:
    """Render the BC-styled page header.

    Shows the signed-in user and a Logout link when a session is
    active; on the login page (no user) the right side is empty so
    the chrome reads as "you're not signed in yet" without an
    inert button.
    """
    user = current_user()
    user_block: list = []
    if user is not None:
        user_block = [
            html.Div(
                [
                    html.Span("Signed in as ", style={"opacity": 0.75}),
                    html.Span(user, style={"fontWeight": 600}),
                ],
                className="bc-header__user",
            ),
            html.A("Logout", href="/logout", className="bc-header__logout"),
        ]

    return html.Header(
        html.Div(
            [
                html.A(
                    [
                        _wordmark(),
                        html.Div(className="bc-header__divider"),
                        html.Div(title, className="bc-header__title"),
                    ],
                    href="/",
                    className="bc-header__brand",
                ),
                html.Div(className="bc-header__spacer"),
                *user_block,
            ],
            className="bc-header__inner",
        ),
        className="bc-header",
    )
