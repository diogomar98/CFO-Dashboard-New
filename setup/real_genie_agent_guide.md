# Real Data Genie Agent — ABN Databricks setup

This is a separate **read-only Real Data Genie Agent**. Do not modify the original Synthetic Agent or point Real Data at its certified Synthetic views.

## 1. Publish three real, source-backed Unity Catalog tables

The project already contains **exact, audited CSV extracts**. No invented source table names or new ABN operational data are required for this first stage:

| Genie data object | Source in this repo | Period | Records |
|---|---|---|---|
| `cfo_group_quarterly` | `data/abn_quarterly.csv` | Q1 2024–Q2 2026 | 10 |
| `cfo_segment_quarterly` | `data/abn_segments_quarterly.csv` | Q4 2024–Q2 2026 | 28 (4 lines × 7 quarters) |
| `cfo_group_nii_nim_2021` | `data/abn_group_nii_nim_2021_public.csv` | Q1 2021–Q2 2026 | 22 |

Open a Databricks **Python notebook** with permission to create governed Unity Catalog tables. Make the three CSVs accessible to that notebook in an approved workspace path or UC Volume, and use an **existing** catalog and schema for which you are explicitly authorized to create reporting tables. The simplest notebook cell, after the project files are accessible, is:

```python
import sys
sys.path.insert(0, "/Workspace/Users/YOUR_USER/CFO-Dashboard-New")
from setup.real_genie_uc_setup import prepare_source_tables

summary = prepare_source_tables(
    spark,
    catalog="YOUR_APPROVED_CATALOG",
    schema="YOUR_APPROVED_SCHEMA",
    source_dir="/Workspace/Users/YOUR_USER/CFO-Dashboard-New/data",
)
print(summary)
```

Replace these **example paths and placeholders** with the actual Databricks workspace, catalog and schema paths. If your CSVs are in an approved UC Volume, point `source_dir` to the correct `/Volumes/catalog/schema/volume/folder` path instead. If you run `setup/real_genie_uc_setup.py` as a standalone script, the equivalent configuration can be passed through `REAL_GENIE_CATALOG`, `REAL_GENIE_SCHEMA` and `REAL_GENIE_SOURCE_DIR` environment variables. The script does **not** create or grant access to a new catalog/schema on your behalf.

The script checks **exact column order, dates, row counts, business-line keys and public historical source URLs**, writes explicit nullable floating-point metric types, adds table/column comments and refuses to overwrite an existing table. The reporting data are stored *inside your ABN workspace*; GitHub contains the already-uploaded financial extracts but no credentials.

> Prefer an approved Unity Catalog location with **read-only SELECT** access for the Genie runtime, and no other data sources added to this Agent. The bootstrap script intentionally does not issue `GRANT` statements or modify role permissions.

### Data definitions and mandatory constraints

**Group** contains exactly the 24 named financial fields already in the reporting extract. Names ending `_m` are **EUR millions**; `_pct` are **percentage units** (e.g. 15.86 means 15.86%, not 0.1586); `_bps` are **basis points**. Income values are quarter flows; loans, deposits, RWA and assets are quarter-end positions; CET1, LCR and NSFR are quarter-end ratios. Quarterly balance sheet and capital values are unavailable before Q4 2024. `NULL` means **not supplied**, not zero.

**Segments**: `Personal & Business Banking`, `Corporate Banking`, `Wealth Management`, `Group Functions`. Segment NII, NIM, net profit, CET1 and LCR are **not supplied**. Group Functions can contain a negative loan adjustment. Do not sum business lines to recreate bank-wide totals unless reconciliation is independently demonstrated.

**History** contains independently reviewed Group NII/NIM observations back to 2021, plus an original public factsheet URL and workbook-cell provenance. It is a **historical** table, not an ARX model forecast.

To validate your published tables (replace the two identifiers first):

```sql
SELECT COUNT(*) FROM REPLACE_CATALOG.REPLACE_SCHEMA.cfo_group_quarterly;       -- 10
SELECT COUNT(*) FROM REPLACE_CATALOG.REPLACE_SCHEMA.cfo_segment_quarterly;     -- 28
SELECT COUNT(*) FROM REPLACE_CATALOG.REPLACE_SCHEMA.cfo_group_nii_nim_2021;   -- 22

SELECT date, cet1_ratio_pct, cet1_capital_m, rwa_m
FROM REPLACE_CATALOG.REPLACE_SCHEMA.cfo_group_quarterly
WHERE date = DATE '2026-06-30';

SELECT DISTINCT business_line
FROM REPLACE_CATALOG.REPLACE_SCHEMA.cfo_segment_quarterly
ORDER BY business_line;
```

## 2. Create and tune the new Genie Agent

In Databricks: **Genie / Genie Agents → Create**. Name it **ABN CFO Cockpit — Real Reported Data**. Select an approved Pro/Serverless SQL warehouse, and attach ONLY the three UC tables you created (not any Synthetic views).

**Description to paste:**

> Read-only ABN AMRO CFO analyst for reconciled, reported quarterly financial figures. It answers Group profitability/capital/liquidity questions, quarterly Group NII/NIM trends since 2021, and business-line loans/deposits/RWA for Q4 2024–Q2 2026. The latest financial reporting cutoff is Q2 2026. Every numerical statement must be traceable to the attached certified reporting sources; missing indicators remain unavailable. It does not access Synthetic data, internal transactional systems, live markets, peer data or model forecasts.

**General instructions to paste** into Configure → Instructions (may appear as Configure → Examples / Text depending on ABN's Genie version):

1. Use ONLY the three attached Real Data Unity Catalog reporting objects. These are disclosed/extracted ABN AMRO financial facts, **not** the synthetic certified dataset. Do not query other objects or infer extra periods/metrics.
2. Treat `date` as the **last day of a financial quarter**. When asked for the latest figures, use `MAX(date)`. Never pretend data are daily, monthly, or live.
3. Group P&L starts Q1 2024; quarter-end Group capital/balance sheet starts Q4 2024; business lines start Q4 2024; independently checked Group NII/NIM starts Q1 2021. Preserve `NULL`: do not interpolate, invent zero values or pull Group figures into missing segment fields.
4. `_m` denotes **EUR million**; `_pct` is a percentage displayed on a 0–100 scale; `_bps` is basis points. Compare percentage *rates* in percentage points. For `cost_of_risk_bps` retain the signed value as reported.
5. Income/expenses are **quarterly flows**; loans, RWA, deposits, assets are **quarter-end stocks**. Do not SUM quarter-end balances over multiple quarters to derive annual stocks. When asked for annual profit, sum only the four relevant *quarterly net profits*, making the quarter coverage explicit.
6. Business-line queries MUST filter `business_line` to the user-selected line. Only `loans_m`, `deposits_m`, `rwa_m` are available by segment. No segment NIM, NII, CET1 ratio, net profit or LCR is supplied.
7. Group and business-line figures have different scope. Don't join Group records to every segment and then sum duplicate Group metrics. The `Group Functions` segment may include negative adjustments; preserve them.
8. For 2021-on NII/NIM, prefer `cfo_group_nii_nim_2021` and expose the `source_url` when explaining a historical value. It is NOT a forecast, a budget or a statement about management guidance.
9. When asked **why** a change happened, quantify the supported observed difference but **do not invent business causation** (loan mix, regulation, hedging, deposit beta, credit loss or portfolio shifts) without contemporaneous written source commentary, which these tables do not contain.
10. Genie generates read-only SQL. Provide concise answers with the reporting period and Group/segment scope. If unsupported, explain exactly what additional governed data source would be needed. Do not manufacture peer comparisons, news, benchmarks, forecasts or regulatory thresholds.
11. If exact case distinctions matter, match literal `business_line` values as published. Do not call `Personal & Business Banking` "Personal Banking" without clarifying that it is the published scope.
12. SQL answer examples and any SQL functions added to the Agent must operate only on these three tables and cannot perform database writes. Avoid join relationships by default: the Group series and the business-line table are **not interchangeable reporting grains**.

**Dataset descriptions and column comments** are added by the setup script from the exact file headers. In the Agent UI, review Configure → Data / Knowledge Store to ensure those metadata are present. In Configure → Examples, paste the individually named SELECT statements from `setup/real_genie_trusted_queries.sql`. You can add one at a time and run each to verify results.

## 3. Connect the app (without redirecting Synthetic)

1. Copy the new **Real Genie Agent ID** from its Databricks URL/settings.
2. Add `REAL_GENIE_SPACE_ID=<your new agent ID>` to the **Databricks App environment**. Keep the existing `GENIE_SPACE_ID` untouched; that belongs exclusively to Synthetic.
3. Attach the new Agent as an App resource with **CAN RUN** (or the current equivalent) and ensure app user / service principal access to the approved SQL warehouse and the three UC datasets. ABN permission requirements may vary depending on identity forwarding.
4. Restart/redeploy the App. Open **Real Data → Ask CFO Copilot** or floating **Jarvis**, set **Answer using → Real Data Genie · SQL**, then test the questions below.
5. Open **Inspect Genie SQL and retrieved source rows** under an answer. Check the query against the configured UC objects. Factsheet AI remains the default mode and is kept in **separate chat threads**, including separate 36-hour session history.

No token, real bank password, Genie space ID or confidential notebook output should be committed to GitHub.

### Minimal acceptance tests

| Question | Required behavior |
|---|---|
| What was Q2 2026 Group net profit? | Queries `cfo_group_quarterly`, includes Q2 2026 and EUR m |
| How did NIM change between 2022 and 2023? | Uses public `cfo_group_nii_nim_2021`, basis points, quarter precision |
| Compare Wealth Management and Corporate Banking RWA in Q2 2026 | Reads `cfo_segment_quarterly`; two named lines, no Group misattribution |
| What was Personal & Business Banking NIM? | Says **unavailable**; does not substitute Group NIM |
| What was 2023 Group CET1? | Says **not in attached table**; does not extrapolate older quarter-end ratios |
| How much did ECB rate decisions increase ABN NII? | Requires approved causal/sensitivity data; do not invent business causality |
| Switch to Synthetic Copilot | Original Synthetic Genie Space and its sample data remain unchanged |

### Security and provenance

This integration reuses existing corporate `WorkspaceClient` auth and Genie SDK (same connector as Synthetic), but the Real adapter is **separate** and cannot enter Synthetic mock mode. Genie SQL, query rows and AI commentary are shown distinctly. Genie/SQL warehouse permissions and the three attached datasets are the primary access boundary. The current prototype session stores short-lived Genie conversation IDs; no app-global chat store or background agent is installed.
