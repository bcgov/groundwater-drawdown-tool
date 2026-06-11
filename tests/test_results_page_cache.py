"""Regression tests for the results-page pipeline cache guard.

`run_pipeline_if_needed` must NOT replay the BCGW pipeline (and must
not wipe per-well overrides) when the cached `analysis-result` was
produced from the same `analysis-inputs` — the F5-refresh case. The
fingerprint comparison is what enforces that; these tests pin it down.

Page modules call ``dash.register_page`` at import time, which requires
a pages-enabled Dash app to exist first, so the module is imported via
``create_app()`` (which auto-discovers every page) rather than directly.
"""

from __future__ import annotations

import pytest
from dash import no_update

from gwdrawdown.app import create_app


@pytest.fixture(scope="module")
def app():
    return create_app()


@pytest.fixture(scope="module")
def results_page(app):
    from gwdrawdown.ui.pages import results_page as rp

    return rp


def test_no_inputs_is_a_noop(results_page):
    out = results_page.run_pipeline_if_needed(None, None)
    assert out == (no_update, no_update, no_update)


def test_matching_fingerprint_skips_rerun_and_keeps_overrides(results_page):
    inputs = {"pumping_lon": -123.5, "pumping_lat": 48.8, "Q_value": 200.0}
    cached = {"_fingerprint": results_page._inputs_fingerprint(inputs)}
    out = results_page.run_pipeline_if_needed(inputs, cached)
    # All three outputs untouched: result, well-overrides, selected-well.
    assert out == (no_update, no_update, no_update)


def test_fingerprint_ignores_key_order(results_page):
    a = {"pumping_lon": -123.5, "Q_value": 200.0}
    b = {"Q_value": 200.0, "pumping_lon": -123.5}
    assert results_page._inputs_fingerprint(a) == results_page._inputs_fingerprint(b)


def test_stale_fingerprint_reruns_and_resets_overrides(app, results_page):
    """A changed-inputs payload must go down the re-run path.

    There is no BCGW pool in tests, so the re-run surfaces an error
    payload — which is exactly the evidence that the pipeline was
    attempted — and resets overrides and selection for the new run.
    """
    inputs = {"pumping_lon": -123.5}  # incomplete: from_json will fail
    cached = {"_fingerprint": "stale-fingerprint-from-previous-inputs"}
    with app.server.test_request_context("/results"):
        result, overrides, selected = results_page.run_pipeline_if_needed(
            inputs, cached
        )
    assert "_error" in result
    assert overrides == {}
    assert selected is None


def test_error_payload_has_no_fingerprint_so_refresh_retries(app, results_page):
    """A cached error payload must not satisfy the cache guard."""
    inputs = {"pumping_lon": -123.5}
    cached = {"_error": "Pipeline error: BCGW unreachable"}
    with app.server.test_request_context("/results"):
        result, _overrides, _selected = results_page.run_pipeline_if_needed(
            inputs, cached
        )
    # The guard fell through to the run path (which errors again here,
    # for lack of a pool) instead of returning no_update.
    assert result is not no_update
    assert "_error" in result
