"""Footer component shown on every page.

A BC-styled dark-blue strip with:

- the tool version (read fresh from ``version.txt`` on each render so the
  Phase 6 auto-updater can swap the file under a running process),
- the date that version was installed — the mtime of ``version.txt``,
  which the install / update process touches when it lands the file,
- a link to the documentation site,
- the results-interpretation disclaimer and the internal-use notice
  (see ``ui/disclaimers.py``).

The version text is a button that opens a modal listing the most recent
``CHANGELOG.md`` entries, so a user whose colleague has a feature they
don't can see at a glance which version added it and how their install
compares.

All visual rules live in ``assets/theme.css``; this module is plain
markup plus the modal toggle callback.
"""

from __future__ import annotations

import re
from datetime import datetime

from dash import Input, Output, callback, ctx, dcc, html, no_update

from gwdrawdown import config
from gwdrawdown.ui import disclaimers

# Published documentation site (GitHub Pages). Not user-tunable —
# pointing it elsewhere is a code release, like the BCGW DSN.
DOCS_URL = "https://bcgov.github.io/groundwater-drawdown-tool/"

# How many leading ``## [...]`` sections of the CHANGELOG to render in
# the modal. Bounded so the modal stays scannable.
_MAX_CHANGELOG_SECTIONS = 3

_CHANGELOG_PATH = config.PROJECT_ROOT / "CHANGELOG.md"


def _last_updated_date() -> str:
    """Return ``YYYY-MM-DD`` of ``version.txt``'s last-modified time.

    On a fresh install or an auto-update extraction the file's mtime is
    the extraction timestamp, so this is the date the currently
    installed release landed on the user's machine.
    """
    try:
        mtime = config.VERSION_FILE.stat().st_mtime
    except OSError:
        return "unknown"
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")


def _recent_changelog() -> str:
    """Return the most recent shipped CHANGELOG sections as Markdown.

    Only the first ``_MAX_CHANGELOG_SECTIONS`` ``## [...]`` blocks are
    kept, so the modal does not become an entire-history scroll wall.
    The ``[Unreleased]`` working-set heading is skipped: the modal is
    opened by users running an installed release, so a developer-side
    "what's queued for the next release" block is irrelevant (and
    misleading — it shows as an empty heading right above the user's
    actual release notes).
    """
    try:
        content = _CHANGELOG_PATH.read_text(encoding="utf-8")
    except OSError:
        return "_Changelog not available._"
    pattern = re.compile(r"^## \[(?P<label>[^\]]+)\]", re.MULTILINE)
    sections = [
        m for m in pattern.finditer(content)
        if m.group("label").strip().lower() != "unreleased"
    ]
    if not sections:
        return "_No release notes available._"
    start = sections[0].start()
    if len(sections) <= _MAX_CHANGELOG_SECTIONS:
        return content[start:].rstrip()
    end = sections[_MAX_CHANGELOG_SECTIONS].start()
    return content[start:end].rstrip()


def make_footer() -> html.Footer:
    """Render the page footer.

    Includes the always-rendered, initially-hidden CHANGELOG modal as a
    sibling of the footer's content row, so clicking the version button
    can reveal it without touching app-level layout.
    """
    version_label = (
        f"Version {config.version()} — last updated {_last_updated_date()}"
    )
    return html.Footer(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Button(
                                version_label,
                                id="footer-version-btn",
                                type="button",
                                className="bc-footer__version-btn",
                                title="See recent changes",
                            ),
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
                    # Two lines: the results-interpretation caveat (also
                    # carried onto every export) and the tool-only
                    # internal-use notice (deliberately never exported —
                    # see ui/disclaimers.py).
                    html.Div(
                        [
                            html.Div(disclaimers.INTERPRETATION_BANNER),
                            html.Div(disclaimers.INTERNAL_USE),
                        ],
                        className="bc-footer__disclaimer",
                    ),
                ],
                className="bc-footer__inner",
            ),
            _changelog_modal(),
        ],
        className="bc-footer",
    )


def _changelog_modal() -> html.Div:
    """Hidden modal listing the most recent CHANGELOG entries."""
    return html.Div(
        html.Div(
            [
                html.Div(
                    [
                        html.H2("What's new", className="bc-modal__title"),
                        html.Button(
                            "✕",
                            id="footer-changelog-close",
                            type="button",
                            className="bc-modal__close",
                            title="Close",
                            **{"aria-label": "Close changelog"},
                        ),
                    ],
                    className="bc-modal__header",
                ),
                dcc.Markdown(
                    _recent_changelog(),
                    className="bc-modal__content",
                ),
            ],
            className="bc-modal__dialog",
        ),
        id="footer-changelog-modal",
        className="bc-modal",
        style={"display": "none"},
    )


@callback(
    Output("footer-changelog-modal", "style"),
    Input("footer-version-btn", "n_clicks"),
    Input("footer-changelog-close", "n_clicks"),
    prevent_initial_call=True,
)
def _toggle_changelog_modal(_open_clicks: int, _close_clicks: int):
    """Open the modal on version-button click, close it on the close button."""
    if ctx.triggered_id == "footer-version-btn":
        return {"display": "flex"}
    if ctx.triggered_id == "footer-changelog-close":
        return {"display": "none"}
    return no_update
