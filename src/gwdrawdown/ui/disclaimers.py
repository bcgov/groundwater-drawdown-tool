"""Canonical disclaimer strings, defined once so wording can't drift.

Two distinct disclaimers, with deliberately different reach:

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
