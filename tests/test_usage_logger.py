"""Tests for the centralized usage logger.

The logger probes its target directory on a background thread, so the
tests wait for ``enabled`` to flip before asserting on written files.
A local ``tmp_path`` stands in for the Object Storage share.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from gwdrawdown.analysis import AnalysisInputs, AnalysisResult
from gwdrawdown.usage_logger import UsageLogger, UsageLogHandler


def _make_inputs() -> AnalysisInputs:
    return AnalysisInputs(
        pumping_lon=-123.6,
        pumping_lat=48.7,
        pumping_x_albers=1_000_000.0,
        pumping_y_albers=380_000.0,
        source_aquifer_id=186,
        source_aquifer_name="Test Aquifer",
        source_subtype_code="4b",
        transmissivity_m2_per_day=250.0,
        storativity=0.005,
        ts_overridden=False,
        Q_value=3.97,
        Q_unit="L/s",
        Q_m3_per_day=343.0,
        duration_days=90.0,
        buffer_radius_m=1000.0,
        same_aquifer_filter=False,
        u_threshold=0.01,
        at_risk_fraction=0.30,
        pumping_well_tag_number=96473,
    )


def _enabled_logger(log_dir: Path) -> UsageLogger:
    """Construct a logger and wait for its background probe to finish."""
    ul = UsageLogger(log_dir, version="9.9.9", enabled=True)
    for _ in range(100):
        if ul.enabled:
            break
        time.sleep(0.02)
    assert ul.enabled, "background probe did not enable the logger"
    return ul


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def _summary_files(log_dir: Path) -> list[Path]:
    return sorted(log_dir.glob("*_summary.jsonl"))


def _detail_files(log_dir: Path) -> list[Path]:
    return sorted(log_dir.glob("*_detail.jsonl"))


def test_probe_enables_logger_and_writes_app_start(tmp_path: Path) -> None:
    ul = _enabled_logger(tmp_path)
    assert ul.enabled is True
    # The successful probe writes one "Application started" detail event.
    detail = _detail_files(tmp_path)
    assert len(detail) == 1
    records = _read_jsonl(detail[0])
    assert records[0]["message"] == "Application started"
    assert records[0]["tool_version"] == "9.9.9"


def test_log_analysis_writes_summary_record(tmp_path: Path) -> None:
    ul = _enabled_logger(tmp_path)
    result = AnalysisResult(inputs=_make_inputs(), n_total=7, n_at_risk=2)

    ul.log_analysis(result, bcgw_user="IDIR\\OFFICER")

    summary = _summary_files(tmp_path)
    assert len(summary) == 1
    record = _read_jsonl(summary[0])[0]
    assert record["status"] == "success"
    assert record["run_id"] == result.run_id
    assert record["bcgw_user"] == "IDIR\\OFFICER"
    assert record["tool_version"] == "9.9.9"
    assert record["pumping_lat"] == 48.7
    assert record["pumping_lon"] == -123.6
    assert record["pumping_well_tag_number"] == 96473
    assert record["n_total"] == 7
    assert record["n_at_risk"] == 2
    # The password must never reach the log.
    assert "password" not in json.dumps(record).lower()


def test_log_analysis_error_writes_error_summary_and_detail(tmp_path: Path) -> None:
    ul = _enabled_logger(tmp_path)

    ul.log_analysis_error("Pipeline error: boom", bcgw_user="IDIR\\OFFICER")

    record = _read_jsonl(_summary_files(tmp_path)[0])[0]
    assert record["status"] == "error"
    assert record["error_message"] == "Pipeline error: boom"
    # Also lands in the detail log as an ERROR event.
    events = _read_jsonl(_detail_files(tmp_path)[0])
    assert any(e["level"] == "ERROR" and e["stage"] == "analysis" for e in events)


def test_log_login_records_success_and_failure(tmp_path: Path) -> None:
    ul = _enabled_logger(tmp_path)

    ul.log_login("officer", success=True)
    ul.log_login("officer", success=False, error_code="ORA-01017")

    events = _read_jsonl(_detail_files(tmp_path)[0])
    logins = [e for e in events if e["stage"] == "login"]
    assert {e["success"] for e in logins} == {True, False}
    failed = next(e for e in logins if e["success"] is False)
    assert failed["error_code"] == "ORA-01017"
    assert failed["level"] == "WARNING"


def test_disabled_logger_is_a_silent_noop(tmp_path: Path) -> None:
    """A logger constructed with enabled=False writes nothing, never raises."""
    ul = UsageLogger(tmp_path, version="9.9.9", enabled=False)
    assert ul.enabled is False

    ul.log_analysis(AnalysisResult(inputs=_make_inputs()))
    ul.log_login("officer", success=True)
    ul.log_event("ERROR", "test", "should not be written")

    assert list(tmp_path.iterdir()) == []


def test_unwritable_directory_disables_logging_without_raising() -> None:
    """An unreachable share leaves the logger disabled, not crashed."""
    # A path *under an existing file* (this test module) cannot be
    # created as a directory — stands in for an unreachable share.
    bad_dir = Path(__file__) / "cannot" / "exist"
    ul = UsageLogger(bad_dir, version="9.9.9", enabled=True)
    # Give the background probe thread time to run and fail.
    time.sleep(0.3)
    assert ul.enabled is False
    # Writes are still safe no-ops.
    ul.log_login("officer", success=True)
    ul.log_analysis(AnalysisResult(inputs=_make_inputs()))


def test_summary_record_is_written_as_readable_utf8(tmp_path: Path) -> None:
    """Non-ASCII content (m³, em dashes) is not escaped to \\uXXXX."""
    ul = _enabled_logger(tmp_path)
    inputs = AnalysisInputs.from_json(
        {
            **_make_inputs().to_json(),
            "Q_unit": "m³/d",
            "source_aquifer_name": "211 (bedrock) — directly overlapping",
        }
    )
    ul.log_analysis(AnalysisResult(inputs=inputs))

    raw = _summary_files(tmp_path)[0].read_text("utf-8")
    assert "m³/d" in raw
    assert "—" in raw
    assert "\\u" not in raw


def test_log_handler_skips_already_captured_records(tmp_path: Path) -> None:
    """Records flagged usage_logged=True are not forwarded (no duplicate)."""
    ul = _enabled_logger(tmp_path)
    handler = UsageLogHandler(ul)
    test_logger = logging.getLogger("gwdrawdown.test_dedup_target")
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.DEBUG)
    try:
        test_logger.warning("already captured", extra={"usage_logged": True})
        test_logger.warning("not captured")
    finally:
        test_logger.removeHandler(handler)

    messages = [e["message"] for e in _read_jsonl(_detail_files(tmp_path)[0])]
    assert "not captured" in messages
    assert "already captured" not in messages


def test_log_handler_forwards_warnings_to_detail_log(tmp_path: Path) -> None:
    ul = _enabled_logger(tmp_path)
    handler = UsageLogHandler(ul)
    test_logger = logging.getLogger("gwdrawdown.test_handler_target")
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.DEBUG)
    try:
        test_logger.info("info is below threshold, dropped")
        test_logger.warning("a forwarded warning")
    finally:
        test_logger.removeHandler(handler)

    events = _read_jsonl(_detail_files(tmp_path)[0])
    messages = [e["message"] for e in events]
    assert "a forwarded warning" in messages
    assert "info is below threshold, dropped" not in messages
