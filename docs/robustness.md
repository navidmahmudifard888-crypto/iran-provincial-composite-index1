# Robustness

All robustness outputs test dependence on modeling assumptions. They are not real-world probability statements.

## Scenario sensitivity

- Equal weight: mean absolute rank change **2.39**, max **7**
- Educational emphasis: mean **4.45**, max **15**
- Social emphasis: mean **4.58**, max **20**
- Economic emphasis: mean **4.32**, max **14**
- Security emphasis: mean **5.23**, max **17**
- Infrastructure emphasis: mean **4.32**, max **11**

## Monte Carlo

- Global weighting: mean score SD **12.63**; mean P95–P05 rank width **21.42**
- Local baseline neighborhood: mean score SD **1.77**; mean P95–P05 rank width **5.74**

## Leave-One-Out

Indicator LOO: median per-indicator maximum rank impact **2.0**; largest observed impact **15**.

Domain LOO:

| Domain removed | Mean absolute rank change | Max rank change |
|---|---:|---:|
| Economic | 6.06 | 21 |
| Social | 3.94 | 14 |
| Educational | 3.42 | 13 |
| Security | 1.10 | 3 |
| Infrastructure | 0.77 | 3 |

## Temporal and normalization sensitivity

- Temporal rank Spearman range: **0.994–1.000**
- Maximum mean absolute rank change across temporal tests: **0.71**
- Maximum absolute temporal rank change: **3**
- Normalization rank Spearman range: **0.957–1.000**

Interpretation: temporal specifications are highly stable in the tested range, while some domain-weight assumptions materially affect rankings. The baseline should therefore be presented together with the sensitivity results.
