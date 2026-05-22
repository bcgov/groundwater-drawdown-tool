"""Footer component shown on every page.

A BC-styled dark-blue strip with the tool version (read fresh from
``version.txt`` on each render so the Phase 6 auto-updater can swap
the file under a running process), a link to the documentation site,
and a screening-tool disclaimer. The signed-in user and the Logout
link both live in the header; the footer carried a duplicate "Signed
in as" line until Phase 5d.

All visual rules live in ``assets/theme.css``; this module is plain
markup.
"""

from __future__ import annotations

from dash import html

from gwdrawdown import config

# Published documentation site (GitHub Pages). Not user-tunable —
# pointing it elsewhere is a code release, like the BCGW DSN.
DOCS_URL = "https://bcgov.github.io/groundwater-drawdown-tool/"


def make_footer() -> html.Footer:
    """Render the page footer with version and disclaimer."""
    return html.Footer(
        html.Div(
            [
                html.Div(
                    [
                        html.Span(f"Version {config.version()}"),
                        html.A(
                            "Documentation",
                            href=DOCS_URL,
                            target="_blank",
                            rel="noopener noreferrer",
                            className="bc-footer__link",
                        ),
                    ],
                    className="bc-footer__meta",
                ),
                html.Div(
                    "Screening tool — results are advisory and must be "
                    "reviewed by the regional hydrogeologist.",
                    className="bc-footer__disclaimer",
                ),
                # Empty right-hand cell, equal width to the version cell,
                # so the disclaimer sits at the true page centre rather
                # than centred in the leftover space beside the version.
                html.Div(className="bc-footer__spacer"),
            ],
            className="bc-footer__inner",
        ),
        className="bc-footer",
    )
