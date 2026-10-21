# Four-eyes source inventory — public ABN Horizon research

**Research snapshot:** 21 October 2026. **Forecasting data cutoff:** 30 June 2026 until a new reported quarter is published. **No app/forecast values changed.**

## Reproducible raw-source evidence

- ABN official archive: https://www.abnamro.com/en/investor-relations/information/all-financial-reports
- GitHub Action source package: https://github.com/diogomar98/CFO-Dashboard-New/actions/runs/39638234274/artifacts/12365085159
- Workflow result: **45 original XLSX files**, representing **all 42 quarters from 2016 Q1 through 2026 Q2**, zero failed downloads, each valid as an OOXML/ZIP workbook.
- `source_manifest.csv` contains the reporting quarter, full official source URL, workbook label, whether it is an updated/restated alternative, hash SHA-256, size, tab count, validation status and review status.
- `original_workbooks/` holds copies of the unmodified public workbooks.
- Original official 2016-Q4 and updated-segmentation variant, 2018-Q1 and restated variant, 2021-Q4 and new-reporting-structure variant are both collected: **none is implicitly selected**.
- **Evidence status only:** A valid ZIP is not proof that every metric is economically comparable. We have NOT extracted or harmonized the 42-quarter model-input panel, backtested forecasts or approved restatements. This package is not yet wired into the Streamlit app.

## 4-eyes review register

| Information / candidate input | Exact public source | Primary URL | State | Review/normalization required |
| --- | --- | --- | --- | --- |
| Consolidated quarterly net interest income (NII), net profit, fee income, operating income and costs | ABN AMRO all quarterly Factsheet XLSX + each quarterly report, 2016 Q1–2026 Q2 | https://www.abnamro.com/en/investor-relations/information/all-financial-reports | 42 quarters of official raw factsheets downloaded and hash checked; **values not yet reconciled** | Distinguish Q4 standalone from FY YTD; compare same-definition consolidated Group figures in overlapping factsheets and reports |
| NIM (basis points) and cost/income ratio | Same archive; Q2 2026 quarterly report, "Financial review", printed page 5 | https://assets.ctfassets.net/1u811bvgvthc/XdAWhG6RCScxulxUI24zg/4437970f789fb52f232a0d7589427778/ABN_AMRO_Bank_Interim_Report___Quarterly_Report_second_quarter_2026.pdf | Published 2026 Q2 NIM **149 bps**; 2016–2026 workbook retrieval complete | Check numerator/denominator definition, calculation, ratio changes and historical restatements |
| Commercial NII vs reported statutory NII | Q2 2026 quarterly report, "Other information / Alternative performance measures", printed page 64 | https://assets.ctfassets.net/1u811bvgvthc/XdAWhG6RCScxulxUI24zg/4437970f789fb52f232a0d7589427778/ABN_AMRO_Bank_Interim_Report___Quarterly_Report_second_quarter_2026.pdf | **Validated disclosure:** Q2 statutory NII €1,700m; residual NII €12m; commercial NII €1,688m | Commercial guidance MUST NOT be used against statutory NII without scope reconciliation |
| Deposits, customer loans, RWA, CET1 and capital | ABN quarterly factsheets + Pillar 3 reports at same official archive | https://www.abnamro.com/en/investor-relations/information/all-financial-reports | Raw quarterly factsheets downloaded; published Pillar 3 documents indexed; numeric extraction pending | Quarter-end stock vs quarterly income distinction; regulatory definition and capital requirements, scope |
| Reported outlook, 2026 commercial NII and cost guidance | ABN Investor Relations Q2 2026 12 Aug 2026 official release | https://www.abnamro.com/en/news/abn-amro-posts-net-profit-of-eur-781-million-in-q2-2026 | **Verified:** full-year commercial NII guidance €6.8bn, cost guidance €5.5bn **including NIBC** | 1 Aug 2026 NIBC closing creates major historical comparability/boundary difference |
| Restated/alternative reports | Official archive: updated-segmentation factsheet 2016 Q4; restated factsheet 2018 Q1; 2021 Q4 new-reporting-structure factsheet | https://www.abnamro.com/en/investor-relations/information/all-financial-reports?selectedTab=2021 | **All original and alternative files downloaded** | Explicit 4-eyes choice on which historical version and how to restate intervening series |
| Historical report cross-check, 2021 Q4 | Quarterly Report fourth quarter 2021, printed page 7 | https://assets.ctfassets.net/1u811bvgvthc/3aF00xJGYcPJeXjYRsGngv/f15a62801c359fe8561d90d138daca67/ABN_AMRO_Bank_Quarterly_Report_4th_quarter_2021.pdf | **Validated disclosure:** Q4 2021 NII €1,339m and NIM 128bps | Older bank core vs consolidated reporting lines must not be mixed |
| ECB Deposit Facility Rate | ECB Data Portal, precise series `FM.B.U2.EUR.4F.KR.DFR.LEV` | https://data.ecb.europa.eu/data/datasets/FM/FM.B.U2.EUR.4F.KR.DFR.LEV | **Official series identified; history NOT downloaded into the evidence package yet** | Quarterly aggregation, time-of-publication cutoff; rate-change effective date |
| NL mortgage interest rate on new lending | ECB MFI Interest Rate Statistics `MIR.M.NL.B.A2C.A.R.A.2250.EUR.N` | https://data.ecb.europa.eu/data/datasets/MIR/MIR.M.NL.B.A2C.A.R.A.2250.EUR.N | **Official series identified; not downloaded** | Monthly to quarterly averaging; this is a national market proxy, not ABN's observed mortgage yield |
| NL mortgage rate on outstanding balances | ECB MIR `MIR.M.NL.B.A22.A.R.A.2250.EUR.O` | https://data.ecb.europa.eu/data/datasets/MIR/MIR.M.NL.B.A22.A.R.A.2250.EUR.O | **Official series identified; not downloaded** | Prefer for slow repricing proxy, not a substitute for ABN asset yield |
| NL real GDP growth | Eurostat `namq_10_gdp` quarterly | https://ec.europa.eu/eurostat/databrowser/product/view/namq_10_gdp | **Official dataset identified; not downloaded** | NL geo, volume growth, seasonal adjustment and public release vintage for backtests |
| NL headline inflation (HICP) | Eurostat successor dataset `prc_hicp_minr` (replaces retired `prc_hicp_midx`) | https://ec.europa.eu/eurostat/databrowser/product/view/prc_hicp_minr | **Official successor dataset identified; not downloaded** | Monthly to quarterly transformation and time-series rebasing; avoid mixing old/new HICP definitions |
| NL unemployment rate | Eurostat `une_rt_m` | https://ec.europa.eu/eurostat/databrowser/product/view/une_rt_m | **Official dataset identified; not downloaded** | Seasonally adjusted total unemployment, geo NL, monthly to quarterly and release/vintage control |

## Suggested modelling and interval acceptance criteria

1. Approve one uniform consolidated quarterly **definition** for NII/NIM, loans, deposits, group RWA and costs; record any pre/post 2016, 2018 or 2021 restatement regimes.
2. First establish historical **seasonal-naïve** and drift benchmarks. Prefer a parsimonious dynamic regression/ARX forecast for interest margins/income with a small number of documented exogenous drivers and explicit lags. Never use NII and NIM as independently adjustable forecasts after they can be reconciled using properly defined average earning assets.
3. Use rolling-origin, as-of-date forecasts for 1, 2, 3 and 4 quarters ahead, not random cross-validation; evaluate bias/MAE and interval calibration by horizon. Exclude unreleased historical revisions from old-origin training sets wherever data vintages permit.
4. Generate **prediction intervals** using simulated future innovations or calibrated residual/bootstrap forecast errors. Show alpha=10%, 5%, 1% as 90%, 95%, 99% interval coverage only if backtesting supports those labels.
5. Do NOT claim reliable 99% empirical coverage solely from 42 quarterly observations: 1% one-tail coverage implies far fewer than one independent tail observation. Use transparent stressed scenarios as a separate visual layer when extreme-risk calibration is not supported.
6. Always separate: published Group facts, management guidance (including acquisition effects), public macro proxies, modelling assumptions, and scenario/simulation outputs.

**No ABN-internal nonpublic data has been sourced, requested or included in this research evidence package.**
