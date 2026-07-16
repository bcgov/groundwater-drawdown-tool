"""Run-level export controls for the results page.

Two whole-run exports sit beside the per-table CSV buttons:

- **KML** — every well plus the pumping point, colour-coded by status,
  for opening in Google Earth (clients are more familiar with Google
  Earth than GeoJSON, so KML is the spatial-export format).
- **PDF** — the full licence-assessment artifact: parameters, the
  at-risk table, both charts, and the per-well details table.

The PDF needs the two Plotly charts as images. Rather than render them
server-side (which would pull in ``kaleido`` and a bundled Chromium),
a clientside callback captures the already-drawn charts with
``Plotly.toImage`` and stashes the PNG data-URIs in a Store. The
server-side build callback then fires off that Store, decodes the
images, and streams the PDF back. So the export is a two-hop chain:

    PDF button click
      -> clientside capture  -> ``pdf-chart-images`` Store
      -> server ``build_pdf`` -> ``export-pdf-download``

Both build callbacks apply any active per-well overrides via
`analysis.apply_overrides` so the exports match the on-screen tables.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from dash import (
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    dcc,
    html,
    no_update,
)

from gwdrawdown import config
from gwdrawdown.analysis import AnalysisResult, apply_overrides
from gwdrawdown.ui.components.export_html_map import build_html_map
from gwdrawdown.ui.components.export_kml import build_kml
from gwdrawdown.ui.components.export_pdf import build_pdf
from gwdrawdown.ui.session import current_user

logger = logging.getLogger(__name__)

_EXPORT_BUTTON_STYLE = {
    "padding": "0.45rem 1rem",
    "border": "1px solid #1565c0",
    "backgroundColor": "#1565c0",
    "color": "white",
    "borderRadius": "3px",
    "cursor": "pointer",
    "fontSize": "0.85rem",
    "marginRight": "0.5rem",
}

_SECTION_STYLE = {
    "border": "1px solid var(--bc-border, #D9D9D9)",
    "borderRadius": "var(--bc-radius-lg, 6px)",
    "padding": "0.85rem 1.1rem",
    "marginBottom": "1.5rem",
    "backgroundColor": "var(--bc-surface, #FFFFFF)",
}


def build_export_bar() -> html.Div:
    """Static export section: PDF / HTML / KML buttons, downloads, image Store.

    Lives inside ``results-content`` so it only shows once an analysis
    has been run. The CSV buttons stay on their respective tables —
    these three are whole-run exports.
    """
    return html.Div(
        [
            html.Span(
                "Export this analysis: ",
                style={"fontWeight": "600", "marginRight": "0.5rem"},
            ),
            html.Button(
                "Download PDF report",
                id="export-pdf-btn",
                n_clicks=0,
                style=_EXPORT_BUTTON_STYLE,
            ),
            html.Button(
                "Download interactive map (HTML)",
                id="export-html-btn",
                n_clicks=0,
                style=_EXPORT_BUTTON_STYLE,
            ),
            html.Button(
                "Download KML (Google Earth)",
                id="export-kml-btn",
                n_clicks=0,
                style=_EXPORT_BUTTON_STYLE,
            ),
            html.Div(
                "The tables further down each have their own CSV export "
                "button, and any chart can be saved as an image from the "
                "camera icon in its top-right toolbar.",
                style={
                    "fontSize": "0.8rem",
                    "color": "#555",
                    "marginTop": "0.5rem",
                },
            ),
            dcc.Download(id="export-pdf-download"),
            dcc.Download(id="export-html-download"),
            dcc.Download(id="export-kml-download"),
            # Transient store for the browser-captured chart PNGs; only
            # written by the clientside callback on a PDF-button click.
            dcc.Store(id="pdf-chart-images", storage_type="memory"),
        ],
        style=_SECTION_STYLE,
    )


def _coerce_overrides(
    raw: dict[str, Any] | None,
) -> dict[int, dict[str, float | None]]:
    """Re-key the JSON-stored overrides to ``{int(WTN): {...}}``.

    Mirrors `results_page._coerce_overrides`; kept local so this module
    doesn't import the page. sessionStorage stringifies dict keys.
    """
    if not raw:
        return {}
    out: dict[int, dict[str, float | None]] = {}
    for k, v in raw.items():
        try:
            wtn = int(k)
        except (TypeError, ValueError):
            continue
        if isinstance(v, dict):
            out[wtn] = v
    return out


def _resolve(
    result_data: dict[str, Any] | None,
    overrides_data: dict[str, Any] | None,
) -> tuple[AnalysisResult, dict[int, dict[str, float | None]]] | None:
    """Deserialise the cached result and apply overrides, or None."""
    if not result_data or "_error" in result_data:
        return None
    try:
        base = AnalysisResult.from_json(result_data)
    except (TypeError, KeyError, ValueError):
        logger.exception("Bad analysis-result payload (export)")
        return None
    overrides = _coerce_overrides(overrides_data)
    return apply_overrides(base, overrides), overrides


@callback(
    Output("export-kml-download", "data"),
    Input("export-kml-btn", "n_clicks"),
    State("analysis-result", "data"),
    State("well-overrides", "data"),
    prevent_initial_call=True,
)
def export_kml(
    _n_clicks: int,
    result_data: dict[str, Any] | None,
    overrides_data: dict[str, Any] | None,
) -> object:
    """Build and stream the KML file for the current run."""
    resolved = _resolve(result_data, overrides_data)
    if resolved is None:
        return no_update
    current, overrides = resolved
    kml = build_kml(current, overrides_by_wtn=overrides)
    return dcc.send_string(kml, f"drawdown-KML-{current.run_id[:8]}.kml")


@callback(
    Output("export-html-download", "data"),
    Input("export-html-btn", "n_clicks"),
    State("analysis-result", "data"),
    State("well-overrides", "data"),
    prevent_initial_call=True,
)
def export_html_map_file(
    _n_clicks: int,
    result_data: dict[str, Any] | None,
    overrides_data: dict[str, Any] | None,
) -> object:
    """Build and stream the standalone interactive-map HTML file."""
    resolved = _resolve(result_data, overrides_data)
    if resolved is None:
        return no_update
    current, overrides = resolved
    html_doc = build_html_map(current, overrides_by_wtn=overrides)
    return dcc.send_string(html_doc, f"drawdown-map-{current.run_id[:8]}.html")


def _decode_data_uri(uri: object) -> bytes | None:
    """Decode a ``data:image/png;base64,...`` URI to raw bytes."""
    if not isinstance(uri, str) or "," not in uri:
        return None
    try:
        return base64.b64decode(uri.split(",", 1)[1])
    except (ValueError, TypeError):
        return None


@callback(
    Output("export-pdf-download", "data"),
    Input("pdf-chart-images", "data"),
    State("analysis-result", "data"),
    State("well-overrides", "data"),
    prevent_initial_call=True,
)
def export_pdf(
    images: dict[str, Any] | None,
    result_data: dict[str, Any] | None,
    overrides_data: dict[str, Any] | None,
) -> object:
    """Build the PDF once the clientside callback has captured the charts.

    Fired by a change to ``pdf-chart-images`` (written only on a PDF
    button click). The chart PNGs may be ``None`` if the browser
    capture failed — `build_pdf` substitutes a placeholder note.
    """
    if not images:
        return no_update
    resolved = _resolve(result_data, overrides_data)
    if resolved is None:
        return no_update
    current, overrides = resolved
    pdf_bytes = build_pdf(
        current,
        user=current_user() or "—",
        version=config.version(),
        overrides_by_wtn=overrides,
        dd_chart_png=_decode_data_uri(images.get("dd")),
        impact_chart_png=_decode_data_uri(images.get("impact")),
    )
    return dcc.send_bytes(pdf_bytes, f"drawdown-report-{current.run_id[:8]}.pdf")


# Clientside capture of the two Plotly charts. Runs on a PDF-button
# click, calls Plotly.toImage on each graph div, and writes the PNG
# data-URIs (plus a timestamp so a repeat export re-triggers the
# server callback) into the pdf-chart-images Store. Returning a
# Promise from a clientside callback is supported by Dash; toImage is
# async. A capture failure resolves to nulls — the server build then
# falls back to a "chart unavailable" note rather than erroring.
#
# No explicit width/height is passed to toImage: each chart is
# captured at its current rendered size (scale 2 for resolution).
# That matters for the impact chart, whose on-screen height grows
# with the well count — forcing a fixed height would squash a
# many-well chart. `build_pdf` scales each captured image to fit its
# PDF page while preserving aspect.
clientside_callback(
    """
    async function(nClicks) {
        if (!nClicks) { return window.dash_clientside.no_update; }
        function grab(id) {
            var host = document.getElementById(id);
            if (!host || !window.Plotly) { return Promise.resolve(null); }
            var gd = host.querySelector('.js-plotly-plot') || host;
            return window.Plotly.toImage(
                gd, {format: 'png', scale: 2}
            ).catch(function() { return null; });
        }
        var dd = await grab('dd-chart');
        var impact = await grab('impact-chart');
        return {dd: dd, impact: impact, ts: Date.now()};
    }
    """,
    Output("pdf-chart-images", "data"),
    Input("export-pdf-btn", "n_clicks"),
    prevent_initial_call=True,
)
