# ABN AMRO quarterly reporting mode

This branch changes the Streamlit entry point to show **reported ABN AMRO quarterly financial data** instead of synthetic daily-bank dashboards. The original modules remain in the repository for later migration, but are not shown in this mode.

## Source and coverage

Only the uploaded **ABN_AMRO_Q2_2026_-_Factsheet.xlsx**, including its worksheets, supplied the financial metrics in:
- `data/abn_quarterly.csv`: Q1 2024–Q2 2026 P&L (10 quarters); Q4 2024–Q2 2026 balance-sheet / capital / liquidity (7 quarter ends).
- `data/abn_segments_quarterly.csv`: loans, deposits and RWA for PBB, Wealth Management, Corporate Banking and Group Functions; 7 quarter ends. Group Functions can be negative due to consolidation/adjustments.

Financial statement values are in EUR **millions**; percentages are stored in percent units and NIM in **basis points**. Input precision is carried forward. Profit/income/cost flows are quarterly, and loans/deposits/capital are stocks at period-end.

## What changed

- `main.py` invokes `src.reported_dashboard.render_reported_dashboard()`, then stops to prevent synthetic monthly views from running. It fails closed if the sourced CSVs are absent.
- `src/reported_dashboard.py` presents executive KPIs, quarterly P&L, balance sheet, capital/liquidity, and reported segment trends.
- Adjacent quarter comparisons are labelled **QoQ**, not MoM or daily; unavailable values are never filled with 0.
- Segment figures are checked against published consolidated amounts at load time (0.01 EURm reconciliation tolerance).
- Original prototype code has **not been deleted**. Legacy news, peers, M&A, forecasting, treasury DV01 and risk-scenario modules are not represented as certified facts.

## Deliberately not generated

No fabricated monthly observations or daily anomalies, bank-level treasury positions, trading sensitivities, IFRS 9 stage estimates, geographic allocations, individual product rates, or speculative forecasts.

The financial investments line is a *consolidated balance-sheet aggregate*, not a duration-bearing portfolio.

## Run

Use existing `app.yaml.txt` command or run `streamlit run main.py`. Install packages including `pandas`, `streamlit` and dependencies used by the existing entry-point imports. The two CSVs are committed in this branch.

## Key financial check — Q2 2026

- Net profit: EUR 780.531615m
- Net interest income: EUR 1,699.854335m
- Loans: EUR 275,750.770085m
- Deposits: EUR 303,187.096112m
- CET1: 15.859229928%
- LCR: 158.6%

**Review / deployment limitations:** this is a provenance-first reporting mode, not a live Databricks ingestion pipeline. The local Streamlit app was not executed in a hosted Databricks workspace from this integration. The original radial/interactive modules are preserved in source but intentionally bypassed because their mathematical assumptions and 30-day synthetic-data requirements would misrepresent quarterly factsheet observations. The branch requires runtime smoke-testing in your workspace before merging.
