"""PDF export of a full analysis run.

Produces the licence-assessment artifact described in PROJECT_PLAN.md
§5 Phase 5c: input parameters, a summary-card row, a Cooper-Jacob
assumptions disclaimer, the at-risk summary table, the two result
charts, and the full per-well details table — mirroring the legacy
Excel output.

Page layout (fixed, via explicit ``PageBreak``s):

- Page 1 — input parameters, summary cards, method and assumptions.
- Page 2 — the distance-drawdown and impact-% charts.
- Page 3+ — the at-risk wells table (as many pages as it needs).
- A fresh page onward — the full per-well details table.

The chart images are *not* rendered here. Plotly figures are captured
in the browser (a clientside callback calls ``Plotly.toImage``) and the
resulting PNG bytes are handed to `build_pdf`. This keeps the heavy
headless-browser dependency (``kaleido``) out of the install and
guarantees the PDF charts match exactly what the officer saw on screen.

The module is otherwise pure: given an `AnalysisResult` plus the two
PNG byte strings it returns the PDF as ``bytes``. No Dash imports.
"""

from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from gwdrawdown.analysis import AnalysisResult, WellResult
from gwdrawdown.core.flagging import WellStatus
from gwdrawdown.ui.components.palette import STATUS_PALETTE

_PAGE_SIZE = landscape(letter)
_MARGIN = 0.4 * inch
# Usable content width between the left and right margins.
_CONTENT_WIDTH = _PAGE_SIZE[0] - 2 * _MARGIN

_BANNER_COLOUR = colors.HexColor("#b00020")
_HEADING_COLOUR = colors.HexColor("#0d47a1")
_GRID_COLOUR = colors.HexColor("#bbbbbb")
_HEADER_BG = colors.HexColor("#fafafa")
# Light-purple row tint for the Cooper-Jacob outside-validity advisory,
# matching `results_table._OUTSIDE_VALIDITY_ROW_BG`.
_OUTSIDE_VALIDITY_BG = colors.HexColor("#f3e5f5")

# Summary-card accent colours — the shared status-palette foreground
# plus two local hues, matching `ui/components/stat_cards.py`.
_SUMMARY_ACCENTS: dict[str, str] = {
    "neutral": "#003366",
    "at_risk": STATUS_PALETTE[WellStatus.AT_RISK][1],
    "ok": STATUS_PALETTE[WellStatus.OK][1],
    "insufficient": STATUS_PALETTE[WellStatus.INSUFFICIENT_DATA][1],
    "suspect": STATUS_PALETTE[WellStatus.SUSPECT_DATA][1],
    "outside": STATUS_PALETTE[WellStatus.OUTSIDE_VALIDITY][1],
    "drawdown": "#1565c0",
}

_EDITABLE_FIELD_LABELS: dict[str, str] = {
    "static_water_level_m": "NPL",
    "finished_well_depth_m": "Finished Depth",
    "stickup_m": "Stickup",
    "top_of_fracture_or_aquifer_or_screen_m": "Top of Frac/Screen",
}

# (compact header, WellResult attribute or derived key, decimals).
# decimals=None -> the value is text, rendered as-is.
_PER_WELL_COLUMNS: list[tuple[str, str, int | None]] = [
    ("WTN", "well_tag_number", 0),
    ("Use", "intended_water_use", None),
    ("Aq ID", "aquifer_id", 0),
    ("Fin.D", "finished_well_depth_m", 2),
    ("Tot.D", "total_depth_drilled_m", 2),
    ("Bdrk.D", "bedrock_depth_m", 2),
    ("Yield", "yield_m3_per_day", 2),
    ("NPL", "static_water_level_m", 2),
    ("Stick", "stickup_m", 2),
    ("GW Mat.", "aquifer_material_gwells", None),
    ("Reass. Mat.", "reassigned_material", None),
    ("Dist", "distance_m", 1),
    ("Drawdn", "drawdown_m", 4),
    ("Top Frac", "top_of_fracture_or_aquifer_or_screen_m", 2),
    ("SAD", "sad_m", 3),
    ("Imp %", "impact_pct", 1),
    ("Status", "well_status", None),
    ("Edited", "edited", None),
]
# Relative column weights — scaled to the content width so the table
# always fills the frame. The Status column is widened enough to clear
# the longest value ("INSUFFICIENT_DATA").
_PER_WELL_WEIGHTS = [
    34, 62, 30, 35, 35, 37, 42, 31, 31, 52, 54, 37, 44, 39, 33, 31, 68, 48,
]

_AT_RISK_COLUMNS: list[tuple[str, str, int | None]] = [
    ("WTN", "well_tag_number", 0),
    ("Reassigned Material", "reassigned_material", None),
    ("SAD (m)", "sad_m", 3),
    ("Impact (m)", "drawdown_m", 4),
    ("Impact %", "impact_pct", 1),
]
_AT_RISK_WEIGHTS = [60, 200, 90, 90, 80]


def _fmt(value: object, decimals: int | None) -> str:
    """Render a cell value: '' for None, fixed decimals for numbers."""
    if value is None:
        return ""
    if decimals is None:
        return str(value)
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


def _scaled_widths(weights: list[float], target: float) -> list[float]:
    """Scale relative column weights so they sum to ``target`` points."""
    total = sum(weights)
    return [w / total * target for w in weights]


def _well_cell(w: WellResult, key: str, edited: str) -> object:
    """Pull a per-well table cell value by column key."""
    if key == "impact_pct":
        return w.impact_fraction * 100 if w.impact_fraction is not None else None
    if key == "well_status":
        return w.well_status.value
    if key == "edited":
        return edited
    return getattr(w, key, None)


def _make_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "gwTitle",
            parent=base["Title"],
            fontSize=16,
            textColor=_HEADING_COLOUR,
            spaceAfter=4,
        ),
        "heading": ParagraphStyle(
            "gwHeading",
            parent=base["Heading2"],
            fontSize=11,
            textColor=_HEADING_COLOUR,
            spaceBefore=12,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "gwBody", parent=base["BodyText"], fontSize=8, leading=11
        ),
        "disclaimer": ParagraphStyle(
            "gwDisclaimer",
            parent=base["BodyText"],
            fontSize=7.5,
            leading=10,
            spaceAfter=6,
            textColor=colors.HexColor("#444444"),
        ),
        "legend": ParagraphStyle(
            "gwLegend",
            parent=base["BodyText"],
            fontSize=7,
            leading=9,
            spaceBefore=4,
            textColor=colors.HexColor("#555555"),
        ),
        "cardLabel": ParagraphStyle(
            "gwCardLabel",
            parent=base["BodyText"],
            fontSize=6,
            leading=8,
            textColor=colors.HexColor("#606060"),
        ),
        "cell": ParagraphStyle(
            "gwCell", parent=base["BodyText"], fontSize=5.5, leading=7
        ),
        "cellHeader": ParagraphStyle(
            "gwCellHeader",
            parent=base["BodyText"],
            fontSize=5.5,
            leading=7,
            fontName="Helvetica-Bold",
        ),
    }
    return styles


def _input_parameters_table(result: AnalysisResult, styles: dict) -> Table:
    """Two-column label/value table summarising the run inputs.

    Well counts deliberately do *not* appear here — they get their own
    summary-card row (`_summary_cards`).
    """
    inputs = result.inputs
    ts_tag = " (override)" if inputs.ts_overridden else ""
    if inputs.is_manual_mode:
        source = f"Manual entry ({inputs.manual_material}) — no mapped aquifer"
        filter_txt = "n/a (manual entry)"
    else:
        source = (
            f"{inputs.source_aquifer_name} (id {inputs.source_aquifer_id}, "
            f"subtype {inputs.source_subtype_code or '—'})"
        )
        filter_txt = "ON" if inputs.same_aquifer_filter else "off"

    rows = [
        ("Run timestamp", result.run_timestamp.strftime("%Y-%m-%d %H:%M:%S")),
        (
            "Pumping point",
            f"lon {inputs.pumping_lon:.6f}, lat {inputs.pumping_lat:.6f} "
            f"(BC Albers {inputs.pumping_x_albers:.1f}, "
            f"{inputs.pumping_y_albers:.1f})",
        ),
        ("Source aquifer", source),
        (
            "Transmissivity / Storativity",
            f"T = {inputs.transmissivity_m2_per_day:g} m²/day, "
            f"S = {inputs.storativity:g}{ts_tag}",
        ),
        (
            "Pumping rate",
            f"{inputs.Q_value:g} {inputs.Q_unit} = "
            f"{inputs.Q_m3_per_day:.3f} m³/day",
        ),
        ("Pumping duration", f"{inputs.duration_days:g} days"),
        ("Buffer radius", f"{inputs.buffer_radius_m:g} m"),
        ("Source-aquifer filter (spatial)", filter_txt),
    ]
    data = [
        [
            Paragraph(f"<b>{label}</b>", styles["body"]),
            Paragraph(value, styles["body"]),
        ]
        for label, value in rows
    ]
    table = Table(data, colWidths=[2.2 * inch, _CONTENT_WIDTH - 2.2 * inch])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, _GRID_COLOUR),
                ("BACKGROUND", (0, 0), (0, -1), _HEADER_BG),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


# Summary-card geometry. The card height is fixed so every card — and
# its colour bar — is the same length regardless of how many lines its
# label wraps to. The bar is a background-filled cell (not a drawn
# line), so it spans exactly the card height with no line-cap overflow.
_CARD_HEIGHT = 58
_CARD_BAR_WIDTH = 6
_CARD_GAP = 6


def _card(
    label: str,
    value: str,
    accent: colors.Color,
    styles: dict,
    *,
    width: float,
) -> Table:
    """One summary card: a full-height colour bar + label + value."""
    value_style = ParagraphStyle(
        f"gwCardValue-{label}",
        parent=styles["body"],
        fontSize=15,
        leading=18,
        fontName="Helvetica-Bold",
        textColor=accent,
    )
    content = [
        Paragraph(label.upper(), styles["cardLabel"]),
        Spacer(1, 3),
        Paragraph(value, value_style),
    ]
    card = Table(
        [["", content]],
        colWidths=[_CARD_BAR_WIDTH, width - _CARD_BAR_WIDTH],
        rowHeights=[_CARD_HEIGHT],
    )
    card.setStyle(
        TableStyle(
            [
                # Colour bar — a filled cell, so it spans exactly the
                # card height. No line-cap overflow at the corners.
                ("BACKGROUND", (0, 0), (0, 0), accent),
                ("BACKGROUND", (1, 0), (1, 0), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.5, _GRID_COLOUR),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 0),
                ("TOPPADDING", (0, 0), (0, 0), 0),
                ("BOTTOMPADDING", (0, 0), (0, 0), 0),
                ("LEFTPADDING", (1, 0), (1, 0), 7),
                ("RIGHTPADDING", (1, 0), (1, 0), 6),
                ("TOPPADDING", (1, 0), (1, 0), 6),
                ("BOTTOMPADDING", (1, 0), (1, 0), 6),
            ]
        )
    )
    return card


def _summary_cards(result: AnalysisResult, styles: dict) -> Table:
    """A row of count cards, mirroring the results-page stat cards.

    Each card is its own bordered mini-table with a full-height
    coloured left bar; the cards are spaced apart by thin gap columns
    on the outer table. The "Outside validity" count uses the same
    advisory rule as the on-screen card — wells whose ``u_max`` reaches
    ``inputs.u_threshold`` — not ``result.n_outside_validity`` (which
    the pipeline no longer emits).
    """
    u_threshold = result.inputs.u_threshold
    advisory = sum(1 for w in result.wells if w.u_max >= u_threshold)
    max_dd = (
        f"{result.max_drawdown_m:.3f} m"
        if result.max_drawdown_m is not None
        else "—"
    )
    cards = [
        ("Total wells", str(result.n_total), "neutral"),
        ("At risk", str(result.n_at_risk), "at_risk"),
        ("OK", str(result.n_ok), "ok"),
        ("Insufficient data", str(result.n_insufficient_data), "insufficient"),
        ("Suspect data", str(result.n_suspect_data), "suspect"),
        ("Outside validity", str(advisory), "outside"),
        ("Max drawdown", max_dd, "drawdown"),
    ]
    n = len(cards)
    card_w = (_CONTENT_WIDTH - (n - 1) * _CARD_GAP) / n
    built = [
        _card(
            label,
            value,
            colors.HexColor(_SUMMARY_ACCENTS[key]),
            styles,
            width=card_w,
        )
        for label, value, key in cards
    ]
    # Interleave thin empty gap columns so the cards sit apart.
    cells: list[object] = []
    col_widths: list[float] = []
    for i, card in enumerate(built):
        cells.append(card)
        col_widths.append(card_w)
        if i < n - 1:
            cells.append("")
            col_widths.append(_CARD_GAP)
    outer = Table([cells], colWidths=col_widths)
    outer.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return outer


def _result_table(
    column_spec: list[tuple[str, str, int | None]],
    weights: list[float],
    wells: list[WellResult],
    edited_by_wtn: dict[int, str],
    styles: dict,
    *,
    header_para: bool,
    u_threshold: float | None = None,
) -> Table:
    """Build a reportlab Table from a column spec and a list of wells.

    Status cells get the shared status-palette background so the PDF
    reads consistently with the on-screen results table. When
    ``u_threshold`` is supplied, rows whose well fails the Cooper-Jacob
    validity check (``u_max >= u_threshold``) get a light-purple tint —
    the same advisory the per-well table shows on screen. The status
    cell keeps its own colour on top of the row tint.
    """
    headers = [
        Paragraph(h, styles["cellHeader"]) if header_para else h
        for h, _, _ in column_spec
    ]
    data: list[list[object]] = [headers]
    status_col = next(
        (i for i, (_, key, _) in enumerate(column_spec) if key == "well_status"),
        None,
    )
    style_cmds: list[tuple] = [
        ("GRID", (0, 0), (-1, -1), 0.4, _GRID_COLOUR),
        ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("FONTSIZE", (0, 0), (-1, -1), 5.5),
    ]
    for row_idx, w in enumerate(wells, start=1):
        edited = edited_by_wtn.get(w.well_tag_number, "")
        row: list[object] = []
        for _, key, decimals in column_spec:
            text = _fmt(_well_cell(w, key, edited), decimals)
            # Wrap free-text columns so long values don't overflow.
            if decimals is None and key != "well_status":
                row.append(Paragraph(text, styles["cell"]))
            else:
                row.append(text)
        data.append(row)
        # Purple outside-validity row tint (advisory). Applied before
        # the status-cell colour so the status cell still wins on its
        # own column.
        if u_threshold is not None and w.u_max >= u_threshold:
            style_cmds.append(
                (
                    "BACKGROUND",
                    (0, row_idx),
                    (-1, row_idx),
                    _OUTSIDE_VALIDITY_BG,
                )
            )
        if status_col is not None:
            bg, _fg = STATUS_PALETTE[w.well_status]
            style_cmds.append(
                (
                    "BACKGROUND",
                    (status_col, row_idx),
                    (status_col, row_idx),
                    colors.HexColor(bg),
                )
            )
    table = Table(
        data,
        colWidths=_scaled_widths(weights, _CONTENT_WIDTH),
        repeatRows=1,
    )
    table.setStyle(TableStyle(style_cmds))
    return table


def _chart_flowable(
    png: bytes | None,
    styles: dict,
    label: str,
    *,
    max_w: float,
    max_h: float,
) -> object:
    """A chart Image box-fitted into ``(max_w, max_h)``, or a fallback note.

    The image is scaled to fit *entirely* within the box, preserving
    aspect — so a tall impact chart (its on-screen height grows with
    the well count) stays whole on a single page rather than
    overflowing or being clipped.
    """
    if not png:
        return Paragraph(
            f"<i>{label} chart unavailable — re-run the export with the "
            f"results page fully loaded.</i>",
            styles["disclaimer"],
        )
    reader = ImageReader(io.BytesIO(png))
    src_w, src_h = reader.getSize()
    ratio = min(max_w / src_w, max_h / src_h)
    return Image(io.BytesIO(png), width=src_w * ratio, height=src_h * ratio)


def _page_decorations(result: AnalysisResult, user: str, version: str):
    """Return an onPage callback that draws the banner and footer."""
    ts = result.run_timestamp.strftime("%Y-%m-%d %H:%M")

    def _draw(canvas, doc) -> None:
        width, height = _PAGE_SIZE
        canvas.saveState()
        # Top screening banner — on every page per PROJECT_PLAN.md §5.
        canvas.setFillColor(_BANNER_COLOUR)
        canvas.rect(0, height - 24, width, 24, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawCentredString(
            width / 2,
            height - 16,
            "SCREENING TOOL — results are advisory and must be reviewed "
            "by the regional hydrogeologist.",
        )
        # Bottom footer — run identity + pagination.
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.setFont("Helvetica", 7)
        canvas.drawString(
            _MARGIN,
            16,
            f"Run {result.run_id}  ·  {ts}  ·  v{version}  ·  "
            f"{user}  ·  Page {doc.page}",
        )
        canvas.restoreState()

    return _draw


def _method_text(u_threshold: float) -> list[str]:
    """Cooper-Jacob method + assumptions, as separate paragraphs.

    The "Method and assumptions" wording is the section *heading* —
    it is deliberately not repeated as a lead-in here. The validity
    threshold actually in force (``inputs.u_threshold``) is quoted so
    the reader sees the real number rather than a generic statement.
    """
    return [
        "Drawdown is estimated using the Cooper-Jacob (1946) "
        "distance-drawdown approximation to the Theis solution. This "
        "method assumes a homogeneous, isotropic, infinite confined "
        "aquifer of uniform thickness, a fully penetrating well, a "
        "constant pumping rate, and no recharge over the pumping "
        "period.",
        "The approximation is strictly valid only for small values "
        "of u = r²S / (4Tt). This validity check is advisory only and "
        "is not enforced: a well that does not meet the criterion — "
        f"u reaching the configured threshold of {u_threshold:g} — "
        "will still be assigned a drawdown value and retain its "
        "SAD-based status, but it will be flagged in the results "
        "table. Drawdown results for such wells should be interpreted "
        "with caution at that distance and duration.",
        "SAD is calculated using the unconfined aquifer formula; for "
        "confined and fractured-bedrock wells, this may overestimate "
        "SAD, so the driller's log should be reviewed.",
        "These are screening-level estimates and are not a substitute "
        "for assessment by the regional hydrogeologist.",
    ]

_PER_WELL_LEGEND = (
    "<b>Row tint.</b> Light purple = outside Cooper-Jacob validity "
    "(advisory): the well's u = r²S/(4Tt) reaches the configured "
    "threshold, so the drawdown number is shown but should be treated "
    "with caution at that distance / duration. The Status cell keeps "
    "its own colour. The &quot;Edited&quot; column lists any per-well "
    "fields adjusted by the reviewer."
)


def build_pdf(
    result: AnalysisResult,
    *,
    user: str,
    version: str,
    overrides_by_wtn: dict[int, dict[str, float | None]] | None = None,
    dd_chart_png: bytes | None = None,
    impact_chart_png: bytes | None = None,
) -> bytes:
    """Render a full analysis run to a PDF document.

    Args:
        result: The analysis result, with per-well overrides already
            applied by `analysis.apply_overrides`.
        user: Signed-in BCGW username, shown in the page footer.
        version: Tool version string, shown in the page footer.
        overrides_by_wtn: Raw per-WTN override map, used only to fill
            each well's "Edited" column. ``None`` means no overrides.
        dd_chart_png: PNG bytes of the distance-drawdown chart captured
            in the browser, or ``None`` if capture failed.
        impact_chart_png: PNG bytes of the impact-% chart, or ``None``.

    Returns:
        The PDF document as ``bytes``.
    """
    overrides_by_wtn = overrides_by_wtn or {}
    styles = _make_styles()
    u_threshold = result.inputs.u_threshold
    edited_by_wtn = {
        wtn: ", ".join(
            label
            for field_name, label in _EDITABLE_FIELD_LABELS.items()
            if field_name in cells
        )
        for wtn, cells in overrides_by_wtn.items()
    }

    # --- Page 1: parameters, summary, method ---------------------------
    story: list[object] = [
        Paragraph("Groundwater Drawdown Screening Report", styles["title"]),
        Spacer(1, 6),
        Paragraph("Input parameters", styles["heading"]),
        _input_parameters_table(result, styles),
        Paragraph("Summary", styles["heading"]),
        _summary_cards(result, styles),
        Paragraph("Method and assumptions", styles["heading"]),
        *[
            Paragraph(para, styles["disclaimer"])
            for para in _method_text(u_threshold)
        ],
        PageBreak(),
    ]

    # --- Pages 2 & 3: one chart per page -------------------------------
    # Each chart gets its own page — the impact chart in particular can
    # be tall, since its on-screen height scales with the well count.
    chart_max_h = 6.7 * inch
    story += [
        Paragraph("Distance-drawdown", styles["heading"]),
        _chart_flowable(
            dd_chart_png,
            styles,
            "Distance-drawdown",
            max_w=_CONTENT_WIDTH,
            max_h=chart_max_h,
        ),
        PageBreak(),
        Paragraph("Impact % per well", styles["heading"]),
        _chart_flowable(
            impact_chart_png,
            styles,
            "Impact %",
            max_w=_CONTENT_WIDTH,
            max_h=chart_max_h,
        ),
        PageBreak(),
    ]

    # --- Page 3+: at-risk wells table ----------------------------------
    story.append(
        Paragraph(f"At-risk wells ({result.n_at_risk})", styles["heading"])
    )
    at_risk = sorted(
        (w for w in result.wells if w.well_status == WellStatus.AT_RISK),
        key=lambda w: -(w.impact_fraction or 0),
    )
    if at_risk:
        story.append(
            _result_table(
                _AT_RISK_COLUMNS,
                _AT_RISK_WEIGHTS,
                at_risk,
                edited_by_wtn,
                styles,
                header_para=False,
            )
        )
    else:
        story.append(
            Paragraph(
                "No wells flagged at-risk at the configured threshold.",
                styles["body"],
            )
        )
    story.append(PageBreak())

    # --- Fresh page onward: full per-well details table ----------------
    story.append(
        Paragraph(f"All wells in buffer ({result.n_total})", styles["heading"])
    )
    wells_sorted = sorted(result.wells, key=lambda w: w.distance_m)
    if wells_sorted:
        story.append(
            _result_table(
                _PER_WELL_COLUMNS,
                _PER_WELL_WEIGHTS,
                wells_sorted,
                edited_by_wtn,
                styles,
                header_para=True,
                u_threshold=u_threshold,
            )
        )
        story.append(Paragraph(_PER_WELL_LEGEND, styles["legend"]))
    else:
        story.append(
            Paragraph("No wells returned by the buffer query.", styles["body"])
        )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=_PAGE_SIZE,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        # Top margin clears the 24-pt banner; bottom clears the footer.
        topMargin=0.55 * inch,
        bottomMargin=0.45 * inch,
        title="Groundwater Drawdown Screening Report",
    )
    decorate = _page_decorations(result, user, version)
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()
