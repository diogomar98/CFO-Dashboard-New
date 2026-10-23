"""ABN Real Data Genie setup configuration. No Synthetic code or tables are modified.

The only inputs are the approved UC location and the existing source CSVs.
Databricks SDK Genie creation requires an approved SQL warehouse ID supplied
through the Databricks notebook widget, never committed credentials.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from uuid import NAMESPACE_URL, uuid5

CATALOG = "frbg3s_studio_a"
SCHEMA = "cfo_cockpit"
TITLE = "ABN CFO Cockpit — Real Reported Data"
DESCRIPTION = (
    "Read-only ABN AMRO CFO analyst for reported Group profitability, capital, "
    "liquidity and historical NII/NIM; and segment loans, deposits and RWA. "
    "Sources are reviewed reporting extracts, current through Q2 2026. "
    "No synthetic values, invented figures, peers, forecasts or live feeds."
)
TABLES = (
    "cfo_group_quarterly",
    "cfo_segment_quarterly",
    "cfo_group_nii_nim_2021",
)
EXPECTED_ROWS = dict(zip(TABLES, (10, 28, 22)))
SQL_QUESTIONS = (
    "What is the most recent Group quarterly net profit?",
    "Show the latest five reported quarters of Group net interest income.",
    "How did the Group CET1 ratio move from Q1 to Q2 2026?",
    "What are reported loans, deposits and RWA for Wealth Management?",
    "Compare the business lines in the most recent reported quarter.",
    "How did Group net interest income and net interest margin change from 2022 to 2023?",
    "What are the latest available Group liquidity ratios?",
    "Show quarterly Group profitability trends since 2025.",
    "Compare reported Group CET1 and Group RWA in Q2 2026.",
    "What metrics are available for Personal & Business Banking?",
)
INSTRUCTIONS = """You are the ABN AMRO CFO Real Reported Data analyst. Answer in concise financial language.

SOURCES AND SCOPE
- Use ONLY the three attached certified reporting tables in frbg3s_studio_a.cfo_cockpit.
- These are reported/extracted facts, not synthetic data or live core-bank operational data.
- Data ends Q2 2026. 'date' is the financial quarter-end; use MAX(date) for the latest value.
- Group income statement data start Q1 2024; Group balance sheet, capital and liquidity start Q4 2024.
- Group NII/NIM history starts Q1 2021 in cfo_group_nii_nim_2021.
- Segment data run Q4 2024–Q2 2026 and have four exact business-line values:
  Personal & Business Banking, Corporate Banking, Wealth Management, Group Functions.
- Segment sources contain ONLY loans_m, deposits_m and rwa_m. No segment NII, NIM,
  net profit, CET1 or LCR is supplied. Never substitute Group figures for missing segment data.
- Never join Group metrics to each segment and then sum duplicated Group values.
  Group Functions may have negative adjustments. Do not derive Group totals from
  segments without independently verified reconciliation.

METRIC DEFINITIONS
- _m means EUR millions; _pct is a percentage already on the 0–100 scale;
  _bps means basis points. Do not multiply percentage values by 100.
- P&L metrics are quarter flows. Loans, RWA, deposits, assets and CET1 capital are
  quarter-end stocks; don't sum balance sheet stocks across quarters.
- A full-year Group income figure may be summed from four complete quarterly flows,
  but explicitly name the periods included.
- Comparisons of percentage ratios are percentage-point movements; NIM is in basis points.
- Preserve negative values and NULL as reported. Missing data is not zero.

ANALYSIS AND ANSWER QUALITY
- All numerical answers must follow returned SQL evidence from the attached tables.
- Provide periods, reporting scope, units and a clear supporting calculation when relevant.
- When asked WHY something changed, distinguish measured movement from business causes.
  Without contemporaneous source commentary, do not invent causality, management actions,
  forecasts, peer comparisons, regulatory thresholds, interest-rate betas or stress effects.
- Historical source_url in cfo_group_nii_nim_2021 identifies the source factsheet.
- Never assert monthly, daily, live or future numbers.
- When an answer is unsupported, say exactly what data is unavailable.
- Produce read-only SQL only (SELECT or WITH). Never alter, write, or delete tables.
"""


def _id(label: str) -> str:
    return uuid5(NAMESPACE_URL, "abn-cfo-real-genie/" + label).hex


def trusted_sql_examples(repo_root: Path) -> list[dict]:
    """Parse exactly the 10 source-controlled, single-statement SELECT examples."""
    source = (repo_root / "setup" / "real_genie_trusted_queries.sql").read_text(
        encoding="utf-8"
    )
    chunks = re.split(r"(?m)^-- EXAMPLE (\d+)\.[^\n]*\n", source)
    examples = {}
    for index in range(1, len(chunks), 2):
        number = int(chunks[index])
        uncommented = "\n".join(
            line for line in chunks[index + 1].splitlines()
            if line.strip() and not line.lstrip().startswith("--")
        ).strip()
        uncommented = uncommented.replace(
            "REPLACE_CATALOG.REPLACE_SCHEMA", f"{CATALOG}.{SCHEMA}"
        ).rstrip(";").strip()
        if not re.match(r"(?is)^SELECT\b", uncommented):
            raise ValueError(f"Genie example {number} isn't a SELECT query")
        if ";" in uncommented:
            raise ValueError(f"Genie example {number} must contain one query")
        examples[number] = uncommented
    if sorted(examples) != list(range(1, 11)):
        raise ValueError("Ten trusted Genie SQL examples are required")
    for sql in examples.values():
        if "REPLACE_CATALOG" in sql:
            raise ValueError("Genie example still has an unreplaced catalog")
    return [
        {
            "id": _id(f"example-{i}"),
            "question": [SQL_QUESTIONS[i - 1]],
            "sql": [examples[i]],
        }
        for i in range(1, 11)
    ]


def genie_serialized_space(repo_root: Path) -> str:
    """Create a v2 Genie Agent with sources, instructions and ten SQL examples."""
    example_queries = trusted_sql_examples(repo_root)
    data = {
        "version": 2,
        "config": {
            "sample_questions": [
                {"id": _id(f"sample-{i}"), "question": [question]}
                for i, question in enumerate(SQL_QUESTIONS[:5], start=1)
            ]
        },
        "data_sources": {
            "tables": [
                {"identifier": f"{CATALOG}.{SCHEMA}.{name}"}
                for name in TABLES
            ]
        },
        "instructions": {
            "text_instructions": [{
                "id": _id("finance-instructions"),
                "content": [INSTRUCTIONS],
            }],
            "example_question_sqls": example_queries,
        },
    }
    return json.dumps(data, ensure_ascii=False)


def validate_existing_tables(spark, repo_root: Path) -> dict:
    """Create only if all are absent; verify ALL source values if already present."""
    import pandas as pd
    from setup.real_genie_uc_setup import _load, prepare_source_tables

    existing = {
        name: spark.catalog.tableExists(f"{CATALOG}.{SCHEMA}.{name}")
        for name in TABLES
    }
    if any(existing.values()) and not all(existing.values()):
        raise RuntimeError(
            "Only some Real Genie tables exist. Inspect the partial setup "
            "and finish it manually; no existing object will be overwritten."
        )
    if not any(existing.values()):
        return prepare_source_tables(
            spark,
            catalog=CATALOG,
            schema=SCHEMA,
            source_dir=str(repo_root / "data"),
        )

    for name in TABLES:
        expected = _load(name, repo_root / "data")
        actual = spark.table(f"{CATALOG}.{SCHEMA}.{name}").toPandas()
        if list(actual.columns) != list(expected.columns):
            raise RuntimeError(f"{name} differs from the reviewed CSV columns")
        if len(actual) != EXPECTED_ROWS[name]:
            raise RuntimeError(f"{name} has a different row count")
        actual["date"] = pd.to_datetime(actual["date"]).dt.strftime("%Y-%m-%d")
        keys = ["date", "business_line"] if name == "cfo_segment_quarterly" else ["date"]
        expected = expected.sort_values(keys).reset_index(drop=True)
        actual = actual.sort_values(keys).reset_index(drop=True)
        try:
            pd.testing.assert_frame_equal(
                expected, actual, check_dtype=False, check_exact=False,
                rtol=1e-10, atol=1e-8,
            )
        except AssertionError as exc:
            raise RuntimeError(
                f"{name} doesn't match the source CSV: refusing to modify "
                "an existing table."
            ) from exc
    return {
        name: {"table": f"{CATALOG}.{SCHEMA}.{name}", "rows": EXPECTED_ROWS[name],
               "status": "verified existing"}
        for name in TABLES
    }


def create_or_reuse_agent(workspace_client, warehouse_id: str, repo_root: Path) -> str:
    """Never silently retarget a preexisting Agent or overwrite its instructions."""
    if not warehouse_id or not warehouse_id.strip():
        raise ValueError("An approved SQL warehouse ID is required")
    intended = {f"{CATALOG}.{SCHEMA}.{table}" for table in TABLES}

    next_page = None
    matches = []
    while True:
        page = workspace_client.genie.list_spaces(
            page_size=100, page_token=next_page
        )
        matches.extend(
            space for space in (getattr(page, "spaces", None) or [])
            if getattr(space, "title", None) == TITLE
        )
        next_page = getattr(page, "next_page_token", None)
        if not next_page:
            break

    if len(matches) > 1:
        raise RuntimeError("Multiple Real Genie spaces have this name; review them manually")
    if matches:
        space_id = matches[0].space_id
        # Requires CAN EDIT. Fail closed rather than reusing an unrelated agent.
        existing = workspace_client.genie.get_space(
            space_id=space_id, include_serialized_space=True
        )
        if not getattr(existing, "serialized_space", None):
            raise RuntimeError("Cannot inspect existing Real Genie agent's sources")
        saved = json.loads(existing.serialized_space)
        configured = {
            table["identifier"]
            for table in saved.get("data_sources", {}).get("tables", [])
        }
        if configured != intended:
            raise RuntimeError(
                "Existing Real Genie agent sources differ from approved tables; "
                "no agent was modified."
            )
        if getattr(existing, "warehouse_id", None) != warehouse_id.strip():
            raise RuntimeError(
                "Existing Real Genie agent uses a different SQL warehouse; "
                "inspect it before linking the App."
            )
        return space_id

    space = workspace_client.genie.create_space(
        warehouse_id=warehouse_id.strip(),
        title=TITLE,
        description=DESCRIPTION,
        serialized_space=genie_serialized_space(repo_root),
    )
    return space.space_id
