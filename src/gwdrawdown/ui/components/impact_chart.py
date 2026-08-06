"""Horizontal Impact-% bar chart for the results page.

Sits below the distance-drawdown chart as a scan-at-a-glance view
of which wells are closest to (or past) the at-risk threshold. One
horizontal bar per well, coloured by `WellStatus` using the shared
palette so the impact chart, the distance-drawdown chart, the per-
well status cells, and the map markers all read consistently.

Distance-drawdown answers "where on the cone does each well sit?"
The Impact-% chart answers "is each well safe?" — the question
licence assessments actually have to answer. Both views matter; this
one is faster to scan when the buffer is busy.

Conventions:

- Bars are sorted descending by impact so the highest-risk wells
  sit at the top of the chart.
- The at-risk threshold (from ``inputs.at_risk_fraction``) is drawn
  as a vertical dashed line; bars crossing the line are AT_RISK by
  definition. The line is dark rather than red on purpose — see
  ``_THRESHOLD_LINE_COLOR``. The results-page caption describes it as
  "the dashed vertical line" so the wording tracks the colour.
- Wells with no computable impact (INSUFFICIENT_DATA, SUSPECT_DATA)
  are excluded — their row in the per-well details table is where
  the data-quality conversation belongs. A small caption below the
  chart calls out how many wells were excluded so officers know to
  look there.
- If any well's impact exceeds 100 %, the X axis extends to fit it
  (no clipping); the threshold line stays at 30 % (or whatever the
  config value is).
- Every bar carries its WTN on the y axis wherever there is room to
  read it — Plotly's automatic tick thinning is overridden, because a
  chart showing 40 bars and 13 labels reads as a rendering fault
  (client feedback, 2026-07). Past the point where labels genuinely
  cannot fit, the thinning stands and the caption says so.
"""

from __future__ import annotations

import plotly.graph_objects as go

from gwdrawdown.analysis import AnalysisResult
from gwdrawdown.ui.components.palette import (
    SELECTION_COLOR,
    STATUS_COLOR,
)

_DEFAULT_BAR_COLOR = "#9e9e9e"
# Threshold line colour — deliberately not red so it doesn't blend
# into the AT_RISK red bars sitting right next to it. Black reads
# as "this is the boundary" and contrasts with every status colour
# in the shared palette.
_THRESHOLD_LINE_COLOR = "#000000"

# Pixel height per bar (after layout margins). 24 px keeps WTN
# labels readable and lets ~20 wells fit on a single screen
# without scrolling.
_BAR_PIXEL_HEIGHT = 24
# Floor / ceiling so a 1-well buffer doesn't get a 30 px chart and
# a 200-well buffer doesn't get a 4800 px chart that overshadows
# everything else on the page.
#
# The ceiling was 720, which is where item 3d came from: past ~26
# wells the bars compress until Plotly starts thinning the y-axis
# ticks, and WTNs silently disappear from a chart that still shows
# every bar. 1200 lets ~46 wells through at full spacing and ~86
# with every WTN still labelled (see `_MIN_LABELLED_BAR_PX`).
#
# Not raised further on purpose. The PDF export captures this chart
# at its rendered size and box-fits it into one fixed page, so every
# extra pixel of height shrinks the whole chart in the report. 1200
# is the point where the screen gains a lot and the PDF loses little.
_MIN_CHART_HEIGHT = 220
_MAX_CHART_HEIGHT = 1200

# Vertical space per bar below which labelling every well stops being
# legible and starts being a grey smear. Above it the y axis is
# forced to show every WTN (`dtick=1`); below it Plotly's own tick
# thinning is left alone and the caption says so, which is the honest
# failure mode — a reader who can see labels are missing knows to use
# hover or the details table.
_MIN_LABELLED_BAR_PX = 13
# Below this the WTN ticks are still all drawn, just smaller.
_COMFORTABLE_BAR_PX = 18

# Vertical chrome (title, axis, margins) outside the plotting area,
# used to turn a chart height into a per-bar height.
_CHART_CHROME_PX = 80


def _chart_height(well_count: int) -> int:
    """Pixel height for ``well_count`` bars, clamped to the bounds."""
    return max(
        _MIN_CHART_HEIGHT,
        min(_MAX_CHART_HEIGHT, _CHART_CHROME_PX + _BAR_PIXEL_HEIGHT * well_count),
    )


def _wtn_axis_settings(height: int, well_count: int) -> tuple[dict, bool]:
    """Y-axis tick settings, and whether every WTN gets a label.

    Plotly thins category ticks on its own once bars are tight, which
    is how a chart ends up showing 40 bars and 13 labels (item 3d,
    client feedback 2026-07). Where there is room, ``dtick=1`` overrides
    that so bar and label always correspond; where there genuinely
    isn't, the thinning stands and the caller says so in the caption
    rather than letting the reader assume the labels are complete.
    """
    bar_px = (height - _CHART_CHROME_PX) / max(well_count, 1)
    if bar_px < _MIN_LABELLED_BAR_PX:
        return {}, False
    font_size = 10 if bar_px >= _COMFORTABLE_BAR_PX else 8
    return {"dtick": 1, "tickfont": {"size": font_size}}, True


def _empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font={"color": "#777", "size": 13},
    )
    fig.update_layout(
        xaxis={"visible": False},
        yaxis={"visible": False},
        height=220,
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig


def make_impact_chart(
    result: AnalysisResult,
    *,
    selected_wtn: int | None = None,
) -> go.Figure:
    """Build the horizontal Impact-% bar chart for `result`.

    Args:
        result: The (override-applied) `AnalysisResult` driving the
            page.
        selected_wtn: Currently-selected well, if any — its bar is
            outlined in blue so selection state agrees with the map
            and the distance-drawdown chart.

    Returns:
        A `plotly.graph_objects.Figure`.
    """
    wells_with_impact = [
        w for w in result.wells if w.impact_fraction is not None
    ]
    excluded = result.n_total - len(wells_with_impact)

    if not wells_with_impact:
        return _empty_figure(
            "No wells with computable impact."
            + (
                f" ({excluded} excluded for missing NPL / depth.)"
                if excluded
                else ""
            )
        )

    # Descending by impact — worst wells at the TOP. Plotly draws
    # categorical Y axes bottom-up, so we reverse here and let
    # ``yaxis.autorange='reversed'`` flip the visual order.
    wells_with_impact.sort(key=lambda w: w.impact_fraction or 0.0)

    impact_pct = [(w.impact_fraction or 0.0) * 100 for w in wells_with_impact]
    wtns = [str(w.well_tag_number) for w in wells_with_impact]
    customdata = [w.well_tag_number for w in wells_with_impact]
    colors = [
        STATUS_COLOR.get(w.well_status, _DEFAULT_BAR_COLOR)
        for w in wells_with_impact
    ]
    # Outline the selected well so selection state is consistent
    # across all three visualisations.
    line_colors = [
        SELECTION_COLOR if w.well_tag_number == selected_wtn else color
        for w, color in zip(wells_with_impact, colors, strict=True)
    ]
    line_widths = [
        2 if w.well_tag_number == selected_wtn else 0
        for w in wells_with_impact
    ]
    hover = [
        (
            f"WTN {w.well_tag_number}<br>"
            f"Impact: {(w.impact_fraction or 0) * 100:.1f}%<br>"
            f"Drawdown: {w.drawdown_m:.3f} m<br>"
            f"SAD: {(f'{w.sad_m:.3f} m' if w.sad_m is not None else '—')}<br>"
            f"Status: {w.well_status.value}"
        )
        for w in wells_with_impact
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=impact_pct,
            y=wtns,
            orientation="h",
            marker={
                "color": colors,
                "line": {"color": line_colors, "width": line_widths},
            },
            customdata=customdata,
            hovertext=hover,
            hoverinfo="text",
            name="Impact",
        )
    )

    # At-risk threshold line. Drawn via `add_shape` (not `add_vline`)
    # so we can explicitly set ``layer="above"`` — Plotly's default
    # shape layer puts vlines underneath bar traces in some versions,
    # which made the line invisible behind the AT_RISK bars.
    threshold_pct = result.inputs.at_risk_fraction * 100
    fig.add_shape(
        type="line",
        x0=threshold_pct,
        x1=threshold_pct,
        y0=0,
        y1=1,
        yref="paper",
        line={"color": _THRESHOLD_LINE_COLOR, "width": 2, "dash": "dash"},
        layer="above",
    )
    fig.add_annotation(
        x=threshold_pct,
        y=1,
        yref="paper",
        yanchor="bottom",
        text=f"{threshold_pct:g}% threshold",
        showarrow=False,
        font={"color": _THRESHOLD_LINE_COLOR, "size": 11},
    )

    # X axis: at least 0 to 100, but extend to fit any well that ran
    # past 100 % impact.
    max_pct = max(100.0, max(impact_pct) * 1.05)

    height = _chart_height(len(wells_with_impact))
    tick_settings, all_wtns_labelled = _wtn_axis_settings(
        height, len(wells_with_impact)
    )

    title_text = (
        "Impact % per well (sorted by magnitude of impact, "
        f"{len(wells_with_impact)} wells)"
    )
    if excluded:
        title_text += (
            f" — {excluded} excluded "
            "(no computable impact; see per-well table)"
        )
    if not all_wtns_labelled:
        # Say it rather than let the reader assume the axis is complete.
        title_text += (
            "<br><sub>Too many wells to label every bar — hover a bar for "
            "its WTN, or use the details table below.</sub>"
        )

    fig.update_layout(
        # Small title font (well under Plotly's 17 px default): both the
        # results page and the PDF export carry a separate "Impact % per
        # well" heading above this chart, so the in-chart title is a
        # secondary caption — it must not compete with that heading, and
        # it stays legible once the figure is scaled down into the PDF.
        title={
            "text": title_text,
            "x": 0.5,
            "xanchor": "center",
            "font": {"size": 11},
        },
        xaxis={
            "title": "Impact (% of SAD)",
            "range": [0, max_pct],
            "ticksuffix": "%",
            "showgrid": True,
            "gridcolor": "#eee",
            "zeroline": False,
        },
        yaxis={
            "title": "WTN",
            "type": "category",
            "automargin": True,
            **tick_settings,
        },
        height=height,
        margin={"l": 80, "r": 30, "t": 60, "b": 50},
        plot_bgcolor="white",
        paper_bgcolor="white",
        bargap=0.25,
        showlegend=False,
    )
    return fig
