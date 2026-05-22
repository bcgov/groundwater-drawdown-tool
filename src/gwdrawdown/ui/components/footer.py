"""Footer component shown on every page.

A BC-styled dark-blue strip with the tool version (read fresh from
``version.txt`` on each render so the Phase 6 auto-updater can swap
the file under a running process), the signed-in user, and a
screening-tool disclaimer. The Logout link moved to the header in
Phase 5a — keeping logout in two places duplicated chrome.

All visual rules live in ``assets/theme.css``; this module is plain
markup.
"""

from __future__ import annotations

from dash import html

from gwdrawdown import config
from gwdrawdown.ui.session import current_user


def make_footer() -> html.Footer:
    """Render the page footer with version, user and disclaimer."""
    meta: list = [html.Span(f"Version {config.version()}")]
    user = current_user()
    if user is not None:
        meta.append(html.Span(f"Signed in as {user}"))

    return html.Footer(
        html.Div(
            [
                html.Div(meta, className="bc-footer__meta"),
                html.Div(
                    "Screening tool — results are advisory and must be "
                    "reviewed by the regional hydrogeologist.",
                    className="bc-footer__disclaimer",
                ),
            ],
            className="bc-footer__inner",
        ),
        className="bc-footer",
    )
