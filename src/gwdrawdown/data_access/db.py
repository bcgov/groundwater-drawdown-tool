"""BCGW Oracle connection pool, lazy-initialised by the login handler.

The pool is **not** created at module import or at app startup. It is
created the first time a user successfully signs in (the login handler
calls ``init_pool(user, password)``) and torn down on logout / session
expiry / app shutdown via ``close_pool()``.

Sizing is small (default 1-2 from ``config``) because Stage 1 is
single-user. The pool abstraction itself is kept for Stage 2 deployment
where the same code services many sessions in one process. See
DESIGN_NOTES.md "Why a connection pool for one user".

User credentials are passed into ``init_pool`` and held inside the
``oracledb`` pool object — never assigned to module globals, never
written to disk. The session layer holds them in server-side session
memory only.

oracledb thin mode is the default in 2.x; no Instant Client is required
on the user's machine. The pool target (``BCGW_DSN``) is hardcoded in
``config`` and is the same for every user. See PROJECT_PLAN.md §4.1.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import oracledb

from gwdrawdown import config

logger = logging.getLogger(__name__)


class PoolNotInitialisedError(RuntimeError):
    """Raised when a caller tries to acquire a connection before login.

    Every data-access caller is expected to be reachable only after
    successful login. Hitting this exception is a routing bug, not a
    user error — surface it loudly rather than papering over it.
    """


# Module-level pool reference. This is the only mutable module-level
# state the project allows: it represents a per-process resource (the
# connection pool to BCGW) and is keyed by the credentials of the
# currently-logged-in user. There is exactly one logged-in user at a
# time in Stage 1.
_pool: oracledb.ConnectionPool | None = None


def init_pool(user: str, password: str) -> None:
    """Create the BCGW connection pool for a logged-in user.

    Called by the login handler after credentials have been validated
    (e.g. by a ``SELECT 1 FROM DUAL`` round-trip). Idempotent
    in the sense that calling it twice without an intervening
    ``close_pool()`` raises — the caller (login handler) is responsible
    for tearing down a previous session before starting a new one.

    IT has confirmed user workstations are permitted outbound TCP to
    bcgw.bcgov:1521 (Q8). If the network posture changes, this is the
    call site that will fail first.

    Args:
        user: BCGW username.
        password: BCGW password (held in oracledb's pool object only).

    Raises:
        RuntimeError: if a pool is already initialised.
        oracledb.DatabaseError: bubbled up from oracledb (bad
            credentials, network unreachable, etc.). Caller should
            catch and surface the message in the login UI.
    """
    global _pool
    if _pool is not None:
        raise RuntimeError(
            "Connection pool already initialised; call close_pool() first."
        )

    # The signed-in user is recorded by usage_logger.py as part of the
    # sign-in event; keep the username out of the general app log to
    # avoid logging credentials in plain text (CodeQL py/clear-text-
    # logging-sensitive-data).
    logger.info("Initialising BCGW connection pool")
    _pool = oracledb.create_pool(
        user=user,
        password=password,
        dsn=config.BCGW_DSN,
        min=config.DB_POOL_MIN,
        max=config.DB_POOL_MAX,
        increment=config.DB_POOL_INCREMENT,
    )


def close_pool() -> None:
    """Tear down the BCGW connection pool, if any.

    Safe to call multiple times and safe to call when the pool was
    never initialised (e.g. logout-without-login on session expiry).
    """
    global _pool
    if _pool is None:
        return
    logger.info("Closing BCGW connection pool")
    try:
        _pool.close()
    finally:
        _pool = None


def is_initialised() -> bool:
    """Return True if ``init_pool`` has been called and the pool is open."""
    return _pool is not None


@contextmanager
def get_connection() -> Iterator[oracledb.Connection]:
    """Acquire a pooled connection for the duration of a ``with`` block.

    On exit the connection is returned to the pool, not closed — that's
    the point of pooling. If the caller raises, the connection is still
    released cleanly.

    Raises:
        PoolNotInitialisedError: if called before ``init_pool``.
    """
    if _pool is None:
        raise PoolNotInitialisedError(
            "BCGW connection pool is not initialised. "
            "The user must sign in before any data-access call."
        )
    conn = _pool.acquire()
    try:
        yield conn
    finally:
        _pool.release(conn)
