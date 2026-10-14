# Decision Log

- Reference year set to **1403** as a recency anchor, not a cutoff.
- Historical observations retained at the logical-series level.
- Exact duplicates removed only from the modeling layer.
- Conflicting sub-provincial Tehran rows are not forced into the province key.
- Count-to-per-100,000 conversion is limited to substantively meaningful event/capacity series.
- School/class counts use same-year `Population6Plus` when available.
- Other selected counts use same-year total population, then the nearest total-population observation within a maximum two-year gap when required.
- Rates, percentages, ratios, indexes and already-per-capita measures receive no additional population division.
- Design weights are exposed explicitly and tested through sensitivity analysis.
- SHDI 2023 is used as a convergent external criterion, not a clean independent holdout.
