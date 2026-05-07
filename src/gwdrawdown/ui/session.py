"""Server-side session helpers for the Dash UI.

Reads from Flask's ``session`` (server-side, filesystem backend
configured in ``app.py``). The username is stored in the session for
footer display and audit logging; the password is held inside
``oracledb``'s pool object only and never reaches the session. See
DESIGN_NOTES.md "Why BCGW credentials are entered at runtime".

Authenticated state requires both: a username in the session **and**
an open BCGW connection pool. After an app restart the session
cookie may still be valid (8 h lifetime, signed with the new
``SECRET_KEY``) but the in-memory pool is gone — `is_authenticated`
detects that mismatch, clears the session, and the UI guard sends
the user back to ``/login`` for a fresh sign-in.
"""

from __future__ import annotations

import logging

import flask

from gwdrawdown import data_access

logger = logging.getLogger(__name__)

USER_KEY = "user"


def current_user() -> str | None:
    """Return the username of the logged-in user, or None if unauthenticated."""
    return flask.session.get(USER_KEY)


def is_authenticated() -> bool:
    """Return True iff the session has a user **and** the pool is open.

    A session without a live pool is a stale cookie from a previous
    app run. Clear it so the next layout render redirects to
    ``/login`` instead of letting callbacks blow up with
    ``PoolNotInitialisedError``.
    """
    user = current_user()
    if user is None:
        return False
    if not data_access.is_initialised():
        logger.info(
            "Stale session for user %r (BCGW pool not initialised); clearing.",
            user,
        )
        flask.session.clear()
        return False
    return True


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
