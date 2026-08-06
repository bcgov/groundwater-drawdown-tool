"""Tests for the one query in `data_access.queries` that builds its SQL.

Every other template in that module is a fixed string with fixed bind
names, so there is nothing to test without a live BCGW connection.
``delineated_aquifer_ids`` is different: it assembles an ``IN`` list
whose length depends on the data, which is exactly the shape of query
that tends to grow a string-interpolation bug. These tests drive it
against a fake cursor and pin the two properties that matter — the IDs
are *bound*, never interpolated, and a long list is chunked rather than
sent as one over-long ``IN``.
"""

from __future__ import annotations

from typing import Any

from gwdrawdown.data_access import queries as q


class _FakeCursor:
    """Records executed statements and replays canned rows.

    ``delineated`` is the set of aquifer IDs the fake "database" knows
    about; the cursor returns whichever of the bound IDs are in it, so
    the difference the caller computes is exercised for real.
    """

    def __init__(self, delineated: set[int]) -> None:
        self._delineated = delineated
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._rows: list[tuple[Any, ...]] = []

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, sql: str, binds: dict[str, Any]) -> None:
        self.calls.append((sql, binds))
        self._rows = [
            (aquifer_id,)
            for aquifer_id in binds.values()
            if aquifer_id in self._delineated
        ]

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


class _FakeConnection:
    def __init__(self, delineated: set[int]) -> None:
        self.cursor_obj = _FakeCursor(delineated)

    def cursor(self) -> _FakeCursor:
        return self.cursor_obj


def test_returns_only_the_ids_that_exist() -> None:
    conn = _FakeConnection({186, 199})
    assert q.delineated_aquifer_ids(conn, [186, 199, 1143]) == {186, 199}


def test_empty_input_runs_no_query() -> None:
    conn = _FakeConnection({186})
    assert q.delineated_aquifer_ids(conn, []) == set()
    assert conn.cursor_obj.calls == []


def test_nulls_and_duplicates_are_ignored() -> None:
    conn = _FakeConnection({186})
    assert q.delineated_aquifer_ids(conn, [186, 186, None, 186]) == {186}
    _sql, binds = conn.cursor_obj.calls[0]
    assert list(binds.values()) == [186]


def test_ids_are_bound_not_interpolated() -> None:
    """The IN list carries generated bind NAMES only.

    `queries` is the only module allowed to hold SQL, on the condition
    that values are always bound. A regression here would be a real
    injection surface, since aquifer IDs originate in query results
    rather than in code.
    """
    conn = _FakeConnection({186})
    q.delineated_aquifer_ids(conn, [186, 1143])
    sql, binds = conn.cursor_obj.calls[0]
    assert ":id0" in sql and ":id1" in sql
    assert "1143" not in sql
    assert binds == {"id0": 186, "id1": 1143}


def test_long_id_lists_are_chunked() -> None:
    """Oracle rejects an IN list past 1000 expressions (ORA-01795).

    A buffer normally spans a handful of aquifers, so this is defensive
    — but the failure mode it avoids is losing the whole analysis, not
    just the flag.
    """
    ids = list(range(1, q._MAX_IN_LIST * 2 + 5))
    conn = _FakeConnection(set(ids))
    assert q.delineated_aquifer_ids(conn, ids) == set(ids)
    assert len(conn.cursor_obj.calls) == 3
    for _sql, binds in conn.cursor_obj.calls:
        assert len(binds) <= q._MAX_IN_LIST
