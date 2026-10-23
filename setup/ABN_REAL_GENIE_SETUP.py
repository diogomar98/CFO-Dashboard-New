# Databricks notebook source
# ABN CFO Cockpit — Real Genie deployment (no code editing needed)
#
# Open as a Databricks Python notebook and click Run All ONCE.
# This publishes or verifies the 3 reporting tables and creates/reuses
# the separately governed Real Genie Agent using preconfigured settings:
# Catalog/schema: frbg3s_studio_a.cfo_cockpit
# SQL warehouse: 7405605052754358
# No widgets, SQL editing, credentials or manual copy/paste of SQL examples.
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
    CATALOG, SCHEMA, TABLES, TITLE, WAREHOUSE_ID, create_or_reuse_agent,
    validate_existing_tables,
)

print("Source Git folder:", REPO_ROOT)
print("Target Unity Catalog:", f"{CATALOG}.{SCHEMA}")
print("No existing Synthetic views or Genie settings will be modified.")

# COMMAND ----------

print("Checking the three approved reporting source datasets...")
summary = validate_existing_tables(spark, REPO_ROOT)
for name, details in summary.items():
    print(name, "=>", details)
print("Source check PASSED. Data cutoff: Q2 2026.")

# COMMAND ----------

from databricks.sdk import WorkspaceClient

print("Creating or verifying the Real Genie Agent...")
print("Approved Genie SQL warehouse:", WAREHOUSE_ID)
client = WorkspaceClient()
real_genie_space_id = create_or_reuse_agent(
    client, WAREHOUSE_ID, REPO_ROOT
)
synthetic_genie_space_id = os.getenv("GENIE_SPACE_ID", "").strip()
if synthetic_genie_space_id and real_genie_space_id == synthetic_genie_space_id:
    raise RuntimeError("Real Genie ID unexpectedly matches Synthetic: STOP")

print("")
print("REAL GENIE AGENT READY")
print("Name:", TITLE)
print("ID:", real_genie_space_id)
print("Sources:", ", ".join(f"{CATALOG}.{SCHEMA}.{n}" for n in TABLES))
print("Financial instructions and 10 trusted SQL examples are configured.")
print("")
print("FINAL STEPS IN THE DATABRICKS APPS UI (no code editing):")
print("  1. Edit CFO Dashboard App -> Resources -> Add Genie Agent")
print("  2. Select this Real Genie Agent; permission CAN RUN")
print("  3. Give the resource the key: real-genie")
print("  4. Copy the ready-made app.yaml from this Git repo into your ABN App")
print("     (verify existing Synthetic and other settings are preserved)")
print("  5. Redeploy; choose Real Data -> Real Data Genie · SQL")
print("  6. Verify Synthetic mode still uses the original Genie Agent")
