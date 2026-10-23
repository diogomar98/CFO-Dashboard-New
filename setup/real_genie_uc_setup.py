"""One-time Databricks notebook cell: publish ACTUAL source extracts into UC.

BEFORE RUNNING in ABN:
  1. Put only the three validated Real Data CSVs from the existing project in
     a driver-visible approved location (workspace file or UC Volume).
  2. Set REAL_GENIE_CATALOG, REAL_GENIE_SCHEMA, REAL_GENIE_SOURCE_DIR.
  3. Execute in an approved notebook attached to your allowed SQL/compute.
  4. Inspect reconciliation output; attach three resulting UC tables to a NEW
     Real Genie Agent. Leave the Synthetic Genie Agent untouched.

FAIL CLOSED: not a scheduled job; no overwrite/merge/replace of UC objects,
no Synthetic files, no privileged grants, no live ABN system connections.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import os
import re

import pandas as pd

SOURCE_NAMES = {
    "cfo_group_quarterly": "abn_quarterly.csv",
    "cfo_segment_quarterly": "abn_segments_quarterly.csv",
    "cfo_group_nii_nim_2021": "abn_group_nii_nim_2021_public.csv",
}
EXPECTED_ROWS = {
    "cfo_group_quarterly":10,
    "cfo_segment_quarterly":28,
    "cfo_group_nii_nim_2021":22,
}
GROUP_FIELDS = (
    "nii_m", "net_fee_income_m", "operating_income_m",
    "operating_expenses_m", "impairment_charges_m", "net_profit_m",
    "cost_income_ratio_pct", "nim_bps", "roe_pct", "loans_m",
    "deposits_m", "rwa_m", "cet1_ratio_pct", "lcr_pct",
    "nsfr_pct", "total_assets_m", "financial_investments_m",
    "loan_deposit_ratio_pct", "cet1_capital_m",
    "total_capital_ratio_pct", "cost_of_risk_bps",
    "residential_mortgages_m", "consumer_loans_m",
    "corporate_client_loans_m",
)
SEGMENT_FIELDS = ("loans_m","deposits_m","rwa_m")
HISTORY_FIELDS = (
    "nii_m","nim_bps","nii_cell","nim_cell",
    "source_url","review_status",
)
COLUMN_HELP = {
    "date":"Published financial quarter-end, not daily data; values denote the reporting quarter.",
    "business_line":"As-reported ABN business line; exact values: Personal & Business Banking, Corporate Banking, Wealth Management, Group Functions.",
    "nii_m":"Quarterly net interest income (EUR millions), not annualised.",
    "nim_bps":"Net interest margin in basis points; 100 basis points = one percentage point.",
    "net_fee_income_m":"Quarterly net fee income in EUR millions.",
    "operating_income_m":"Quarterly operating income in EUR millions.",
    "operating_expenses_m":"Quarterly operating expenses in EUR millions.",
    "impairment_charges_m":"Quarterly impairment charges in EUR millions; preserve negative values.",
    "net_profit_m":"Quarterly Group net profit in EUR millions.",
    "cost_income_ratio_pct":"Published cost-to-income ratio in PERCENT units (e.g. 58.2 means 58.2%).",
    "roe_pct":"Published Group return on equity percentage; not necessarily comparable to peer RoTE.",
    "loans_m":"Reported quarter-end customer-loan balance (EUR millions). Group Functions adjustments may be negative.",
    "deposits_m":"Reported quarter-end customer-deposit balance (EUR millions).",
    "rwa_m":"Reported quarter-end risk-weighted assets in EUR millions.",
    "cet1_ratio_pct":"Published CET1 ratio in PERCENT units, not a decimal fraction.",
    "cet1_capital_m":"Published CET1 regulatory capital in EUR millions.",
    "total_capital_ratio_pct":"Published total capital ratio in PERCENT units.",
    "lcr_pct":"Published liquidity coverage ratio in PERCENT units.",
    "nsfr_pct":"Published net stable funding ratio in PERCENT units.",
    "total_assets_m":"Reported quarter-end total assets in EUR millions.",
    "financial_investments_m":"Reported financial investments in EUR millions.",
    "loan_deposit_ratio_pct":"Published loan/deposit ratio in PERCENT units.",
    "cost_of_risk_bps":"Published cost of risk in basis points; do not reinterpret as percentages.",
    "residential_mortgages_m":"Published residential mortgage loans in EUR millions.",
    "consumer_loans_m":"Published consumer loans in EUR millions.",
    "corporate_client_loans_m":"Published corporate client loans in EUR millions.",
    "nii_cell":"Workbook cell coordinates for historical NII provenance.",
    "nim_cell":"Workbook cell coordinates for historical NIM provenance.",
    "source_url":"Verified public source factsheet URL for this historical quarter.",
    "review_status":"Description of previously completed source verification.",
}


def _identifier(value,name):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",value or ""):
        raise ValueError(
            f"{name} must be an explicit allowed Unity Catalog identifier. "
            "Use REAL_GENIE_CATALOG and REAL_GENIE_SCHEMA environment variables."
        )
    return value


def _load(name,source_dir):
    src=Path(source_dir) / SOURCE_NAMES[name]
    if not src.is_file():
        raise FileNotFoundError("Real reporting CSV not found: "+str(src))
    df=pd.read_csv(src,dtype={"business_line":str})
    expected={
        "cfo_group_quarterly":["date",*GROUP_FIELDS],
        "cfo_segment_quarterly":["date","business_line",*SEGMENT_FIELDS],
        "cfo_group_nii_nim_2021":["date",*HISTORY_FIELDS],
    }[name]
    if list(df.columns)!=expected:
        raise ValueError(f"{name}: exact CSV columns/order do not match the validated source.")
    if len(df)!=EXPECTED_ROWS[name]:
        raise ValueError(f"{name}: unexpected historical reporting row count.")
    if df["date"].isna().any() or df["date"].duplicated().any() and name!="cfo_segment_quarterly":
        raise ValueError(f"{name}: missing or duplicated reporting period.")
    if name=="cfo_segment_quarterly":
        allowed={
            "Corporate Banking","Group Functions",
            "Personal & Business Banking","Wealth Management",
        }
        if set(df.business_line)!=allowed or df[["date","business_line"]].duplicated().any():
            raise ValueError("Segment labels or quarter/business-line keys do not reconcile.")
    if name=="cfo_group_nii_nim_2021":
        if not df["source_url"].str.startswith("https://assets.ctfassets.net/").all():
            raise ValueError("Historical NII/NIM source URL does not match approved public publisher.")
        if df[["nii_m","nim_bps"]].isna().any().any():
            raise ValueError("Historical 2021-on NII/NIM has a missing reported observation.")
    if df["date"].min() != ("2021-03-31" if name=="cfo_group_nii_nim_2021"
                            else "2024-03-31" if name=="cfo_group_quarterly"
                            else "2024-12-31"):
        raise ValueError("Source quarterly range starts on the wrong date.")
    if df["date"].max()!="2026-06-30":
        raise ValueError("Dataset contains an unexpected reporting cutoff.")
    return df


def _schema(name):
    # Keep source validation usable outside Databricks (e.g. CI) without Spark.
    from pyspark.sql.types import (
        DateType, DoubleType, StringType, StructField, StructType,
    )
    fields=[StructField("date",DateType(),False)]
    if name=="cfo_segment_quarterly":
        fields.append(StructField("business_line",StringType(),False))
        metrics=SEGMENT_FIELDS
    elif name=="cfo_group_quarterly":
        metrics=GROUP_FIELDS
    else:
        metrics=("nii_m","nim_bps")
    fields.extend(StructField(key,DoubleType(),True) for key in metrics)
    if name=="cfo_group_nii_nim_2021":
        fields.extend(StructField(key,StringType(),True) for key in HISTORY_FIELDS[2:])
    return StructType(fields)


def _to_rows(name,frame):
    fields=[f.name for f in _schema(name)]
    for _,row in frame.iterrows():
        record=[]
        for key in fields:
            value=row[key]
            if key=="date":
                record.append(date.fromisoformat(str(value)))
            elif pd.isna(value):
                record.append(None)
            elif key=="business_line" or key in HISTORY_FIELDS[2:]:
                record.append(str(value))
            else:
                record.append(float(value))
        yield tuple(record)


def prepare_source_tables(spark, *,catalog, schema,source_dir):
    """Create only new managed UC tables; refuse to overwrite ANY prior assets."""
    catalog=_identifier(catalog,"REAL_GENIE_CATALOG")
    schema=_identifier(schema,"REAL_GENIE_SCHEMA")
    if not source_dir:
        raise ValueError("Provide REAL_GENIE_SOURCE_DIR for the validated project CSVs.")
    full=f"`{catalog}`.`{schema}`"
    prepared={name:_load(name,source_dir) for name in SOURCE_NAMES}
    result={}
    for name,frame in prepared.items():
        target=f"{full}.`{name}`"
        if spark.catalog.tableExists(f"{catalog}.{schema}.{name}"):
            raise FileExistsError(
                f"{target} already exists. Review it before any explicit refresh."
            )
        source=spark.createDataFrame(
            list(_to_rows(name,frame)),schema=_schema(name),
        )
        # Spark Connect compatibility: saveAsTable defaults to fail-if-table-exists.
        # The explicit tableExists check above additionally prevents rewrites.
        source.write.saveAsTable(target)
        # These comments are source metadata to help Genie generate correct SQL.
        description={
            "cfo_group_quarterly":"ABN AMRO published Group 2024 Q1–2026 Q2 quarterly actuals; P&L fields are flows, balance-sheet/capital/liquidity fields are quarter-end stocks or ratios. Null means not disclosed.",
            "cfo_segment_quarterly":"ABN AMRO published quarter-end loans, deposits and RWA for four business lines in 2024 Q4–2026 Q2; no segment NIM, NII, profit or CET1 ratio.",
            "cfo_group_nii_nim_2021":"Independently reconciled public ABN AMRO Group NII and NIM each quarter 2021 Q1–2026 Q2, with source factsheet link and workbook-cell provenance.",
        }[name]
        spark.sql("COMMENT ON TABLE "+target+" IS '"+description.replace("'","''")+"'")
        for col in _schema(name).fieldNames():
            comment=COLUMN_HELP[col].replace("'","''")
            spark.sql(f"ALTER TABLE {target} ALTER COLUMN `{col}` COMMENT '{comment}'")
        count=spark.table(target).count()
        if count!=len(frame):
            raise RuntimeError(f"{target}: published row count changed after copy")
        result[name]={"table":f"{catalog}.{schema}.{name}","rows":count}
    return result


if __name__=="__main__":
    # Run this Python file in the Databricks notebook runtime with `spark`.
    # Supply environment variables using your secure workspace/job configuration.
    # Do not commit catalog/schema, private tokens or ABN warehouse credentials.
    results=prepare_source_tables(
        spark,
        catalog=os.getenv("REAL_GENIE_CATALOG",""),
        schema=os.getenv("REAL_GENIE_SCHEMA",""),
        source_dir=os.getenv("REAL_GENIE_SOURCE_DIR",""),
    )
    for key,item in results.items():
        print(key,item["table"],"rows:",item["rows"])
