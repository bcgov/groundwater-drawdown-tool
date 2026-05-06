"""Default transmissivity (T) and storativity (S) lookup by aquifer subtype.

The lookup table is loaded from ``data/ts_lookup.csv``, sourced from the
legacy Excel `AquiferProperty_DB` sheet (Wei et al. 2009 medians).
See DATA_REFERENCE.md §4 for the values and provenance.

Aquifer subtype codes are reported by `GW_AQUIFER_ATTRS.AQUIFER_SUBTYPE_CODE`
in BCGW. Codes seen in production: ``1a``, ``1b``, ``1c``, ``2``, ``3``,
``4a``, ``4b``, ``4c``, ``5a``, ``5b``, ``6a``, ``6b``, ``UNK``.

`5b` (karstic limestone) is in the table but flagged ``valid = no``;
karstic flow is not amenable to a single Cooper-Jacob (T, S) and the
team requires manual entry. `UNK` is not in the table at all.

In both "no valid lookup" cases this module returns ``None``; the UI
catches that and prompts the user for manual T/S entry.

CLIENT_TBD: Q1 — confirm the lookup values match current team practice.
CLIENT_TBD: Q2 — currently a single (T, S) per subtype, not a range.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from gwdrawdown import config


@dataclass(frozen=True)
class AquiferProperties:
    """Default T and S for an aquifer subtype.

    Attributes:
        subtype_code: e.g. ``"1a"``, ``"4b"``.
        subtype_description: Human-readable name for display in the UI.
        T_m2_per_day: Transmissivity, m²/day.
        S: Storativity, dimensionless.
    """

    subtype_code: str
    subtype_description: str
    T_m2_per_day: float
    S: float


@lru_cache(maxsize=1)
def load_ts_lookup(
    csv_path: Path | None = None,
) -> dict[str, AquiferProperties]:
    """Load the T/S lookup table, indexed by subtype code.

    Cached on first call. Pass an explicit `csv_path` only in tests; the
    production path comes from `config.TS_LOOKUP_PATH`.

    Rows whose ``valid`` column is not ``yes`` are excluded — callers
    should treat a missing key as "manual entry required". This keeps
    the contract single-meaning: a key is present iff the lookup is
    usable for Cooper-Jacob.
    """
    path = csv_path if csv_path is not None else config.TS_LOOKUP_PATH
    table: dict[str, AquiferProperties] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["valid"].strip().lower() != "yes":
                continue
            table[row["subtype_code"]] = AquiferProperties(
                subtype_code=row["subtype_code"],
                subtype_description=row["subtype_description"],
                T_m2_per_day=float(row["T_m2_per_day"]),
                S=float(row["S_dimensionless"]),
            )
    if not table:
        raise ValueError(f"No valid aquifer subtypes loaded from {path}")
    return table


def lookup(subtype_code: str | None) -> AquiferProperties | None:
    """Return default T/S for an aquifer subtype code, or None.

    Returns ``None`` when:
      - ``subtype_code`` is None or empty,
      - the code is not in the lookup table (e.g. ``"UNK"``),
      - the code is flagged ``valid = no`` in the CSV (e.g. ``"5b"``).

    The UI handles ``None`` by requiring the Water Officer to enter T
    and S manually.
    """
    if not subtype_code:
        return None
    return load_ts_lookup().get(subtype_code)
