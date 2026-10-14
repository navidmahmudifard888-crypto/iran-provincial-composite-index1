# Data source and redistribution review

## Current status

The project owner independently collected individual indicators from multiple sources and consolidated them into a workbook. The Statistical Center of Iran is understood to be a primary source for much of the data, but the original source for every indicator is not currently documented. No blanket redistribution permission has been established for the full workbook.

**Status: SOURCE-LEVEL REVIEW REQUIRED.** This is not a legal determination that the data are restricted; it means the applicable terms have not been verified.

## Release safeguards applied

- Removed the original input workbook from this public-ready archive.
- Removed row-level standardized, transformed, and normalized observation tables from `data/processed/`.
- Retained code, documentation, registry, diagnostic/aggregated outputs, and portfolio figures.
- Did not assign a blanket license to third-party data.

## Review procedure

1. Identify the original source page or download record for each indicator.
2. Record source organization, exact URL/document title, period, retrieval date if known, attribution requirements, and applicable license/terms.
3. Verify whether redistribution of raw data, row-level transformed data, and derived/aggregated outputs is permitted; these are separate questions.
4. Where terms are absent or unclear, contact the source organization and retain the written response.
5. Remove or replace data that cannot be publicly redistributed. Do not invent missing source citations.

## Register template

Use `registry/data_source_register_template.csv` to document each source or dataset. Until verified, use `UNKNOWN / REVIEW REQUIRED` rather than assuming that publicly accessible means freely redistributable.

## Software license

No license for third-party data is implied. The project author's code license should be considered separately from source data rights. Do not add an open-source license that purports to cover data the author does not own or control.
