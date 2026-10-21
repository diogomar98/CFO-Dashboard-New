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

## Stage 1.1 — executive KPI insights and compact quarterly trends (21 October 2026)

The Real Data cards beside the radial now show a **mini sparkline on the right**, drawn only from disclosed observations: 7 reported quarters of CET1/LCR and business-line balances, or 10 reported quarters of net profit/NII. SVG needs no additional Python or Javascript dependencies. It is neutral green in the existing design, and is not an assessment of good/bad direction.

- The cards' **Why** comments now quantify the actual QoQ movements and relevant reported drivers: CET1 capital/RWA, LCR/NSFR/deposits, profit/income/expenses/impairments, and NII/NIM/loan balances. They do not claim more granular causal attribution than the source allows.
- **Impact** explains related reported trends, their implications and source limitations. **Next** identifies concrete validation questions, not fabricated forecasts.
- The four Group KPI **RAG** lights are *directional momentum screening*, **not bank-approved risk limits**: Green = a higher latest-quarter reading, Amber = flat or the first decline, Red = two consecutive declines. The rule appears in the hover explanation and explicitly disclaims ABN regulatory/management thresholds. Segment loans, deposits, RWA and L/D remain *not rated* where the desirable direction is context-dependent.
- Real mode's business-line dial now explicitly says the Group NIM is not a disclosed business-line NIM.
- Synthetic markup and metrics have not been changed.

**If you already copied Stage 1 into ABN:** update **only three files**:
1. Replace `main.py` with the updated dual-mode branch version.
2. Replace `src/real_data_mode.py`.
3. Add **new** `src/kpi_sparklines.py`.

There is **no change** to the two quarterly CSVs, `hud_css.py`, `requirements.txt`, `app.yaml.txt`, Git credentials or existing Databricks connections.

Automated checks: `python -m unittest discover -s tests -p test_dual_mode.py -v`. Review card widths, hover content and mode transitions at your ABN workspace's actual screen size before merging.

## Stage 1.2 — visible bar + trend overlays (21 October 2026)

The original sparkline used nested inline SVG inside the `st.html()` home HUD. Streamlit's DOMPurify sanitization can remove the SVG drawing while leaving the text label visible. The revised `src/kpi_sparklines.py` uses ordinary HTML span elements and CSS to render **both the individual quarter bars and connecting trend-line segments** inside each card. No SVG, canvas, Javascript, charting dependencies, or change to the deployed ABN environment is required. Each plot is drawn from the *same reported data already in the cards*.

- Group figures: 7 quarters for CET1/LCR, 10 quarters for net profit/NII; segment figures: 7 quarters.
- Both layers use the same **zoomed observed-value scale** to make small quarter-to-quarter changes visible in a 110-pixel chart; the accessible tooltip explicitly identifies the zoom (not a zero baseline). Plots are descriptive, not performance or risk ratings.
- The existing dark green visual palette remains; latest quarter highlighted. Existing synthetic path unchanged.

**If Stage 1.1 is already installed and the chart label displays without the plot, copy only** `src/kpi_sparklines.py` **from this branch into the same `src/` folder in Databricks.** The existing `main.py` import/function call and the real-data state do not change.
