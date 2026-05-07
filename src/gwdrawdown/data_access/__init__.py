"""BCGW Oracle data access. Imports from `gwdrawdown.config` only.

All SQL strings live in `queries.py`; the connection pool lives in `db.py`.
See DATA_REFERENCE.md for the schema this layer talks to.
"""

from __future__ import annotations

from gwdrawdown.data_access.db import (
    PoolNotInitialisedError,
    close_pool,
    get_connection,
    init_pool,
    is_initialised,
)

__all__ = [
    "PoolNotInitialisedError",
    "close_pool",
    "get_connection",
    "init_pool",
    "is_initialised",
]
