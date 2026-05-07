"""Server-side session helpers for the Dash UI.

Reads from Flask's ``session`` (server-side, filesystem backend
configured in ``app.py``). The username is stored in the session for
footer display and audit logging; the password is held inside
``oracledb``'s pool object only and never reaches the session. See
DESIGN_NOTES.md "Why BCGW credentials are entered at runtime".
"""

from __future__ import annotations

import flask

USER_KEY = "user"


def current_user() -> str | None:
    """Return the username of the logged-in user, or None if unauthenticated."""
    return flask.session.get(USER_KEY)


def is_authenticated() -> bool:
    """Return True if the current request has a logged-in user."""
    return current_user() is not None


def set_user(username: str) -> None:
    """Mark the session as authenticated and pin the lifetime to permanent.

    ``permanent`` here means "use ``PERMANENT_SESSION_LIFETIME``" rather
    than browser-session-only — the cookie persists until the configured
    inactivity timeout (default 8 hours, ``config.SESSION_TIMEOUT_HOURS``).
    """
    flask.session[USER_KEY] = username
    flask.session.permanent = True


def clear() -> None:
    """Drop all keys from the current session (logout, expiry, error path)."""
    flask.session.clear()
