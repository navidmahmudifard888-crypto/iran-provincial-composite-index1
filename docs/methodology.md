# Methodology

## 1. Objective and unit of analysis

The model produces a multidimensional provincial composite index for comparative analysis across Iran's 31 provinces. The atomic observation is `province × series × year`.

The index is comparative and model-dependent. It does not establish causality or an absolute provincial "risk" probability.

## 2. Data architecture

The final run contains 4,893 raw rows before exact duplicate removal, 151 registry series, 31 provinces, five analytical domains and 22 active subindicator groups. After exact deduplication, 4,864 rows remain in the modeling layer.

## 3. Multi-year temporal design

Reference anchor: **1403**. The anchor determines recency; it is not a cutoff. Historical years remain eligible when supported by the data.

Baseline temporal weight:

`w(age) = max(0.25, 1 - 0.12 × age)`

For each logical series, yearly normalized observations are aggregated to one province-series score using recency weights.

## 4. Normalization

Baseline: Min-Max within each `series_id × year` across provinces. This measures relative provincial standing within each year. Pooled normalization, Z-score and Robust alternatives are retained for sensitivity analysis.

## 5. Population standardization

Population normalization is selective rather than universal. School/class counts use same-year `Population6Plus` when available. Other selected counts use same-year total population when available, otherwise the nearest total-population observation within a maximum two-year gap. Rates, percentages, ratios, indexes and already-per-capita measures are not divided by population again.

## 6. Direction and unit treatment

The registry records `higher_worse`, `higher_better` and `unknown` direction states. Unknown direction excludes a series from the baseline. Unit inference distinguishes percent, ratio, rate, index, per-capita and count concepts before deciding whether a population transform is appropriate.

## 7. Duplicate and conflict handling

Exact duplicate rows are removed from the modeling layer only. The raw workbook is preserved. Geography-level conflict issues that previously came from sub-provincial Tehran records are not silently forced into the Tehran province key. Final unresolved province × series × year conflict keys: **0**.

## 8. Indicator selection

Final registry status:

- CORE: 0
- CONDITIONAL: 33
- EXCLUDED: 118

`CONDITIONAL` reflects incomplete row-level source provenance and methodological sign-off, not proof that the underlying data are invalid.

## 9. Weight hierarchy

The scoring hierarchy is:

`Series → Subindicator → Category → Overall`

Domain weights:

- Economic: 0.35
- Social: 0.30
- Educational: 0.20
- Security: 0.10
- Infrastructure: 0.05

Within categories, active subindicators and active series follow the registry's explicit weight logic. Effective final weights sum to 1.0.

## 10. Missing data and quality

No baseline imputation is performed. Missingness is measured against the expected province-year grid. Province-level data quality uses coverage and temporal freshness diagnostics; provenance is reported separately.

## 11. Robustness

The final package includes domain-weight scenarios, global and local Monte Carlo simulations, indicator LOO, domain LOO, temporal sensitivity, normalization sensitivity, and redundancy audits.

## 12. Interpretation

The final score is a modeled comparative position under selected indicators, transformations, temporal weights and aggregation assumptions. Contributions are accounting quantities, not causal effects.
