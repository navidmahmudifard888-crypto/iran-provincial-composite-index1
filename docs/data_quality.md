# Data Quality

## Final snapshot

- Raw rows before exact deduplication: **4,893**
- Raw rows after exact deduplication: **4,864**
- Exact duplicate rows removed: **29**
- Registry series: **151**
- Active series: **33**
- Active provenance: **33 PARTIALLY_VERIFIED**
- Unresolved provincial conflict keys in the final model: **0**
- Imputation policy: **none**
- Integrity tests: **6/6 PASS**

## What the checks cover

The pipeline checks expected province-year completeness, duplicates, conflicting keys, unit/rate/count interpretation, temporal coverage, and provenance status. Missingness is evaluated against the expected panel rather than only the surviving non-null records.

## Provenance limitation

The project workbook does not contain enough row-level source URLs or extraction records to independently verify the complete lineage of every active series. This is why all 33 active series remain `CONDITIONAL` / `PARTIALLY_VERIFIED`.
