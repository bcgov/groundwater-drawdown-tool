"""Phase 3 smoke test for BCGW connectivity and the four queries.

Prompts the developer for BCGW username and password (via ``getpass``,
never read from ``.env`` — same posture as the eventual login UI), opens
the connection pool, runs each of the four queries against a known BC
test point, prints results, and closes the pool.

The default test point is on Vancouver Island. It is known to fall
inside two stacked aquifer polygons (id 198 — bedrock, id 186 — sand
and gravel) so the script also exercises the same-aquifer filter on the
nearby-wells query using id 186 as the chosen source aquifer.

Usage::

    uv run python scripts/smoke_test_db.py
    uv run python scripts/smoke_test_db.py --point -123.682034,48.759438 \\
                                            --radius 200 \\
                                            --source-aquifer-id 186

This is **not** a pytest test. The live BCGW database is the system
under test; mocking SDO_GEOMETRY would prove nothing useful. Per the
working agreement (PROJECT_PLAN.md §8) Phase 3 is verified by running
this script with valid credentials and inspecting the output.
"""

from __future__ import annotations

import argparse
import getpass
import logging
import sys
from pprint import pformat

import oracledb

from gwdrawdown.core import crs_utils
from gwdrawdown.data_access import (
    PoolNotInitialisedError,
    close_pool,
    get_connection,
    init_pool,
    queries,
)

logger = logging.getLogger("gwdrawdown.smoke_test")

# Default test point: Vancouver Island, intersects aquifers 198 and 186.
DEFAULT_LON = -123.682034
DEFAULT_LAT = 48.759438
DEFAULT_RADIUS_M = 200.0
DEFAULT_SOURCE_AQUIFER_ID = 186


def _parse_point(raw: str) -> tuple[float, float]:
    try:
        lon_s, lat_s = raw.split(",")
        return float(lon_s.strip()), float(lat_s.strip())
    except (ValueError, IndexError) as e:
        raise argparse.ArgumentTypeError(
            f"--point must be 'lon,lat' (e.g. -123.68,48.76); got {raw!r}"
        ) from e


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke test BCGW connectivity and the four data-access queries."
    )
    parser.add_argument(
        "--point",
        type=_parse_point,
        default=(DEFAULT_LON, DEFAULT_LAT),
        help=f"Test point as 'lon,lat' in WGS84. Default: "
        f"{DEFAULT_LON},{DEFAULT_LAT} (Vancouver Island).",
    )
    parser.add_argument(
        "--radius",
        type=float,
        default=DEFAULT_RADIUS_M,
        help=f"Buffer radius in metres for the nearby-wells query. "
        f"Default: {DEFAULT_RADIUS_M:g} m.",
    )
    parser.add_argument(
        "--source-aquifer-id",
        type=int,
        default=DEFAULT_SOURCE_AQUIFER_ID,
        help=f"Aquifer id used to exercise the same-aquifer filter on the "
        f"nearby-wells query. Default: {DEFAULT_SOURCE_AQUIFER_ID}.",
    )
    return parser.parse_args(argv)


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _print_rows(rows: list[dict[str, object]], limit: int = 5) -> None:
    if not rows:
        print("(0 rows)")
        return
    print(f"({len(rows)} rows; showing first {min(limit, len(rows))})")
    for row in rows[:limit]:
        print(pformat(row, sort_dicts=False, width=110))


def _prompt_credentials() -> tuple[str, str]:
    print("BCGW credentials are entered at runtime and never written to disk.")
    user = input("BCGW username: ").strip()
    if not user:
        raise SystemExit("Username is required.")
    password = getpass.getpass("BCGW password: ")
    if not password:
        raise SystemExit("Password is required.")
    return user, password


def run(args: argparse.Namespace) -> int:
    lon, lat = args.point
    x, y = crs_utils.to_albers(lon, lat)

    print(f"Test point WGS84:    ({lon}, {lat})")
    print(f"Test point BC Albers: ({x:.3f}, {y:.3f})")
    print(f"Buffer radius:       {args.radius:g} m")
    print(f"Source aquifer id:   {args.source_aquifer_id}")

    user, password = _prompt_credentials()

    # CLIENT_TBD: Q8 — IT permits outbound TCP to bcgw.bcgov:1521;
    # confirmed at the time of writing. If this connect fails with a
    # network-level error, that's the first thing to re-verify.
    try:
        init_pool(user, password)
    except oracledb.DatabaseError as e:
        print(f"\nFailed to open BCGW connection pool: {e}", file=sys.stderr)
        return 2

    try:
        with get_connection() as conn:
            _print_section("Query 6.2 — aquifers containing the test point")
            aquifers = queries.aquifers_at_point(conn, x_albers=x, y_albers=y)
            _print_rows(aquifers, limit=10)

            _print_section(
                f"Query 6.3 — subtype code for source aquifer "
                f"(id={args.source_aquifer_id})"
            )
            subtype = queries.subtype_code_for_aquifer(
                conn, args.source_aquifer_id
            )
            print(f"AQUIFER_SUBTYPE_CODE: {subtype!r}")

            _print_section(
                f"Query 6.1 — nearby wells within {args.radius:g} m "
                f"(no aquifer filter)"
            )
            wells_all = queries.nearby_wells(
                conn,
                x_albers=x,
                y_albers=y,
                radius_m=args.radius,
            )
            _print_rows(wells_all)

            _print_section(
                f"Query 6.1 — nearby wells filtered to aquifer "
                f"{args.source_aquifer_id}"
            )
            wells_filtered = queries.nearby_wells(
                conn,
                x_albers=x,
                y_albers=y,
                radius_m=args.radius,
                aquifer_id=args.source_aquifer_id,
            )
            _print_rows(wells_filtered)

            _print_section("Query 6.4 — well by tag number")
            sample_wtn: int | None = None
            if wells_all:
                sample_wtn = wells_all[0]["WELL_TAG_NUMBER"]
            if sample_wtn is None:
                print("(no wells returned by query 6.1; skipping)")
            else:
                print(f"Looking up WELL_TAG_NUMBER = {sample_wtn}")
                row = queries.well_by_tag(conn, int(sample_wtn))
                if row is None:
                    print("(no row returned)")
                else:
                    print(pformat(row, sort_dicts=False, width=110))

    except PoolNotInitialisedError as e:
        print(f"\nInternal error: {e}", file=sys.stderr)
        return 3
    except oracledb.DatabaseError as e:
        print(f"\nDatabase error during smoke test: {e}", file=sys.stderr)
        return 4
    finally:
        close_pool()

    print()
    print("Smoke test complete.")
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    args = _parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
