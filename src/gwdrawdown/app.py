"""Dash entry point for the Groundwater Drawdown Tool.

Wires up:

- The Dash app with multi-page routing (``use_pages=True``) — pages are
  auto-discovered from ``src/gwdrawdown/ui/pages``.
- Server-side session storage (Flask-Session, filesystem backend at
  ``config.SESSION_DIR``) with the configured inactivity timeout
  (``config.SESSION_TIMEOUT_HOURS``).
- A Flask ``/logout`` route that closes the BCGW connection pool,
  clears the session, and redirects to ``/login``. Logout is an
  action, not a view, so it lives outside the Dash page registry.

The connection pool is **not** opened here — it is opened by the login
handler in ``ui/pages/login_page.py`` after the user's credentials are
verified. See PROJECT_PLAN.md §6 phase 4 and DESIGN_NOTES.md.
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta
from pathlib import Path

import dash
import flask
from dash import dcc, html
from flask_session import Session

from gwdrawdown import config
from gwdrawdown.data_access import close_pool

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Set up the root logger. File rotation lands in Phase 5."""
    logging.basicConfig(
        level=config.LOG_LEVEL,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _configure_sessions(server: flask.Flask) -> None:
    """Install Flask-Session with the project's filesystem backend."""
    config.SESSION_DIR.mkdir(parents=True, exist_ok=True)
    server.config.update(
        # SECRET_KEY is regenerated at every process start. That invalidates
        # cookies issued by previous runs, which is acceptable for Stage 1
        # (single user, local) — they just sign in again.
        SECRET_KEY=secrets.token_hex(32),
        SESSION_TYPE="filesystem",
        SESSION_FILE_DIR=str(config.SESSION_DIR),
        SESSION_PERMANENT=True,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=config.SESSION_TIMEOUT_HOURS),
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        # Local HTTP only in Stage 1; deployment will flip this on.
        SESSION_COOKIE_SECURE=False,
        # Sign the session-id cookie with SECRET_KEY. Combined with the
        # per-process random SECRET_KEY above, this means cookies issued
        # by a previous app run are rejected after a restart, so a
        # browser tab cannot land on /setup with a stale session while
        # the BCGW pool is gone.
        SESSION_USE_SIGNER=True,
    )
    Session(server)


def _register_routes(server: flask.Flask) -> None:
    """Register Flask routes that sit alongside Dash's page routing."""

    @server.route("/logout")
    def logout() -> flask.Response:
        user = flask.session.get("user")
        if user is not None:
            logger.info("User %r logging out", user)
        try:
            close_pool()
        finally:
            flask.session.clear()
        return flask.redirect("/login")


def create_app() -> dash.Dash:
    """Build and return the Dash application instance."""
    pages_folder = Path(__file__).resolve().parent / "ui" / "pages"
    app = dash.Dash(
        __name__,
        title="Groundwater Drawdown Tool",
        use_pages=True,
        pages_folder=str(pages_folder),
        suppress_callback_exceptions=True,
    )
    _configure_sessions(app.server)
    _register_routes(app.server)
    app.layout = html.Div(
        [
            # App-level store: setup page writes the AnalysisInputs JSON
            # here, results page reads it back. Session storage so a
            # browser reload doesn't lose the inputs while the user is
            # iterating, but the data drops on tab close.
            dcc.Store(id="analysis-inputs", storage_type="session"),
            dash.page_container,
        ]
    )
    return app


def main() -> None:
    """Run the Dash dev server on localhost:8050."""
    _configure_logging()
    logger.info("Starting gwdrawdown v%s", config.version())
    app = create_app()
    app.run(host="127.0.0.1", port=8050, debug=config.DASH_DEBUG)


if __name__ == "__main__":
    main()
