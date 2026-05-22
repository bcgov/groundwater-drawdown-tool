"""Top-of-page header chrome — BC Gov visual identity.

A full-width dark-blue band: the BC visual-identity logo on the left,
app title beside it (separated by a thin vertical divider), signed-in
user and Logout link on the right when authenticated. A thin gold
stripe sits along the bottom edge of the band — the hallmark of BC Gov
web properties — rendered via ``border-bottom`` on ``.bc-header`` so
the chrome stays a single tag.

The logo is the official BC positive logo (navy artwork on white),
cropped from the supplied ``BCID_H_RGB_pos.jpg`` to trim its wide
clear-space margins down to a small uniform border. Because the
header band is dark, the asset keeps its white background and
``.bc-header__logo`` (in ``theme.css``) rounds its corners so it
reads as a deliberate white panel — the BC brand's treatment for the
logo in a dark context — rather than a bare image.
"""

from __future__ import annotations

from dash import get_asset_url, html

from gwdrawdown.ui.session import current_user

_LOGO_ASSET = "bc_logo_header.jpg"


def _logo() -> html.Img:
    """Render the BC visual-identity logo as an asset-served image."""
    return html.Img(
        src=get_asset_url(_LOGO_ASSET),
        alt="Government of British Columbia",
        className="bc-header__logo",
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
                        _logo(),
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
