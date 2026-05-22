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
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import dash
import flask
from dash import dcc, html
from flask_session import Session

from gwdrawdown import config, usage_logger
from gwdrawdown.data_access import close_pool

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Configure the root logger: console plus a daily-rotating file.

    Replaces the Phase 4 ``basicConfig``. A ``TimedRotatingFileHandler``
    rolls ``<LOG_DIR>/gwdrawdown.log`` at midnight and keeps
    ``config.LOG_RETENTION_DAYS`` days of history. Existing handlers are
    cleared first so the debug-mode reloader (which re-runs ``main`` in a
    child process) does not stack duplicate handlers.
    """
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(config.LOG_LEVEL)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = TimedRotatingFileHandler(
        config.LOG_DIR / "gwdrawdown.log",
        when="midnight",
        backupCount=config.LOG_RETENTION_DAYS,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


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
        # BC Sans from the official BC Gov font CDN. If the CDN is
        # unreachable from the user's workstation (offline, VPN
        # blocked) the @font-face simply fails to load and the page
        # falls back to the system-sans stack declared in
        # `assets/theme.css`. No tool-level error path needed.
        external_stylesheets=[
            "https://static.gov.bc.ca/fonts/BCSans/css/BCSans.css",
        ],
    )
    _configure_sessions(app.server)
    _register_routes(app.server)
    app.layout = html.Div(
        [
            # App-level stores. All three are sessionStorage so a tab
            # refresh keeps state but tab close drops it.
            #
            # - analysis-inputs: setup page writes the AnalysisInputs
            #   JSON here on Run Analysis.
            # - analysis-result: results page caches the pipeline output
            #   so override edits and tab refreshes don't replay the
            #   BCGW queries. Cleared (re-populated) when
            #   analysis-inputs changes.
            # - well-overrides: per-WTN dict of edited cells from the
            #   per-well details table, applied on top of
            #   analysis-result by the render callback.
            dcc.Store(id="analysis-inputs", storage_type="session"),
            dcc.Store(id="analysis-result", storage_type="session"),
            dcc.Store(id="well-overrides", storage_type="session", data={}),
            dash.page_container,
        ]
    )
    return app


def main() -> None:
    """Run the Dash dev server on localhost:8050."""
    _configure_logging()
    logger.info("Starting gwdrawdown v%s", config.version())
    # Centralized usage logging: probes the Object Storage share on a
    # background thread and forwards WARNING+ records to the detail log.
    # A failure here never blocks startup (see usage_logger.py).
    usage_logger.init_usage_logger()
    app = create_app()
    app.run(host="127.0.0.1", port=8050, debug=config.DASH_DEBUG)


if __name__ == "__main__":
    main()
