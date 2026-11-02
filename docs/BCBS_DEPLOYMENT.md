# BCBS Cockpit — ABN computer deployment guide

Branch: feature/bcbs-cover-memo
Source repository: https://github.com/diogomar98/CFO-Dashboard-New/tree/feature/bcbs-cover-memo

## Exactly what changed

| Repository path | Action on ABN computer | Reason |
|---|---|---|
| main.py | REPLACE ONLY after backing up and comparing your locally deployed version | Adds BCBS/CFO workspace router and a back link from the existing CFO UI |
| src/bcbs_cover_memo.py | ADD (new file) | Contains Layer 1/2 placeholders and interactive Layer 3 executive reliability dashboard |
| docs/BCBS_DEPLOYMENT.md | OPTIONAL (documentation only) | This guide |

No changes to requirements.txt, other src/ modules, the Streamlit theme, the Excel factsheet, secrets, databricks settings or app.yaml are required for this prototype.

**Important:** If the version of main.py on the ABN computer has newer work that is not in GitHub, DO NOT blindly replace it. Back it up, compare it, and incorporate the small BCBS router and the return link into that version. The branch was created from CFO-Dashboard-New/main as it existed when the branch was created.

## Recommended deployment steps

1. On GitHub, open the new branch, select **Code > Download ZIP**, and extract it locally.
2. Locate your current Databricks/Streamlit app directory on the ABN computer (it should already contain main.py and src/).
3. Save a backup of the working main.py as, for example, main_backup_before_bcbs.py (keep it outside the deployment directory if scripts are auto-discovered).
4. Copy **src/bcbs_cover_memo.py** into the existing **src/** folder.
5. Compare the branch's **main.py** with your running version. If they match apart from the intended BCBS router, replace main.py with the branch version. Otherwise, apply only the BCBS routing changes to your current version.
6. Run or deploy your existing Streamlit app with **streamlit run main.py**. Do not change your configured App command if it already points to main.py.
7. Test the new entry point before sharing with report owners. Revert using the saved main.py if needed.

## URLs / navigation

- App root (no query string) opens the new BCBS Cockpit, Layer 3 by default.
- ?layer=3 — GRC reliability / limitations dashboard.
- ?layer=2 — Cover Memo / report-owner placeholder.
- ?layer=1 — Operational controls placeholder.
- ?workspace=cfo&enter=1 — Existing CFO home view.
- ?module=brief — Existing CFO Morning Brief window.
- ?module=horizon — Existing CFO Horizon window.
- ?module=scenario — Existing CFO What-If window.
- ?module=copilot — Existing CFO Copilot window.

Existing CFO module deep links continue to open their legacy modules. The CFO UI gets a link back to the BCBS Cockpit.

## Safety and functionality

The entire BCBS Layer 3 display is currently **synthetic/fictional**. The dummy issues, monetary scopes, MIs, trends, status and conclusions do not come from the ABN Power BI Cover Memo or any Databricks data source. The report selector changes only a visible label — it does not retrieve different source data.

Functional prototype features: switch layers, filter material issues by metric and severity, inspect an issue with mitigating controls and actions, and export the illustrative limitations register as CSV.

Do not present synthetic conclusions as real report reliability assessments. Before connecting internal sources, agree the scope/impact methodology, report-owner sign-off, data access and audit trail. Affected population or monetary scope is **not** an actual reporting error; accepted MIs do not prove the reported data is correct.

## Troubleshooting

- Blank page or import error: check you copied the NEW src/bcbs_cover_memo.py file to the same src/ directory main.py uses, and that your deployment uses this branch's main.py.
- Old CFO homepage on entry: clear the query parameters from the URL. Any ?module= or ?enter= link deliberately opens the original CFO experience.
- If using Databricks Apps: restart/redeploy the app after replacing files and verify that the start command still points to main.py.
- If the ABN environment has additional local changes: do not overwrite settings, credentials, data folders or local main.py without comparing.
