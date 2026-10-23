# Databricks notebook source
# ABN CFO Cockpit — Real Genie deployment (no code editing needed)
#
# Run All from this notebook in the Git folder. The first run validates
# or publishes the three exact source-backed UC tables in:
# frbg3s_studio_a.cfo_cockpit
#
# To ALSO create the Genie Agent, enter the approved SQL warehouse ID in
# the widget displayed above this notebook, then Run All again.
#
# This never modifies the original Synthetic Genie Agent or its tables.

# COMMAND ----------

from pathlib import Path
import os
import sys

def _find_repo_root():
    """Resolve Git repo regardless of the username or cloned folder name."""
    candidates = [Path.cwd()]
    if "__file__" in globals():
        candidates.append(Path(__file__).resolve().parent)
    try:
        notebook_path = (
            dbutils.notebook.entry_point.getDbutils()
            .notebook().getContext().notebookPath().get()
        )
        candidates.append(Path("/Workspace" + notebook_path).parent)
    except Exception:
        pass
    for candidate in candidates:
        for folder in (candidate, *candidate.parents):
            if (folder / "setup" / "real_genie_auto.py").is_file() and (
                folder / "data" / "abn_quarterly.csv"
            ).is_file():
                return folder
    raise FileNotFoundError(
        "Open THIS notebook from the CFO-Dashboard-New Git folder in "
        "Databricks. The setup requires setup/real_genie_auto.py and "
        "the three data/*.csv extracts in that same Git folder."
    )

REPO_ROOT = _find_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from setup.real_genie_auto import (
    CATALOG, SCHEMA, TABLES, TITLE, create_or_reuse_agent,
    validate_existing_tables,
)

print("Source Git folder:", REPO_ROOT)
print("Target Unity Catalog:", f"{CATALOG}.{SCHEMA}")
print("No existing Synthetic views or Genie settings will be modified.")

# COMMAND ----------

# This is a UI input, not Python you need to edit.
# Copy the SQL Warehouse ID from Databricks -> SQL Warehouses -> warehouse details.
dbutils.widgets.text(
    "sql_warehouse_id", "",
    "SQL warehouse ID (enter to create Genie Agent)"
)
warehouse_id = dbutils.widgets.get("sql_warehouse_id").strip()

# COMMAND ----------

print("Checking the three approved reporting source datasets...")
summary = validate_existing_tables(spark, REPO_ROOT)
for name, details in summary.items():
    print(name, "=>", details)
print("Source check PASSED. Data cutoff: Q2 2026.")

# COMMAND ----------

if not warehouse_id:
    print("")
    print("The 3 Real Data tables are ready.")
    print("NEXT: Choose an approved Pro/Serverless SQL Warehouse.")
    print("Databricks -> SQL Warehouses -> select warehouse -> copy Warehouse ID.")
    print("Paste the ID into the 'sql_warehouse_id' notebook WIDGET and Run All.")
    print("This is a widget value; you do NOT need to edit Python or SQL.")
else:
    from databricks.sdk import WorkspaceClient

    client = WorkspaceClient()
    real_genie_space_id = create_or_reuse_agent(
        client, warehouse_id, REPO_ROOT
    )
    synthetic_genie_space_id = os.getenv("GENIE_SPACE_ID", "").strip()
    if synthetic_genie_space_id and real_genie_space_id == synthetic_genie_space_id:
        raise RuntimeError("Real Genie ID unexpectedly matches Synthetic: STOP")
    print("")
    print("REAL GENIE AGENT READY")
    print("Name:", TITLE)
    print("ID:", real_genie_space_id)
    print("Sources:", ", ".join(f"{CATALOG}.{SCHEMA}.{n}" for n in TABLES))
    print("Instructions and 10 trusted SQL examples were configured.")
    print("")
    print("NEXT IN DATABRICKS APPS (UI only):")
    print("  1. Edit your CFO Dashboard App -> Resources -> Add Genie Agent")
    print("  2. Select the above Real Genie Agent; permission CAN RUN")
    print("  3. Set the resource key to: real-genie")
    print("  4. Ensure deployed app.yaml contains:")
    print("       - name: REAL_GENIE_SPACE_ID")
    print("         valueFrom: real-genie")
    print("  5. Redeploy the App and select Real Data Genie · SQL")
    print("  6. Keep GENIE_SPACE_ID and all Synthetic sources unchanged")
