# ABN AMRO CFO Cockpit — dual data-mode foundation

**Branch:** `feature/cfo-dual-data-mode-foundation`; forked from the original working `main`. This intentionally replaces the design direction of draft PR #1 (standalone Streamlit dashboard); do **not** merge that older PR first.

## Behaviour

**Synthetic** (the default): all existing views, styling, generators, business-line pills, radial navigation, scenario/Horizon/Treasury/Peers/Strategy/News/Copilot code continue through the original `build_state` and `RENDERERS`. With no `mode` query parameter, URLs and data remain the same as before.

**Real Data · ABN AMRO** (opt-in): the same `main.py` command bar, cards, dial and modal windows. URL uses `mode=real`, carried through `hud.module_url`, `bl_url`, `investigate_url` and dialog close. Real mode uses `src.real_data_mode.build_reported_state` and `render_reported_module`; never calls the synthetic daily-finance calculation layer or the synthetic Copilot handoff.

Mode changes return to the Home module and preserve the current business-line filter.

## Source and frequency

The existing uploaded `data/ABN_AMRO_Q2_2026_-_Factsheet.xlsx` is the sole source for the two derived extracts:
- `data/abn_quarterly.csv`: 10 quarterly income observations Q1 2024–Q2 2026; seven consolidated balance-sheet/capital/liquidity closes Q4 2024–Q2 2026.
- `data/abn_segments_quarterly.csv`: seven quarters of PBB, Wealth Management, Corporate Banking and Group Functions *loans, deposits and RWA*. Group Functions includes adjustments (which may be negative) so Group totals reconcile.

Original source values are in **EUR million** unless a percentage or basis-point unit is included; NIM is given in **basis points** and converted to percent for the headline label. Data coverage and reconciliation are checked at load.

## Real-mode functionality (phase 1)

| Module | Real-mode behaviour |
| --- | --- |
| Main shell / Group KPIs | Actual CET1, LCR, net profit and NII with **QoQ** deltas |
| Business-line filter | Actual segment loans, deposits, RWA and calculated loan/deposit ratio |
| Morning Brief | Quarter-over-quarter actuals and financial history charts |
| Horizon | Historical reported trends, **no forecast output yet** |
| Treasury | Financial-investments aggregate, LCR, NSFR; no individual securities |
| What-If | Real disclosed opening balances; model intentionally **disabled** |
| Copilot | Paused for real mode, preventing synthetic retrieval |
| News, Peers, Strategy | Clickable modal; awaiting separately supported feeds |

The `NOT_ASSESSED` status deliberately does **not** assign fictional RAG colors/limits to reported figures. `UNAVAILABLE` displays a neutral pending-source badge. This is not a full real-data model migration yet.

## ABN / Databricks compatibility checklist

- Existing `app.yaml.txt`, `requirements.txt`, `src/config.py`, service endpoints, environment variables, Genie connection and SQL warehouse settings: **unchanged**.
- No new runtime library (reuses `pandas` and `streamlit`, already required by the original app); no Excel reader is needed in deployed app.
- No overwrite of synthetic files (`src/data_generator.py`, `src/cockpit_views.py`, `src/cockpit_state.py`, `src/engines.py`, `src/modules/`, `src/hud_css.py`).
- No databases, GitHub tokens, production jobs or Databricks asset permissions changed.
- Status and provenance clearly distinguish real quarter-end from synthetic daily readings; unsupported model outputs are intentionally unavailable.

**To validate in ABN before merging:** run `python -m unittest discover -s tests -p test_dual_mode.py`, start the Databricks Streamlit app with the existing entry command, verify Synthetic is unchanged, then switch to Real Data, test Group and three business lines and every modal, and confirm switching between modes and closing windows retains the selected data mode.

`main` has not been changed. Real Data mode is explicitly opt-in. Neither the tests nor the source-grounded performance of the new mode have been exercised in ABN's Databricks workspace from here.

## Next phase

Adapt individual model modules to a quarterly calculation contract: measured vs calculated vs assumed metrics; quarterly balance-sheet stocks vs flows; forecast and scenario assumptions; source lineage to factsheet cells. Do not reuse synthetic 30-day repricing rates or synthetic portfolio DV01 as ABN financial actuals.
