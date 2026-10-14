# Architecture

The repository keeps one authoritative scoring path. The purpose of the surrounding files is to expose the transformations, diagnostics and presentation layers without creating competing score formulas.

```text
Raw workbook
    ↓
load_raw_input / standardization
    ↓
duplicate + conflict audit
    ↓
canonical registry
    ↓
direction + unit + transform rules
    ↓
population standardization (selected counts)
    ↓
within-year normalization
    ↓
recency weighting
    ↓
province × series score
    ↓
subindicator score
    ↓
category score
    ↓
composite score
    ↓
robustness + validation + QA
```

`src/hardening.py` is the authoritative pipeline implementation. `src/index_engine.py` contains shared parsing, normalization and core helper functions. `src/robustness_worker.py` isolates heavier sensitivity workloads.

Power BI, notebooks and visualization scripts consume final model outputs; they do not define a second scoring engine.
