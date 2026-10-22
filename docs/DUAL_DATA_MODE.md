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

## Stage 3 — quarterly Horizon with the Synthetic layout (21 October 2026)

**Implementation:** `src/reported_horizon.py` renders a separate Real Data Horizon using the original Synthetic experience as the reference. `src/reported_horizon_engine.py` contains the dependency-light, testable deterministic quarterly calculations.

### Retained visual structure
- Four headline forecast cards across the top (year-end NIM baseline, FY NII baseline, next-quarter NIM step and balance-sheet run-rate).
- Two-column actual-to-baseline trajectory and Forward Lens with the same green historical line/purple dashed projected line, explicit legend and a What-If navigation link.
- Selectable paths for reported NIM, quarterly NII, loans and deposits.
- An unobtrusive, editable assumptions expander so the default view remains clean.

### Sources and baseline methodology
- Actuals: from the existing `data/abn_quarterly.csv` exclusively; latest quarter Q2 2026. The chart plots true calendar-quarter labels and does not create monthly/daily observations.
- Future points: four quarterly *illustrations* from the latest reported close (Q3 2026–Q2 2027). First 2026 year-end NIM is the illustrative Q4 2026 value. FY2026 NII combines sourced Q1+Q2 actuals with *clearly identified* Q3+Q4 modelled NII. No annualisation of partial-year actuals is presented as a reported FY number.
- Initial editable inputs are the median of the most recent three **consecutive reported QoQ moves**, subject to explicit modelling guardrails: first-quarter NIM movement ±40 bps, NII growth ±15% per quarter, loans/deposits growth ±10% per quarter. A 50% per-quarter retention of the NIM momentum is an **unsourced modelling choice**, not ABN guidance.
- The four trajectories use their separately entered assumptions. NIM is **not** inferred from NII divided by quarter-end loans; customer loans are not treated as interest-earning asset averages. The model neither estimates ECB betas, taxes, credit losses, CET1 sensitivities nor an audited combined P&L.
- No confidence percentages, 90% prediction bands, official budget comparisons or regulatory RAG ratings are shown: there is not enough calibrated evidence in the factsheet to support them.
- When a specific business line is selected, the view explicitly states that these are **Group** NIM/NII baselines; no invented segment profitability forecast is displayed.

### ABN deployment / backwards compatibility
If you already have the working dual-mode app and Stage 2.1 Morning Brief installed, **copy only these three files**:
1. Replace `src/real_data_mode.py`.
2. Create `src/reported_horizon_engine.py`.
3. Create `src/reported_horizon.py`.

Do **not** copy/replace `src/modules/horizon.py`, `src/engines.py`, existing Synthetic data generators, `main.py`, `src/hud_css.py` or financial/news CSVs. The existing `requirements.txt` and `app.yaml.txt` are unchanged. The UI uses Altair, already imported by the working Synthetic Horizon via `src/charts.py`; no new runtime dependency is added to the deployed app.

The non-ABN GitHub checks include source reconciliation, quarter-end dates, Q2 2026 actuals, explicit forecast provenance, NIM momentum decay, independent NII assumptions, full-year NII actual/projected split, safe failure on invalid inputs, Altair chart generation and preserved Synthetic route. **A workspace UI smoke test is still required** for modal sizing, forms, navigation, and changing assumptions before merge.

## Stage 3.1 — Real Data Horizon, 2021-on public series and forecast ranges

**Scope:** Real Data Horizon only. The Synthetic Horizon, its monthly engines, synthetic source CSVs and complete home/dashboard/brief navigation remain untouched. This stage **supersedes the Stage 3 Real Horizon assumptions panel**; Stage 3's `src/reported_horizon_engine.py` remains in GitHub for legacy test coverage but is not used by Real Horizon.

### Public source trail

- **ABN Group:** `data/abn_group_nii_nim_2021_public.csv` — **22 consecutive quarters** Q1 2021–Q2 2026, NII EUR million and NIM basis points from the official public XLSX factsheets; per-row source document URL and exact Group sheet/cell. Validated by independently comparing all 21 adjacent-quarter source workbook pairs for NII and NIM plus selected ABN press releases and both Q4 2021 reporting-structure workbooks: **49/49 checks passed**. Original source evidence: https://github.com/diogomar98/CFO-Dashboard-New/actions/runs/39640848529/artifacts/12365272432.
- **ECB DFR:** `data/ecb_dfr_quarterly_2021_public.csv` — **22 matching quarters**, calendar-day-weighted average and quarter-end policy rate, reconstructed from official ECB *rate-change observations*. Original dated ECB CSV URL and SHA-256 recorded on every output row; supporting retrieval code `research/build_ecb_dfr_quarters.py`.
- Each app load rechecks exact quarter continuity, non-null levels, source domains and whether Q2 2026 public NII/NIM agrees with the already-deployed Q2 2026 factsheet values to within EUR 0.005m / 0.005bps. On discrepancy **fail closed**, never fall back to synthetic financial data.
- Historical loans/deposits/RWA/CET1 were **not** independently reconciled over this 22-quarter sample; they are not projected in Stage 3.1. The previously reviewed quarterly Group home and Morning Brief files and dashboards remain unchanged.

### Forecasting

- `src/public_horizon_engine.py` implements **two candidates per metric**: a last-observation no-change benchmark and a compact ridge-regularised ARX using only lagged NII/NIM and **lagged ECB DFR quarterly changes**. NII is modelled in log level to preserve positivity.
- A chronological expanding-window, rolling-origin evaluation from minimum 12 quarters measures one-quarter absolute forecast error for each candidate. **Auto** selects ARX *only* if its 1Q MAE improves on no-change by over 5%; otherwise uses simpler benchmark. A manual method selector makes either benchmark inspectable.
- Neutral DFR future path holds the Q2 2026 **known quarter-end** DFR rate flat. Users can explicitly override a next-quarter ECB-rate shock ±100bps; the ARX uses lagged rate changes and may respond with a one-quarter delay. The no-change benchmark has no rate sensitivity. Further manual adjustments are NIM bps/quarter and NII %/quarter, clearly labelled scenario assumptions (zero in neutral case).
- Displays the original-style four prominent forecast cards, green **actual** + purple dashed **estimate** trend and Forward Lens, with metric selector between NIM and statutory Group NII, 12Q/all-22Q history and optional 90% / 95% / Both / Off bands. FY2026 NII is clearly split into Q1–Q2 official values and Q3–Q4 projected values.
- **90% / 95% bands are conditional model-estimated ranges**, using Gaussian critical values × observed horizon-specific rolling-origin RMSE. There is **no demonstrated 90/95% future coverage**, no robust tail calibration, no guaranteed normal residuals, and no 99% interval requirement. Backtest results and sample counts are exposed in the UI. These estimates do not account comprehensively for structural breaks, acquisition perimeter, unsupported rate expectations or management adjustments.
- The FY2026 **commercial NII management guidance including NIBC** is not used as a training target and is not falsely equated with the model's **statutory Group NII**. This research model is not ABN guidance.
- Neither use `src/engines.py` nor modify `src/modules/horizon.py`. No change to requirements: Streamlit/Pandas already depend on NumPy; Altair is used by the previous Synthetic Horizon.

### Deployment on top of Stage 3 ABN test workspace

1. **Replace** `src/reported_horizon.py` (same styling, new source-aware forecast UI).
2. **Add** `src/public_horizon_engine.py`.
3. **Add** `data/abn_group_nii_nim_2021_public.csv` (22 official quarters).
4. **Add** `data/ecb_dfr_quarterly_2021_public.csv` (22 rate-derived quarters).

There is **no need to replace** `main.py`, `src/real_data_mode.py`, `src/modules/horizon.py`, `src/reported_horizon_engine.py`, `requirements.txt`, the Q2 factsheet CSVs or Synthetic files. New real-data sources are limited to public files. GitHub tests verify source alignment, Model-driven calculations, 90/95 nested shading, FY income split, fail-closed behavior, scenario isolation, and unchanged Synthetic routing. Test the Streamlit modal, chart legend and sliders visually within ABN before demo.

## Stage 4 — separate neutral Horizon and driver-focused What-If

**Scope: Real Data only. Original Synthetic renderer, monthly simulations and financial reports remain unchanged.**

- **Horizon** in `src/reported_horizon.py` now always runs the automatically selected **neutral** 2021-on public NII/NIM baseline (`model_preference="auto"`, zero shocks/overlays). It retains the four highlighted cards, historical actual-to-projection line, modelled 90%/95% ranges, validation diagnostics, forward lens and navigation to What-If. Removed the former rate-shock and direct NII/NIM adjustments from Horizon's assumptions form; the fourth card reports the **Q2 2026 actual DFR** and labels the held-flat future rate convention.
- **What-If** in NEW `src/reported_scenario.py` runs an explicitly matched neutral-versus-shock comparison with `src/public_scenario_engine.py`. Its source engine and financial source files are **the same** as Horizon: independently cross-checked public ABN Group NII/NIM and publicly derived quarterly ECB DFR history. The original Synthetic `src/modules/scenario.py` is not imported or edited.
- ECB shock input (−100…+100 bps) changes the *hypothetical* flat forward ECB DFR at the model's Q2 2026 cutoff, not a published forward curve. The initial selected What-If method is **ARX**, making rate sensitivity testable. Its lag means the rate-shock effect can only appear from **Q4 2026**, not Q3. Under **Flat financial baseline (ECB-insensitive)**, ECB shocks cannot change financial forecasts; a visible warning recommends ARX. **Auto · same as Horizon** can select different methods for Group NII and NIM and labels ECB-insensitive metrics explicitly.
- Direct NIM bps-per-quarter and NII percent-per-quarter adjustments now exist **only under Advanced overrides** in Real What-If. Those impose a change directly (they are not driven from a deposit/asset repricing model), compound each future quarter and can move NII/NIM independently. Inputs default to zero.
- Matched-model visual comparison includes **reported Group actuals (green), neutral reference (purple dashed), selected scenario (amber)**, and derived **Q4 2026 NIM delta, Q4 2026 NII delta, FY2026 NII delta** plus 4-quarter details and actual/projected split. Both runs use the **same selected model**, financial actuals and source cutoff. Thus an Auto-selected flat model may differ from the forced-ARX What-If reference; the comparison panel always compares like with like.
- Clearly states model limitations: public Group only, not a loan/deposit beta sensitivity, not a CET1 or regulatory stress test, not management guidance; 90/95 interval coverage is not guaranteed by limited historical testing. A zero estimated impact under the flat benchmark **does not imply zero real-world financial exposure**.

**Deploy to an existing working Stage 3.1 Databricks Real Data workspace:** replace `src/reported_horizon.py` and `src/real_data_mode.py`, add `src/reported_scenario.py` and `src/public_scenario_engine.py`. Previous public source CSVs and `src/public_horizon_engine.py` remain unchanged. Do **not** replace `main.py`, `src/modules/horizon.py`, `src/modules/scenario.py`, the original financial CSVs, `src/hud_css.py`, requirements or Databricks configuration. Validate in the deployed Streamlit environment before demonstration.

## Stage 5 — Three Horizon headline cards and Real Copilot evidence foundation

- Real Data Horizon's top strip now has **three cards**: Q4 2026 NIM baseline, FY2026 NII baseline (actual/projected clearly separated), and the **reported Q2 2026 ECB DFR**. The previously weak 'next-quarter NIM step' was removed. Real Morning Brief remains three headline cards.
- Real Copilot now routes to `src/reported_copilot.py`, a **read-only evidence inspection workspace**. Its pure context builder (`src/reported_copilot_evidence.py`) creates small, structured, provenance-labelled, scope-aware packets using the existing quarterly reporting state.
- Group topics: Capital (CET1 ratio, capital, RWA); Profitability (profit, NII, NIM, income, expenses, impairments); Liquidity (LCR, NSFR, loans, deposits). For selected business lines, only disclosed **segment loans/deposits/RWA** are available. Unavailable fields and unsupported causal claims are **not invented**.
- A source-value preview, QoQ movements and JSON context contract are inspectable before an LLM is connected. **No LLM, Genie, network, synthetic fallback or external data transfer is activated** by this stage; these are not AI-generated answers.
- **Credential/security gate for future live Copilot:** The pre-existing Synthetic AI gateway client contains an embedded authentication credential and uses disabled TLS certificate verification. Do **not** reuse that client to transmit Real Data. Before activation, revoke/rotate exposed credentials, remove them (including from Git history where required), use an approved Databricks secret or authorized identity flow, enable proper server certificate verification, and obtain approval to send the selected data fields. Avoid logging prompts containing sensitive or undisclosed data. This stage deliberately leaves Synthetic runtime code untouched.
- The first recommended next AI call is a read-only, sourced Group capital investigation that receives a validated evidence packet and returns an answer citing the actual source values and identifying missing causal evidence. Gate the response before adding other tools, scenario calls or natural-language SQL.
- To deploy on top of existing Stage 4 ABN workspace: replace `src/reported_horizon.py` and `src/real_data_mode.py`; add `src/reported_copilot.py` and `src/reported_copilot_evidence.py`. No changes to Synthetic modules, `main.py`, financial CSVs, or the deployed credentials configuration.

## Stage 5.1 — First LIVE Real Data Copilot investigation: Group CET1 (22 October 2026)

**Scope:** Group CET1 only, within the existing *Real Data* dashboard. Synthetic Copilot, Genie connection, gateway client and all financial CSVs remain untouched.

- **Existing AI Gateway reused, with zero connection changes.** New `src/reported_copilot_partner.py` calls the exact existing `src.openai_partner.generate_prompt_response(prompt)` used by Synthetic Data Copilot. In ABN, this automatically uses your local `openai_partner.py` configuration/token. No authentication credentials or gateway endpoints are copied into new code, added to the repo or surfaced in the UI.
- New `src/reported_copilot.py` retains the three reported metric cards and adds a **verified capital/RWA ratio decomposition**, "Investigate Q2 2026 CET1 movement" button, and a Real-only chat input and chat history. All model-generated responses are explicitly labelled, with the actual source figures and calculations separately displayed.
- **Numerator-first identity**: CET1 Ratio = (CET1 Capital / RWA) × 100. For the two published quarters the calculation isolates (1) numerator change at the previous RWA, then (2) denominator change at the latest CET1 capital. Contributions sum exactly to the reported quarter-on-quarter CET1 percentage-point change. This is **arithmetical attribution only**; it does **not** establish earnings, dividends, regulatory or credit migration causes.
- **Prompt is always self-contained and source constrained:** user's question, ABN Q2 2026 reported Group figures in source-annotated evidence, and the deterministic ratio bridge. It requires Why / Impact / Next and explicitly identifies missing publicly supported causal evidence. It contains no synthetic metrics, forecasts, confidential SQL, external news or unapproved management thresholds. If the gateway fails, UI shows a short error: no synthetic or unsupported deterministic answer is substituted.
- For other Real topics and selected business lines, the read-only evidence view remains accessible but **live AI is not enabled** until their scope-specific checks are built. **Genie is not invoked** by this first CET1 investigation; all required metrics already exist in the sourced quarterly extract.
- **Security/operational caution:** The original legacy `src/openai_partner.py` contains a hardcoded authentication value and uses `verify=False` for outbound HTTPS. User reports replacing the token in the ABN environment. No secrets or legacy client changes were made in this development step, but security remediation remains a separate recommended deployment gate: rotate old credentials, use approved Databricks secrets/identity and HTTPS certificate verification. Never publish or log a token; verify the configured gateway and its data-policy approval inside ABN before exercising live prompts.
- **Databricks deployment when Stage 5 is already installed:** add `src/reported_copilot_partner.py`, replace `src/reported_copilot.py` and `src/reported_copilot_evidence.py`. The existing Real Data router already points at the correct view. Do not replace `openai_partner.py`, `genie_partner.py`, `src/modules/copilot.py`, `main.py`, CSV data, forecasts, or other Synthetic modules.
- **Test gate:** tests mock the existing gateway, verify exactly one call and no Genie, test real financial arithmetic and source citations, reject wrong scope/missing figures and check no fallback to synthetic results. These tests do **not** test connectivity to the corporate ABN gateway from the public GitHub environment. Actual response quality, gateway availability and Databricks chat layout must be validated in ABN.

## Stage 5.2 — Embedded multi-turn Copilot with deterministic visual evidence

**Real Data-only changes.** Synthetic views, `src/modules/copilot.py`, `src/openai_partner.py`, Genie, report data and all other Synthetic modules are preserved. Nothing merged into `main`.

- **Embedded floating launch:** `main.py` mounts a single `render_floating_copilot(s)` on the Real Data command center home and inside whichever Real Data report dialog is active. Native Streamlit `st.popover`, styled as a bottom-right CFO Copilot balloon, avoids a separate page. When the old Real Data Copilot route is opened from the dial, it uses the same conversation engine, but does not duplicate the balloon. Popover interactions rerun Streamlit while keeping the popover open. Real-only CSS, with a responsive panel for narrow windows.
- **Persistent follow-up questions:** `src/reported_copilot_partner.py` still calls the existing `src.openai_partner.generate_prompt_response(prompt)` exactly once for each submitted turn; its new `history` argument includes up to 8 bounded previous user/assistant messages, never model-supplied authoritative facts. Each prompt explicitly marks prior responses as **untrusted dialogue** and separately provides the source-reconciled CET1 capital/RWA arithmetic. Responses never use Synthetic fallback, external news or Genie. `st.session_state["real_cfo_cet1_messages"]` retains recent messages across the Real dashboard, clears on a new conversation and resets on source scope/quarter changes.
- **CFO visual evidence in chat:** deterministic, source-verified Q1/Q2 CET1 ratio cards, Altair positive/negative bars for CET1 numerator and RWA denominator *arithmetic* contributions, and a two-quarter reported-ratio bar chart; exact source figures and caveats beneath. Graphs are computed in Python from the same verified CET1 evidence packet; the language model is **not asked to generate charts or numeric series**. The visual section expands after the first reply.
- The floating chat currently supports **Group CET1 only**. Segment-scoped pages show a clear explanation rather than leaking Group capital values into a segment investigation; Profitability/Liquidity and scenario prompts are deferred for a later phase.
- Controls include a one-click first investigation, bounded 800-character follow-up form, scrollable conversation, "New conversation", and visible sourced-versus-AI interpretation labels. No full browser interaction or unsupported external data transfer; gateway request semantics are unchanged.
- **Security:** user's ABN token remains in their own existing gateway module. The public repository still contains a retired embedded token and legacy `verify=False`: code was *not* modified during this feature to preserve existing integration per user's request, but authorization renewal and transport certificate validation remain required independent security actions.
- **ABN test deployment:** replace `main.py`, `src/reported_copilot.py`, `src/reported_copilot_partner.py`; **add** `src/reported_copilot_balloon.py`. The existing `src/reported_copilot_evidence.py` can remain unchanged. No change to `openai_partner.py`, `genie_partner.py`, quarterly financial CSVs, `src/real_data_mode.py`, CSS sources, `requirements.txt` or synthetic data modules.
- The GitHub unit tests mock the corporate Gateway; **validate popover location/scroll/keyboard usage and live conversation in ABN** before showing to the CFO. Whether the popover fits inside a Streamlit dialog depends on the deployed Streamlit version and current styling. Keep the original Real Copilot page as a functional fallback during validation.
