"""Dash entry point for the Groundwater Drawdown Tool.

Phase 1 stub: launches an empty Dash app on http://localhost:8050 and
logs the tool version on startup. The login page, multi-page routing,
session handling, and the analysis pipeline land in later phases. See
PROJECT_PLAN.md §6 for the build order.
"""

from __future__ import annotations

import logging

import dash
from dash import html

from gwdrawdown import config

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Set up the root logger. File rotation is added in Phase 5."""
    logging.basicConfig(
        level=config.LOG_LEVEL,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def create_app() -> dash.Dash:
    """Build and return the Dash application instance."""
    app = dash.Dash(__name__, title="Groundwater Drawdown Tool")
    app.layout = html.Div(
        [
            html.H1("Groundwater Drawdown Tool"),
            html.P(f"Version {config.version()} — Phase 1 skeleton."),
            html.P(
                "Login, setup, and results pages are added in later phases. "
                "See PROJECT_PLAN.md."
            ),
        ],
        style={
            "fontFamily": "sans-serif",
            "padding": "2rem",
            "maxWidth": "640px",
        },
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
