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

## Stage 1.3 — proportional zero-based charts, spacing and dates

Following the ABN screenshot review:

- Replaced the **observed minimum–maximum zoom** with a **zero-including y-axis** for the bar and line overlay. For positive values this is zero-based; a ~0.3 pp CET1 change now results in only a small line movement rather than appearing like a major ratio jump. This is an intentionally less dramatic but more faithful view of magnitude.
- Reduced bar opacity, line brightness and glow in the existing green HUD aesthetic.
- Replaced the generic `7Q TREND`/`10Q TREND` labels with **first and last reported quarter and year** (e.g., `Q4 2024` and `Q2 2026`). Each individual quarter has its date and value in the bar's tooltip. Labels are sourced from the real dataset, never constructed from a guessed reporting date.
- Gave the four Real Data KPI cards a minimum row height and permitted page scrolling instead of vertically compressing and clipping their headings/badges when the extra data-source selector consumes viewport height. **Synthetic CSS remains unchanged.**
- The card chart still uses CSS/HTML only and requires **no new packages** or Databricks changes.

**For an existing ABN test deployment, update three files only:**
`src/kpi_sparklines.py`, `src/real_data_mode.py`, and `main.py`.
Continue using the same two real quarterly CSVs and all existing Databricks settings.

The bar+line sparkline is deliberately small and cannot reveal subtle ratio movements as prominently as a zoomed chart. Use the adjacent numerical QoQ delta for precise movements.

## Stage 2 — Quarterly Morning Brief (21 October 2026)

This iteration updates **Real Data / Morning Brief only**; the working Synthetic `src/modules/brief.py` is preserved unchanged.

### Default: executive health check
- Three source-backed Group headline cards: **quarterly net profit, CET1 ratio, LCR**, using the latest reported observation and QoQ movement.
- Hover/focus over each card to reveal a compact bar chart plus trend line from observed quarters (no invented observations). Select **Inspect quarterly trend** to open the detailed section.
- Three concise, source-specific CFO observations for profitability, capital and liquidity using existing Why/Impact context.
- If a business line is selected, the three headline cards adapt to only the disclosed *segment* metrics: loans, deposits and RWA. Group-level profit, capital and liquidity are **not** misrepresented as segment-specific.

### Expanded financial view
- An optional **Expand financial view** toggle opens a 3×3 grid of *real* five-quarter charts in the existing dark/green cockpit:
  - Profitability: Net profit, ROE, cost/income ratio.
  - Capital/risk: CET1 ratio, RWA, cost of risk.
  - Balance sheet/liquidity: customer loans, customer deposits, LCR.
- Each tile includes its five quarter/year labels, exact-level tooltip, bar value, transparent previous-quarter bars and a highlighted latest quarter. The bars have an honest zero-including scale; cost of risk preserves negative values.
- Clicking **Explore metric** reveals the metric's historical bar chart, QoQ/YoY comparison and a sourced values table. The four KPI metrics already covered by the main CFO explanations reuse their Why/Impact/Next narrative. No other causal explanation is invented.
- Optional extra real Group metrics: NII, NIM, fee income, NSFR, total operating income and operating expenses.
- Business-line expanded view shows the *three supported* segment metrics rather than an invented nine-metric grid.

### News placement and source controls
- **External news only**, below the financial overview. The existing Synthetic two-column Internal/External feed remains completely unchanged in Synthetic mode.
- No verified real external feed has been connected yet. The Real Data news section explicitly explains this and displays **no sample headlines**, generated news or artificial bank-impact scores. External article integration is a later source/permission review.

### Files to copy for ABN
If the earlier dual-mode version is already running in a separate ABN Databricks test folder:
1. **Add** `src/reported_brief.py`.
2. **Replace** `src/real_data_mode.py`.

No changes to `main.py`, factsheet CSVs, deployment configuration, `requirements.txt`, `src/hud_css.py` or original synthetic modules for this iteration. Validate hover/focus, expansion, drilldowns, modal scrolling, Synthetic-mode regression and Group/segment filtering inside the actual workspace.

## Stage 2.1 — Morning Brief usability and news alignment (21 October 2026)

Following the ABN screenshots:
- The three headline real-financial cards (profit, CET1, LCR) **always** display their historical mini bar-and-line charts. Hover is no longer required, and the chart remains visible at narrow dialog widths.
- The same **Expand/Collapse financial view** button now closes the view and clears the selected metric drilldown. Clicking a primary-card "Inspect quarterly trend" button opens the expanded view.
- Group's expanded grid has **six**, not nine, five-quarter metrics distinct from the headline cards: ROE, cost/income ratio, NIM, RWA, customer loans and customer deposits. Other supported metrics remain selectable for an individual historical drilldown.
- For selected business lines, the factsheet extract has only loans, deposits and RWA; the expanded panel avoids a duplicate three-chart grid and keeps their detailed historical drilldown available via the top cards.
- The external-news section below the financial review now reuses the **same** `news_signals.csv` / `news_geo_impact.csv` sources, 13-day source-relative recency, ranking and four items as the original Synthetic Morning Brief. It reuses the blue `feed-frame is-external`, coloured impact badges, confidence badge, headline, source links and original content structure, arranged in a responsive two-column layout across the wider Morning Brief modal.
- **Provenance safeguard:** those news rows and model-derived impact/confidence classifications are explicitly labelled **prototype / illustrative** in Real Data mode. They are *not* verified against the ABN AMRO fact sheet, and this is not a live news API. If existing prototype CSVs are absent, the news section shows an informative empty state instead of fabricating headlines.

**ABN copy/paste:** replace only `src/reported_brief.py` in the existing dual-mode workspace. The original synthetic renderer, deployed `main.py`, `src/hud_css.py`, `src/real_data_mode.py`, both financial CSVs, requirements and Databricks settings remain unchanged. To display original news rows, retain the existing `data/news_signals.csv` and `data/news_geo_impact.csv` files from the working Synthetic mode.
