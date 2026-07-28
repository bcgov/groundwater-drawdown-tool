"""Canonical disclaimer strings, defined once so wording can't drift.

Three groups, with deliberately different reach:

- ``INTERPRETATION_*`` — results are screening-level and must be
  interpreted by a qualified professional. Shown on the tool UI **and**
  on every exported artifact (PDF, KML, HTML map): whoever reads a
  result needs this caveat attached to it.
- ``INTERNAL_USE`` — the tool *itself* is internal-only and must not be
  shared outside the organization (client direction, 2026-06). Shown on
  the tool UI **only**, never on an exported artifact — a screening
  output may legitimately leave the org as part of a licence file, so
  stamping "do not share" on the report would be wrong. The restriction
  is on distributing the software, not the results.
- **Method guidance** (``METHOD_GUIDANCE`` and the individual constants
  behind it, plus ``at_risk_threshold_explanation``) — client-supplied
  wording about what the tool does and does not tell you. Shown on the
  tool UI and in the PDF; placed *contextually* rather than stacked in
  one block (see the note above the constants).

Plain strings only — no Dash/Flask imports — so the pure export modules
(``export_pdf`` is documented Dash-free) can import these too.
"""

from __future__ import annotations

# Full results-interpretation disclaimer (client wording, 2026-06). Used
# where a complete sentence fits: the PDF body disclaimer and the KML
# document description.
INTERPRETATION_FULL = (
    "All interpretation of results must be carried out by, or in "
    "consultation with, a regional hydrogeologist or a Qualified "
    "Professional with expertise in hydrogeology."
)

# Tightened interpretation line for the space-constrained banners (PDF
# per-page banner, HTML-map banner) and the on-screen footer.
INTERPRETATION_BANNER = (
    "Screening tool — results must be interpreted by, or in consultation "
    "with, a regional hydrogeologist or Qualified Professional."
)

# Tool-only. Never rendered on an exported artifact.
INTERNAL_USE = (
    "This tool is for internal use only and must not be shared outside "
    "the organization."
)

# --- Method / limitation guidance (client wording, 2026-07) -----------------
#
# Supplied verbatim by the client after the end-user testing round. Kept
# as separate constants rather than one blob because they are deliberately
# placed apart: each sits next to the thing it is about, so it is read at
# the moment it is relevant. Five paragraphs stacked in one panel is a
# wall of text nobody reads.
#
# Placement (see also the results page and export_pdf):
#   ANALYTICAL_SOLUTION  -> "Method, assumptions and limitations" panel
#   AQUIFER_DEFAULTS     -> setup page, under the T/S inputs
#   SENSITIVITY_ANALYSIS -> the same panel, after ANALYTICAL_SOLUTION
#   VERIFY_SOURCES       -> per-well details table helper text
#   CONTACT_HYDROGEOLOGIST -> the same panel, last
# All five also appear together in the PDF "Method and assumptions"
# section, which is the artifact that lands on the licence file, and in
# docs/user-guide/methods-and-assumptions.md as the canonical statement.

ANALYTICAL_SOLUTION = (
    "This tool estimates the predicted cone of depression resulting from "
    "pumping a well. It uses an analytical solution to provide a "
    "simplified representation of a complex natural system and may not be "
    "applicable in all situations. The results should not be relied upon "
    "as the sole basis for decision-making and do not replace the advice "
    "of a Qualified Professional or Regional Hydrogeologist."
)

AQUIFER_DEFAULTS = (
    "Default aquifer parameter values for British Columbia are based on a "
    "limited dataset. Best practice is to evaluate a range of values and "
    "conduct a sensitivity analysis of the storage coefficient (S) and "
    "transmissivity (T) input parameters."
)

SENSITIVITY_ANALYSIS = (
    "This tool utilizes a single analytical approach (Cooper-Jacob "
    "Method). Given the inherent uncertainties associated with aquifer "
    "properties, users are encouraged to conduct sensitivity analyses by "
    "running multiple simulations using a range of plausible aquifer "
    "parameter values to better understand the influence of those "
    "uncertainties on predicted drawdown."
)

VERIFY_SOURCES = (
    "Users are encouraged to verify information wherever possible, "
    "including reviewing scanned driller's logs and other supporting "
    "documentation available through the associated GWELLS records."
)

CONTACT_HYDROGEOLOGIST = (
    "If you have questions regarding the use of this tool or the "
    "interpretation of its results, please contact a Regional "
    "Hydrogeologist or Qualified Professional."
)

# Every guidance paragraph, in reading order. Used by the PDF and the
# results-page panel so a new paragraph is added in exactly one place.
METHOD_GUIDANCE: tuple[str, ...] = (
    ANALYTICAL_SOLUTION,
    AQUIFER_DEFAULTS,
    SENSITIVITY_ANALYSIS,
    VERIFY_SOURCES,
    CONTACT_HYDROGEOLOGIST,
)


def at_risk_threshold_explanation(fraction: float) -> str:
    """Explain what the at-risk threshold means, in the client's words.

    Takes the fraction from ``AnalysisInputs.at_risk_fraction`` rather
    than hardcoding 30 % so the text tracks
    ``config.AT_RISK_DRAWDOWN_FRACTION`` if it is ever retuned.
    """
    pct = f"{fraction * 100:g}"
    return (
        f"The {pct}% threshold indicates that the anticipated drawdown "
        f"impact is equal to {pct}% of the calculated Safe Available "
        "Drawdown. This threshold serves as a general screening guideline "
        "to help identify wells that may experience a substantial impact "
        "from the proposed groundwater diversion. Further interpretation "
        "and evaluation should be undertaken by, or in consultation with, "
        "a Regional Hydrogeologist or Qualified Professional."
    )
