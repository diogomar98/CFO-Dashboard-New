# Databricks notebook source
# CFO Cockpit — Replace news_signals from the user-supplied 26-row news snapshot
#
# NO code edits required. Open in ABN Databricks as a Python notebook and
# click Run All. This affects ONLY frbg3as_studio_a.cfo_cockpit.news_signals.
#
# SAFETY: verify all 21 existing columns and expected types before mutation,
# create a backup table, then replace the target's rows transactionally via
# SQL INSERT OVERWRITE (does not drop or recreate the target).
#
# IMPORTANT: classification_method in the provided data identifies this as a
# SYNTHETIC PROTOTYPE assessment, not source-verified impact analysis.
# The articles and public URLs have NOT been independently fact-checked.

# COMMAND ----------

import csv
from pathlib import Path
from datetime import date

TARGET = "frbg3as_studio_a.cfo_cockpit.news_signals"
BACKUP = "frbg3as_studio_a.cfo_cockpit.news_signals_backup_20261023"
EXPECTED_COUNT = 26

# COMMAND ----------

def find_project_root():
    candidates = [Path.cwd()]
    if "__file__" in globals():
        candidates.append(Path(__file__).resolve().parent)
    try:
        context_path = (
            dbutils.notebook.entry_point.getDbutils()
            .notebook().getContext().notebookPath().get()
        )
        candidates.append(Path("/Workspace" + context_path).parent)
    except Exception:
        pass
    for base in candidates:
        for root in [base, *base.parents]:
            if (root / "data" / "news_signals.csv").is_file():
                return root
    raise FileNotFoundError(
        "Could not find data/news_signals.csv in this Databricks Git folder. "
        "Copy it alongside the existing data/ and setup/ folders."
    )

source = find_project_root() / "data" / "news_signals.csv"
with source.open(encoding="utf-8-sig", newline="") as handle:
    reader = csv.DictReader(handle)
    names = list(reader.fieldnames or [])
    records = list(reader)

if len(records) != EXPECTED_COUNT:
    raise ValueError("Expected exactly 26 replacement news_signal rows")
if len(names) != 21 or len(set(names)) != len(names):
    raise ValueError("Expected exactly 21 unique CSV columns")
if any(None in row or any(value is None for value in row.values()) for row in records):
    raise ValueError("Invalid CSV column alignment or unescaped comma")
if any(not name.replace("_", "").isalnum() for name in names):
    raise ValueError("CSV contains an unsupported column name")
ids = [row["news_id"] for row in records]
if ids != [f"NEWS_{number:03d}" for number in range(1, EXPECTED_COUNT + 1)]:
    raise ValueError("Expected NEWS_001 to NEWS_026 in order without duplicates")
if any(row["classification_method"] !=
       "Synthetic prototype classification layered on public source"
       for row in records):
    raise ValueError("Classification metadata differs from supplied prototype")
for row in records:
    date.fromisoformat(row["published_date"])
print("Validated:", len(records), "news signals,", len(names), "columns.")
print("Article claims and classification scores have not been fact-checked.")

# COMMAND ----------

if not spark.catalog.tableExists(TARGET):
    raise RuntimeError(
        f"The table {TARGET} does not exist. Nothing was changed. "
        "Confirm the existing news_signals table location first."
    )
current = spark.table(TARGET)
schema = current.schema
if list(current.columns) != names:
    raise RuntimeError(
        "Existing news_signals columns differ from the CSV. "
        "Nothing was overwritten; inspect the table schema."
    )
if spark.catalog.tableExists(BACKUP):
    raise RuntimeError(
        f"Backup {BACKUP} already exists. Inspect target and backup "
        "before retrying, to avoid replacing the original snapshot."
    )

from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType

string_schema = StructType([
    StructField(name, StringType(), True) for name in names
])
raw = spark.createDataFrame(
    [tuple(row[name] if row[name] != "" else None for name in names)
     for row in records],
    schema=string_schema,
)
typed = raw.select(*[
    F.col(field.name).cast(field.dataType).alias(field.name)
    for field in schema.fields
])

# Fail if a supplied nonempty value could not be converted to its existing
# Databricks type. Missing values are not silently set to zero.
bad_types = [
    field.name for field in schema.fields
    if raw.filter(
        F.col(field.name).isNotNull()
        & F.col(field.name).cast(field.dataType).isNull()
    ).limit(1).count()
]
if bad_types:
    raise ValueError("CSV values do not match target column types: " +
                     ", ".join(bad_types))
for field in schema.fields:
    if not field.nullable and typed.filter(
        F.col(field.name).isNull()
    ).limit(1).count():
        raise ValueError(
            f"Required column {field.name} contains blank CSV values."
        )
if typed.count() != EXPECTED_COUNT:
    raise RuntimeError("Typed source no longer contains exactly 26 rows")
print("Existing target schema confirmed:", TARGET)
print("Creating backup:", BACKUP)

# COMMAND ----------

# Never change the target before a complete snapshot has been saved.
spark.sql(f"CREATE TABLE {BACKUP} AS SELECT * FROM {TARGET}")
print("Original rows preserved in backup:", spark.table(BACKUP).count())

typed.createOrReplaceTempView("news_signals_replacement_20261023")
projection = ", ".join(names)
spark.sql(
    f"INSERT OVERWRITE TABLE {TARGET} "
    f"SELECT {projection} FROM news_signals_replacement_20261023"
)

# Reconcile ALL 21 columns, not only a row count.
actual = spark.table(TARGET).select(*names)
if actual.count() != EXPECTED_COUNT \
   or actual.exceptAll(typed).limit(1).count() \
   or typed.exceptAll(actual).limit(1).count():
    raise RuntimeError(
        "Post-write validation failed. Original data are preserved in "
        f"{BACKUP}. Investigate before any further replacement."
    )
print("SUCCESS: news_signals now contains exactly 26 supplied rows.")
print("Backup:", BACKUP)
print("No other tables, Real Genie settings or Synthetic Genie settings changed.")
