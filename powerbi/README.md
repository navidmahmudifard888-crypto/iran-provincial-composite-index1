# Power BI Handoff

This repository does not include a fabricated `.pbix` file. The intended architecture is:

```text
Python scoring engine
        ↓
final CSV outputs
        ↓
Power BI semantic model
        ↓
interactive dashboard
```

## Recommended report pages

1. **Executive Overview** — ranking, distribution, KPI cards.
2. **Province Explorer** — selected province, five-domain profile and rank.
3. **Domain Analysis** — province × domain heatmap / comparison.
4. **Robustness** — scenarios, Monte Carlo intervals and LOO diagnostics.
5. **Data Quality & Methodology** — missingness, freshness, provenance and methodology notes.
6. **Explainability** — Province → Category → Subindicator → Series contribution drill-down.

Power BI must consume the frozen Python outputs as the source of truth; it should not implement a second scoring formula.
