"""Login page: BCGW credentials -> connection test -> pool init -> /setup.

Flow on submit (matches PROJECT_PLAN.md §6 phase 4):

1. Open a one-shot ``oracledb.connect()`` with the supplied credentials
   and run ``SELECT 1 FROM DUAL`` to verify them. A standalone connect
   surfaces a clean error before we touch the pool, so a bad password
   never leaves a half-initialised pool behind.
2. On success: tear down any leftover pool, call
   ``data_access.init_pool``, mark the Flask session as authenticated,
   redirect to ``/setup``.
3. On failure: show the Oracle error inline, stay on this page, do
   nothing server-side.

The connection target (``config.BCGW_DSN``) is shown read-only on the
form so users always see which database they are signing in to.
"""

from __future__ import annotations

import logging

import dash
import oracledb
from dash import (
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    dcc,
    html,
    no_update,
)

from gwdrawdown import config, data_access
from gwdrawdown.ui import session
from gwdrawdown.ui.components.footer import make_footer
from gwdrawdown.ui.components.header import make_header

dash.register_page(__name__, path="/login", name="Sign in")

logger = logging.getLogger(__name__)

# Eye-toggle button positioned inside the password input on the right
# edge. Most of the look is driven by .bc-form-input (border, focus)
# on the input itself; the toggle is just an absolutely-positioned
# transparent button.
_EYE_BUTTON_STYLE = {
    "position": "absolute",
    "right": "0.5rem",
    "top": "50%",
    "transform": "translateY(-50%)",
    "background": "transparent",
    "border": "none",
    "padding": "0.25rem",
    "cursor": "pointer",
    "color": "var(--bc-text-muted, #606060)",
    "display": "flex",
    "alignItems": "center",
    "justifyContent": "center",
}


def _eye_icon(visible: bool) -> html.Span:
    """Return an inline SVG eye icon.

    `visible=True` shows the "eye-open" glyph (i.e. password is
    currently visible — click to hide); `visible=False` shows the
    "eye-closed" glyph (password is hidden — click to reveal).
    """
    if visible:
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" '
            'viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/>'
            '<circle cx="12" cy="12" r="3"/></svg>'
        )
    else:
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" '
            'viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M17.94 17.94A10.5 10.5 0 0 1 12 19c-6.5 0-10-7-10-7'
            ' a17.5 17.5 0 0 1 4.06-5.06"/>'
            '<path d="M9.9 4.24A10 10 0 0 1 12 4c6.5 0 10 7 10 7'
            ' a17.5 17.5 0 0 1-2.16 3.19"/>'
            '<path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/>'
            '<line x1="2" y1="2" x2="22" y2="22"/></svg>'
        )
    import urllib.parse

    return html.Img(
        src=f"data:image/svg+xml;utf8,{urllib.parse.quote(svg)}",
        style={"width": "20px", "height": "20px", "display": "block"},
        alt="",
    )


def _form_field(label: str, control: html.Div | dcc.Input) -> html.Div:
    """Render a labeled form field as a `.bc-form-field` block.

    Adds vertical spacing between fields by giving each block its own
    bottom margin; the underlying `.bc-form-field` is a flex column
    that stacks label above control.
    """
    return html.Div(
        [
            html.Label(label, className="bc-form-label"),
            control,
        ],
        className="bc-form-field",
        style={"marginBottom": "1rem"},
    )


def layout(**_kwargs: object) -> html.Div:
    if session.is_authenticated():
        return html.Div(
            dcc.Location(href="/setup", id="login-already-authed", refresh=True)
        )
    return html.Div(
        [
            make_header(),
            html.Main(
                html.Div(
                    [
                        html.H1("Sign in"),
                        html.P(
                            "Use your BCGW credentials to access the tool.",
                            style={
                                "color": "var(--bc-text-muted, #606060)",
                                "marginBottom": "1.5rem",
                            },
                        ),
                        html.Form(
                            [
                                _form_field(
                                    "Connection target",
                                    dcc.Input(
                                        id="login-dsn",
                                        type="text",
                                        value=config.BCGW_DSN,
                                        disabled=True,
                                        className="bc-form-input",
                                    ),
                                ),
                                _form_field(
                                    "BCGW username",
                                    dcc.Input(
                                        id="login-username",
                                        type="text",
                                        autoComplete="username",
                                        className="bc-form-input",
                                    ),
                                ),
                                _form_field(
                                    "BCGW password",
                                    html.Div(
                                        [
                                            dcc.Input(
                                                id="login-password",
                                                type="password",
                                                autoComplete="current-password",
                                                className="bc-form-input",
                                                style={"paddingRight": "2.5rem"},
                                            ),
                                            html.Button(
                                                _eye_icon(visible=False),
                                                id="login-password-toggle",
                                                type="button",
                                                title="Show password",
                                                **{"aria-label": "Show password"},
                                                n_clicks=0,
                                                style=_EYE_BUTTON_STYLE,
                                            ),
                                        ],
                                        style={"position": "relative"},
                                    ),
                                ),
                                html.Button(
                                    "Sign in",
                                    id="login-submit",
                                    n_clicks=0,
                                    type="button",
                                    className="bc-btn bc-btn--primary bc-btn--large",
                                ),
                            ],
                        ),
                        html.Div(id="login-error", className="bc-form-error"),
                        dcc.Location(id="login-redirect", refresh=True),
                    ],
                    className="bc-login-card",
                    style={
                        "backgroundColor": "var(--bc-surface, #FFFFFF)",
                        "border": "1px solid var(--bc-border, #D9D9D9)",
                        "borderRadius": "var(--bc-radius-lg, 6px)",
                        "padding": "2rem",
                        "boxShadow": "var(--bc-shadow-md, 0 2px 6px rgba(0,0,0,0.08))",
                    },
                ),
                className="bc-page__content bc-page__content--narrow",
            ),
            make_footer(),
        ],
        className="bc-page",
    )


# Clientside toggle: flip the password input between type="password"
# and type="text" on each click of the eye button, and swap the icon
# + accessibility label so the user can see whether the password is
# currently visible. Kept clientside so the password never round-trips
# the server just to toggle visibility.
clientside_callback(
    """
    function(n_clicks, currentType) {
        if (!n_clicks) {
            return [window.dash_clientside.no_update,
                    window.dash_clientside.no_update,
                    window.dash_clientside.no_update];
        }
        const showing = currentType === 'text';
        const nextType = showing ? 'password' : 'text';
        const label = showing ? 'Show password' : 'Hide password';
        return [nextType, label, label];
    }
    """,
    Output("login-password", "type"),
    Output("login-password-toggle", "title"),
    Output("login-password-toggle", "aria-label"),
    Input("login-password-toggle", "n_clicks"),
    State("login-password", "type"),
    prevent_initial_call=True,
)


# A second clientside callback swaps the eye icon SVG to match the
# new state. Kept separate from the type/label toggle so the icon
# render can derive purely from the input's `type` — that means a
# future server-side override of the type prop still gets the right
# icon, with no extra wiring.
clientside_callback(
    """
    function(currentType) {
        const showing = currentType === 'text';
        const openSvg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"' +
            ' viewBox="0 0 24 24" fill="none" stroke="currentColor"' +
            ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
            '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/>' +
            '<circle cx="12" cy="12" r="3"/></svg>'
        );
        const closedSvg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"' +
            ' viewBox="0 0 24 24" fill="none" stroke="currentColor"' +
            ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
            '<path d="M17.94 17.94A10.5 10.5 0 0 1 12 19c-6.5 0-10-7-10-7' +
            ' a17.5 17.5 0 0 1 4.06-5.06"/>' +
            '<path d="M9.9 4.24A10 10 0 0 1 12 4c6.5 0 10 7 10 7' +
            ' a17.5 17.5 0 0 1-2.16 3.19"/>' +
            '<path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/>' +
            '<line x1="2" y1="2" x2="22" y2="22"/></svg>'
        );
        const svg = showing ? openSvg : closedSvg;
        const encoded = 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
        return {
            type: 'Img',
            namespace: 'dash_html_components',
            props: {
                src: encoded,
                alt: '',
                style: {width: '20px', height: '20px', display: 'block'}
            }
        };
    }
    """,
    Output("login-password-toggle", "children"),
    Input("login-password", "type"),
)


def _verify_credentials(username: str, password: str) -> None:
    """Run ``SELECT 1 FROM DUAL`` against BCGW; raise on failure."""
    conn = oracledb.connect(user=username, password=password, dsn=config.BCGW_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM DUAL")
            cur.fetchone()
    finally:
        conn.close()


@callback(
    Output("login-error", "children"),
    Output("login-redirect", "pathname"),
    Input("login-submit", "n_clicks"),
    Input("login-username", "n_submit"),
    Input("login-password", "n_submit"),
    State("login-username", "value"),
    State("login-password", "value"),
    prevent_initial_call=True,
)
def handle_login(
    _n_clicks: int,
    _user_submit: int,
    _pw_submit: int,
    username: str | None,
    password: str | None,
) -> tuple[str, object]:
    if not username or not password:
        return "Username and password are required.", no_update

    username = username.strip()

    try:
        _verify_credentials(username, password)
    except oracledb.DatabaseError as e:
        logger.warning("Login failed for user %r: %s", username, e)
        return f"Sign-in failed: {e}", no_update

    # Defensive: if a previous session never closed cleanly, drop it
    # before reopening. init_pool itself raises if a pool already exists.
    if data_access.is_initialised():
        data_access.close_pool()
    data_access.init_pool(username, password)
    session.set_user(username)
    logger.info("User %r authenticated", username)
    return "", "/setup"
