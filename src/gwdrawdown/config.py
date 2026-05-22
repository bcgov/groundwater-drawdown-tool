"""Single source of truth for runtime configuration.

Three categories of "config" exist in this tool, handled differently on
purpose (see DESIGN_NOTES.md):

1. Hardcoded constants — same for every user, every machine. The BCGW DSN
   is the canonical example. Edited by code release, not by users.
2. Optional overrides — defaults defined here, overridable via environment
   variables (loaded from a `.env` file at the project root if present).
   The tool runs without any `.env`.
3. User credentials — never stored. Entered through the login UI on every
   session and held only in server-side session memory.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")

# --- Hardcoded constants -----------------------------------------------------

# Not secret, not user-specific. If BC ever changes the host, that's a code
# release, not a config edit. See PROJECT_PLAN.md §4.1.
BCGW_DSN: Final[str] = "bcgw.bcgov:1521/idwprod1.bcgov"

# AQT account self-service page (BCGW database IDWPROD11). Linked from the
# login page so a user whose sign-in fails can check their own account
# status. The jsessionid in any copied URL is a stale session token and is
# deliberately not included here.
BCGW_ACCOUNT_STATUS_URL: Final[str] = (
    "https://apps.gov.bc.ca/int/aqt/jsp/query.jsp"
)

VERSION_FILE: Final[Path] = PROJECT_ROOT / "version.txt"
DATA_DIR: Final[Path] = PROJECT_ROOT / "data"
TS_LOOKUP_PATH: Final[Path] = DATA_DIR / "ts_lookup.csv"
UNIT_CONVERSIONS_PATH: Final[Path] = DATA_DIR / "unit_conversions.csv"


# --- Optional overrides ------------------------------------------------------

LOG_LEVEL: Final[str] = os.environ.get("LOG_LEVEL", "INFO").upper()

OUTPUT_DIR: Final[Path] = Path(
    os.environ.get("OUTPUT_DIR", str(PROJECT_ROOT / "outputs"))
)

LOG_DIR: Final[Path] = Path(
    os.environ.get("LOG_DIR", str(PROJECT_ROOT / "logs"))
)

# Days of daily-rotated local log files to keep (TimedRotatingFileHandler
# backupCount). See app._configure_logging.
LOG_RETENTION_DAYS: Final[int] = int(os.environ.get("LOG_RETENTION_DAYS", "30"))

# Centralized usage log location. Like BCGW_DSN, the default is a fixed,
# non-secret, non-user-specific path — a code release moves it, not a
# config edit. The .env override exists so a developer can point usage
# logging at a local folder during testing. The tool runs fine when the
# share is unreachable: usage logging silently disables itself and never
# blocks or crashes the tool. See usage_logger.py and PROJECT_PLAN.md §5d.
USAGE_LOG_DIR: Final[Path] = Path(
    os.environ.get(
        "USAGE_LOG_DIR",
        r"\\objectstore2.nrs.bcgov\GSS_Share\authorizations\logs"
        r"\groundwater_drawdown_tool",
    )
)

# Set USAGE_LOGGING_ENABLED=false to disable centralized usage logging
# outright (e.g. for local development or automated tests).
USAGE_LOGGING_ENABLED: Final[bool] = os.environ.get(
    "USAGE_LOGGING_ENABLED", "true"
).lower() in {"1", "true", "yes", "on"}

SESSION_DIR: Final[Path] = Path(
    os.environ.get("SESSION_DIR", str(PROJECT_ROOT / "flask_session"))
)

DASH_DEBUG: Final[bool] = os.environ.get("DASH_DEBUG", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Default pumping duration. The legacy Excel used 100 d (east-coast
# Vancouver Island dry-season convention); the client directed 90 d in
# Phase 5, confirmed as the default for all of BC (Q4, Q10).
DEFAULT_PUMPING_DURATION_DAYS: Final[float] = float(
    os.environ.get("DEFAULT_PUMPING_DURATION_DAYS", "90")
)

# CLIENT_TBD: Q3 — at-risk threshold (matches legacy Excel `Impact!V` and
# `InputValues!B30` filter at 30%).
AT_RISK_DRAWDOWN_FRACTION: Final[float] = float(
    os.environ.get("AT_RISK_DRAWDOWN_FRACTION", "0.30")
)

# Cooper-Jacob is only valid when u = r²S / (4Tt) is small. Standard
# literature value is 0.01; some sources allow 0.05.
COOPER_JACOB_U_THRESHOLD: Final[float] = float(
    os.environ.get("COOPER_JACOB_U_THRESHOLD", "0.01")
)

SESSION_TIMEOUT_HOURS: Final[float] = float(
    os.environ.get("SESSION_TIMEOUT_HOURS", "8")
)

# Connection-pool sizing. Single-user app, so 1/2 is enough; the abstraction
# is kept for Stage 2 (more sessions per process). See PROJECT_PLAN.md §4.1.
DB_POOL_MIN: Final[int] = int(os.environ.get("DB_POOL_MIN", "1"))
DB_POOL_MAX: Final[int] = int(os.environ.get("DB_POOL_MAX", "2"))
DB_POOL_INCREMENT: Final[int] = int(os.environ.get("DB_POOL_INCREMENT", "1"))


def version() -> str:
    """Return the current tool version as written in version.txt.

    Read at call time rather than cached so that the Phase 6 auto-updater
    can swap the file under a running process and the next read picks up
    the new value.
    """
    return VERSION_FILE.read_text(encoding="utf-8").strip()
