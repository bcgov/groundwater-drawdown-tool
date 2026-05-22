"""Centralized usage logging to BC Object Storage.

Two log files per calendar month, written as JSONL (one JSON object per
line) to a network share so the GeoBC team can monitor tool health,
generate usage statistics, and troubleshoot field issues across every
user's install:

- ``YYYY-MM_summary.jsonl`` — one record per *analysis run* (each
  "Run Analysis" click). Carries the run inputs and the headline
  outputs (well counts, max drawdown). This is the statistics feed.
- ``YYYY-MM_detail.jsonl`` — one record per *event*: app start, login
  success/failure, pipeline errors, and any WARNING/ERROR forwarded
  from the standard ``logging`` tree via :class:`UsageLogHandler`.
  This is the troubleshooting feed.

JSONL is used (rather than CSV) so concurrent appends never need a
file-level lock and the files can be opened in a text editor without
taking an exclusive lock — the same rationale as the GeoBC LDS tool's
logger, kept consistent on purpose.

Design posture — *logging must never crash or block the tool*:

- Every public method swallows its own exceptions.
- The network share is probed once, on a background thread, so an
  unreachable share (user off the gov network / VPN) does not hang
  app startup. Until the probe succeeds, records are dropped.
- If the share is unreachable or ``config.USAGE_LOGGING_ENABLED`` is
  false, the logger is a silent no-op.

Unlike the LDS tool's logger (one instance per tool *process*), the
Dash app is long-lived and runs many analyses per process, so there is
one process-wide :class:`UsageLogger` — created once at app startup,
reused for every run. Module-level state is acceptable here for the
same reason it is for the standard library root logger: this is
process-wide infrastructure, not per-request application state.

Layering: this module imports ``config`` only. The ``ui`` layer calls
into it; ``core`` and ``data_access`` never do.
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import socket
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gwdrawdown import config

if TYPE_CHECKING:
    from gwdrawdown.analysis import AnalysisResult

logger = logging.getLogger(__name__)


class UsageLogger:
    """Process-wide writer for the centralized usage logs.

    Construct once via :func:`init_usage_logger`; retrieve anywhere via
    :func:`get_usage_logger`. All write methods are fault-tolerant: a
    failure is logged locally (best effort) and otherwise ignored.
    """

    MAX_RETRIES = 3
    RETRY_DELAY = 0.5  # seconds between append retries

    def __init__(self, log_dir: Path, version: str, enabled: bool = True) -> None:
        self.version = version
        self.machine = self._safe(socket.gethostname, "unknown")
        self.os_user = self._os_user()
        # ``enabled`` flips True only after the background probe confirms
        # the share is writable. ``_configured`` gates write attempts.
        self.enabled = False
        self._configured = bool(enabled)
        self._log_dir = log_dir
        # Serialize appends — Dash callbacks run on multiple Flask
        # worker threads and may log concurrently.
        self._lock = threading.Lock()

        if not self._configured:
            logger.info("Usage logging disabled by configuration.")
            return

        # Probe the share off the main thread so a dead network path
        # never delays app startup.
        threading.Thread(
            target=self._initialise, name="usage-logger-init", daemon=True
        ).start()

    # -- internal helpers ----------------------------------------------------

    @staticmethod
    def _safe(fn: Any, default: str) -> str:
        try:
            return str(fn())
        except Exception:
            return default

    def _os_user(self) -> str:
        """Return ``DOMAIN\\user`` (or just the user) for the OS account."""
        try:
            user = (
                os.environ.get("USERNAME")
                or os.environ.get("USER")
                or getpass.getuser()
            )
            domain = os.environ.get("USERDOMAIN", "")
            return f"{domain}\\{user}" if domain else user
        except Exception:
            return "unknown"

    def _initialise(self) -> None:
        """Probe the share; on success enable logging and log app start."""
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            probe = self._log_dir / f".write_test_{os.getpid()}"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except Exception as exc:
            logger.warning(
                "Usage logging disabled: log directory not writable (%s): %s",
                self._log_dir,
                exc,
            )
            return

        self.enabled = True
        logger.info("Usage logging enabled: %s", self._log_dir)
        self._write_detail(
            level="INFO",
            stage="app",
            message="Application started",
            tool_version=self.version,
        )

    def _month_path(self, kind: str) -> Path:
        """Return the current month's ``summary``/``detail`` JSONL path."""
        prefix = datetime.now().strftime("%Y-%m")
        return self._log_dir / f"{prefix}_{kind}.jsonl"

    def _append(self, path: Path, record: dict[str, Any]) -> None:
        """Append one JSON record as a line, with retry. Never raises."""
        if not self.enabled:
            return
        # ensure_ascii=False so non-ASCII content (m³, em dashes in
        # aquifer names) is written as readable UTF-8 rather than \uXXXX
        # escapes. The files are opened with encoding="utf-8".
        line = json.dumps(record, default=str, ensure_ascii=False)
        for attempt in range(self.MAX_RETRIES):
            try:
                with self._lock:
                    with open(path, "a", encoding="utf-8") as fh:
                        fh.write(line + "\n")
                return
            except OSError as exc:
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY)
                else:
                    logger.warning(
                        "Usage log write failed after %d attempts: %s",
                        self.MAX_RETRIES,
                        exc,
                    )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Usage log write failed: %s", exc)
                return

    def _write_detail(self, *, level: str, stage: str, message: str, **fields: Any) -> None:
        """Build and append one detail-log record."""
        record: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "machine": self.machine,
            "os_user": self.os_user,
            "level": level.upper(),
            "stage": stage,
            "message": message,
        }
        for key, value in fields.items():
            if value is not None:
                record[key] = value
        self._append(self._month_path("detail"), record)

    # -- public API ----------------------------------------------------------

    def log_event(
        self,
        level: str,
        stage: str,
        message: str,
        **fields: Any,
    ) -> None:
        """Append a free-form event to the detail log. Never raises."""
        try:
            self._write_detail(level=level, stage=stage, message=message, **fields)
        except Exception:  # pragma: no cover - defensive
            pass

    def log_login(
        self,
        username: str | None,
        *,
        success: bool,
        error_code: str | None = None,
    ) -> None:
        """Record a BCGW sign-in attempt in the detail log. Never raises."""
        try:
            self._write_detail(
                level="INFO" if success else "WARNING",
                stage="login",
                message=(
                    "BCGW sign-in succeeded" if success else "BCGW sign-in failed"
                ),
                bcgw_user=username,
                success=success,
                error_code=error_code,
            )
        except Exception:  # pragma: no cover - defensive
            pass

    def log_analysis(
        self,
        result: AnalysisResult,
        *,
        bcgw_user: str | None = None,
    ) -> None:
        """Append one summary record for a completed analysis run.

        Called once per fresh "Run Analysis" — not on per-well override
        recomputes or browser-tab refreshes. Never raises.
        """
        try:
            inputs = result.inputs
            summary = {
                "run_id": result.run_id,
                "logged_at": datetime.now().isoformat(),
                "run_timestamp": result.run_timestamp.isoformat(),
                "tool_version": self.version,
                "machine": self.machine,
                "os_user": self.os_user,
                "bcgw_user": bcgw_user,
                "status": "success",
                # --- inputs ---
                "pumping_lon": inputs.pumping_lon,
                "pumping_lat": inputs.pumping_lat,
                "pumping_well_tag_number": inputs.pumping_well_tag_number,
                "source_aquifer_id": inputs.source_aquifer_id,
                "source_aquifer_name": inputs.source_aquifer_name,
                "source_subtype_code": inputs.source_subtype_code,
                "is_manual_mode": inputs.is_manual_mode,
                "manual_material": inputs.manual_material,
                "transmissivity_m2_per_day": inputs.transmissivity_m2_per_day,
                "storativity": inputs.storativity,
                "ts_overridden": inputs.ts_overridden,
                "Q_value": inputs.Q_value,
                "Q_unit": inputs.Q_unit,
                "Q_m3_per_day": inputs.Q_m3_per_day,
                "duration_days": inputs.duration_days,
                "buffer_radius_m": inputs.buffer_radius_m,
                "same_aquifer_filter": inputs.same_aquifer_filter,
                # --- outputs ---
                "n_total": result.n_total,
                "n_at_risk": result.n_at_risk,
                "n_ok": result.n_ok,
                "n_insufficient_data": result.n_insufficient_data,
                "n_suspect_data": result.n_suspect_data,
                "n_outside_validity": result.n_outside_validity,
                "max_drawdown_m": result.max_drawdown_m,
            }
            self._append(self._month_path("summary"), summary)
        except Exception:  # pragma: no cover - defensive
            pass

    def log_analysis_error(
        self,
        message: str,
        *,
        bcgw_user: str | None = None,
    ) -> None:
        """Record a failed analysis run in both logs. Never raises."""
        try:
            self.log_event(
                "ERROR", "analysis", message, bcgw_user=bcgw_user
            )
            self._append(
                self._month_path("summary"),
                {
                    "logged_at": datetime.now().isoformat(),
                    "tool_version": self.version,
                    "machine": self.machine,
                    "os_user": self.os_user,
                    "bcgw_user": bcgw_user,
                    "status": "error",
                    "error_message": message,
                },
            )
        except Exception:  # pragma: no cover - defensive
            pass


class UsageLogHandler(logging.Handler):
    """Forward WARNING+ records from the ``logging`` tree to the detail log.

    Acts as a safety net for warnings/errors that are not already
    captured by a dedicated method. Two kinds of record are skipped:

    - records emitted by :mod:`gwdrawdown.usage_logger` itself, so a
      write failure that logs a warning cannot feed back into another
      write attempt;
    - records carrying ``extra={"usage_logged": True}`` — the caller
      has already written a structured event (``log_login``,
      ``log_analysis_error``, ...) and forwarding would only duplicate it.
    """

    def __init__(self, usage_logger: UsageLogger) -> None:
        super().__init__(level=logging.WARNING)
        self._usage_logger = usage_logger

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.name == __name__:
                return
            if getattr(record, "usage_logged", False):
                return
            self._usage_logger.log_event(
                level=record.levelname,
                stage="logging",
                message=record.getMessage(),
                logger_name=record.name,
                lineno=record.lineno,
            )
        except Exception:  # pragma: no cover - defensive
            pass


# --- process-wide instance ---------------------------------------------------

_USAGE_LOGGER: UsageLogger | None = None


def init_usage_logger() -> UsageLogger:
    """Create the process-wide usage logger and attach the log handler.

    Called once from ``app.main``. Kicks off the background share probe
    and (on success) writes the "Application started" detail record.
    """
    global _USAGE_LOGGER
    _USAGE_LOGGER = UsageLogger(
        log_dir=config.USAGE_LOG_DIR,
        version=config.version(),
        enabled=config.USAGE_LOGGING_ENABLED,
    )
    logging.getLogger().addHandler(UsageLogHandler(_USAGE_LOGGER))
    return _USAGE_LOGGER


def get_usage_logger() -> UsageLogger:
    """Return the process-wide usage logger.

    Falls back to a disabled, never-probing instance if called before
    :func:`init_usage_logger` — e.g. from a unit test — so callers can
    always log unconditionally without a None check.
    """
    global _USAGE_LOGGER
    if _USAGE_LOGGER is None:
        _USAGE_LOGGER = UsageLogger(
            log_dir=config.USAGE_LOG_DIR,
            version=config.version(),
            enabled=False,
        )
    return _USAGE_LOGGER
