---
title: Exporting results
parent: User Guide
nav_order: 6
---

# Exporting results

The results page has an **export bar** with buttons for each format.
Every export reflects the current state of the run, including any
per-well edits you have made in the details table.

Exported files are written to the `outputs\` folder inside the install
directory and are also offered as a browser download.

## CSV

Each table on the results page has its own **Export CSV** button. The CSV
reflects the table's current sort and filter state. The per-well CSV
includes a derived "Outside Validity" Yes/No column, so the validity
advisory (shown on screen as a purple row tint) survives the export.

Use CSV when you want the raw numbers in a spreadsheet.

## KML

A KML file for **Google Earth**. It contains one placemark for the
pumping well plus one for each observation well, colour-coded by status
and sized by predicted impact. The full per-well result row travels with
each placemark as attached data.

Use KML when you want to view the results geographically in Google Earth.

## PDF

A landscape PDF report, one section per page: input parameters and a
summary-card row with the method-and-assumptions disclaimer; the
distance-drawdown and impact charts; the at-risk summary table; and the
full per-well details table. Every page carries a screening-tool banner,
and the footer records the run timestamp, run ID, tool version, and
signed-in user.

Use the PDF as the artifact to attach to a licence assessment file.

## Interactive HTML map

A single self-contained HTML file with an interactive map — the pumping
well, the search buffer, and every observation well with clickable
popups. It opens in any browser with no software to install and stays
interactive (pan, zoom, switch basemap).

Use the HTML map to share results with someone who does not have the
tool installed.

## Which format to use

| You want to… | Use |
|---|---|
| Work with the numbers in a spreadsheet | CSV |
| View results in Google Earth | KML |
| Attach a report to an assessment file | PDF |
| Share an interactive view with a colleague | HTML map |
