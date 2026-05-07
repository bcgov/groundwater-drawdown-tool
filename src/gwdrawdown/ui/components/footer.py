"""Footer component shown on every page.

Displays the tool version (read fresh from ``version.txt`` at each
render so the Phase 6 auto-updater can swap the file under a running
process), the logged-in username when there is one, and a Logout link
that targets the Flask ``/logout`` route registered in ``app.py``.
"""

from __future__ import annotations

from dash import html

from gwdrawdown import config
from gwdrawdown.ui.session import current_user

_FOOTER_STYLE = {
    "borderTop": "1px solid #d0d0d0",
    "marginTop": "2.5rem",
    "padding": "0.75rem 1rem",
    "fontSize": "0.85rem",
    "color": "#555",
    "display": "flex",
    "gap": "1.5rem",
    "alignItems": "center",
    "flexWrap": "wrap",
}


def make_footer() -> html.Footer:
    """Render the page footer with version, user, and Logout link."""
    children: list = [
        html.Span(f"Version {config.version()}"),
    ]
    user = current_user()
    if user is not None:
        children.append(html.Span(f"Signed in as {user}"))
        children.append(
            html.A(
                "Logout",
                href="/logout",
                style={"color": "#1565c0", "textDecoration": "none"},
            )
        )
    return html.Footer(children, style=_FOOTER_STYLE)
