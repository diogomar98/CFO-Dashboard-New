# Independent 4-eyes results — Group NII and NIM (2021 Q1–2026 Q2)

**Run:** https://github.com/diogomar98/CFO-Dashboard-New/actions/runs/39640848529
**Download full exact-cell audit and candidate source series:** https://github.com/diogomar98/CFO-Dashboard-New/actions/runs/39640848529/artifacts/12365272432

**Result: PASS on the specifically defined fields below.** This is not a blanket sign-off for the bank's entire historical factsheets or a claim of independently calibrated forecast intervals.

- **22 distinct Group reporting quarters** (Q1 2021–Q2 2026) extracted from the official, publicly hosted factsheets.
- **21 successor-quarter comparisons × 2 metrics = 42**: the earlier factsheet's latest Q value was checked against the next factsheet's previous Q value.
- **5 published-value checks** against independently issued ABN press disclosures (Q1 2022, Q4 2022, Q1 2023, and Q2 2026 NII and NIM where available).
- **2 separate-version checks** for Group 2021 Q4 NII and NIM, original versus new reporting structure.
- **49/49 checks passed**, zero exceptions. Exact URLs, quarter, tab, cell, observed value, independent value and difference in `independent_cross_checks.csv`.

| Quarter | Group NII exact from factsheet (€m) | NIM exact from factsheet (bps) | Evidence |
| --- | ---: | ---: | --- |
| 2021 Q1 | 1,362.917 | 134.465 | Official Q1 2021 workbook; compared to Q2 2021 preceding-column values |
| 2021 Q4 | 1,338.974 | 128.467 | Original AND new-structure Q4 2021 workbooks; same values in Q1 2022 predecessor column |
| 2022 Q1 | 1,309.995 | 125.526 | Q1 2022 factsheet + official press release NII €1,310m |
| 2022 Q4 | 1,563.608 | 150.263 | Q4 2022 factsheet + official press release NII €1,564m |
| 2023 Q1 | 1,620.281 | 162.527 | Q1 2023 factsheet + official press release NII €1,620m |
| 2026 Q2 | 1,699.854 | 148.750 | Q2 2026 factsheet; ~€1,700m and 149bps when rounded |

**Workbook cell mapping**: latest-quarter consolidated Group `Net interest income` in sheet `1.1 Quart. P&L develop.`, cell `C7`, and latest consolidated Group `NIM (in bps)` in the same sheet, usually `C24` or `C25` depending on year; previous-quarter values in the matching next-release sheet's column `D`. **Do not blindly use fixed row coordinates across all years**; extraction uses unique exact Group line labels.

**Boundary:** The 2021Q4 legacy segment labels are Retail Banking / Commercial Banking / Private Banking / CIB; the new-structure version presents PBB / WM / Corporate Banking and Group Functions. This independently supports the decision to **restrict the 2021 Group forecast training data to NII and NIM until the other series are mapped and reconciled**.

**Methodology constraints:** A source-accurate history is not evidence that a forecasting model achieves 99% prediction coverage. With 22 quarters (21 adjacent comparisons), the 99th-percentile tails are not empirically estimable or verifiable with precision; independent macro covariates and fitted model diagnostics are separate next gates. No 99% confidence claim or interval has been added to the working app.

**Source and methods:** `research/reconcile_2021_nii_nim.py` (deterministic extraction and independent comparisons). The official archive and all 45 raw-file checksums are in the earlier `abn-public-factsheets-source-evidence` action artifact. These source files are publicly available, but no private ABN data have been used.
