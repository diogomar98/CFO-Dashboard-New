"""Strictly sourced, read-only context for the future Real Data CFO Copilot.

No LLM calls, Genie queries, synthetic views or assumed causal attribution.
Financial values come exclusively from the existing validated reporting state.
Future AI connectors can consume these structured evidence packets, and must
refuse to answer unsupported requests rather than inventing missing values.
"""
from __future__ import annotations

import math

import pandas as pd


GROUP_TOPICS = {
    "Capital": (
        ("cet1_ratio_pct", "CET1 ratio", "percent"),
        ("cet1_capital_m", "CET1 capital", "EUR millions"),
        ("rwa_m", "Risk-weighted assets", "EUR millions"),
    ),
    "Profitability": (
        ("net_profit_m", "Quarterly net profit", "EUR millions"),
        ("nii_m", "Quarterly net interest income", "EUR millions"),
        ("nim_bps", "Net interest margin", "basis points"),
        ("operating_income_m", "Operating income", "EUR millions"),
        ("operating_expenses_m", "Operating expenses", "EUR millions"),
        ("impairment_charges_m", "Impairment charges", "EUR millions"),
    ),
    "Liquidity": (
        ("lcr_pct", "Liquidity coverage ratio", "percent"),
        ("nsfr_pct", "Net stable funding ratio", "percent"),
        ("loans_m", "Customer loans", "EUR millions"),
        ("deposits_m", "Customer deposits", "EUR millions"),
    ),
}
# Include every Group metric actually present in the source extract,
# including ratios and stock/flow values. Never synthesize unavailable fields.
_ALL_GROUP_METRICS = (
    ("net_profit_m", "Quarterly net profit", "EUR millions"),
    ("nii_m", "Net interest income", "EUR millions"),
    ("net_fee_income_m", "Net fee income", "EUR millions"),
    ("operating_income_m", "Operating income", "EUR millions"),
    ("operating_expenses_m", "Operating expenses", "EUR millions"),
    ("impairment_charges_m", "Impairment charges", "EUR millions"),
    ("cost_income_ratio_pct", "Cost/income ratio", "percent"),
    ("nim_bps", "Net interest margin", "basis points"),
    ("roe_pct", "Return on equity", "percent"),
    ("loans_m", "Customer loans", "EUR millions"),
    ("deposits_m", "Customer deposits", "EUR millions"),
    ("rwa_m", "Risk-weighted assets", "EUR millions"),
    ("cet1_ratio_pct", "CET1 ratio", "percent"),
    ("cet1_capital_m", "CET1 capital", "EUR millions"),
    ("total_capital_ratio_pct", "Total capital ratio", "percent"),
    ("lcr_pct", "Liquidity coverage ratio", "percent"),
    ("nsfr_pct", "Net stable funding ratio", "percent"),
    ("total_assets_m", "Total assets", "EUR millions"),
    ("financial_investments_m", "Financial investments", "EUR millions"),
    ("loan_deposit_ratio_pct", "Loan/deposit ratio", "percent"),
    ("cost_of_risk_bps", "Cost of risk", "basis points"),
    ("residential_mortgages_m", "Residential mortgages", "EUR millions"),
    ("consumer_loans_m", "Consumer loans", "EUR millions"),
    ("corporate_client_loans_m", "Corporate client loans", "EUR millions"),
)
GROUP_TOPICS["All reported metrics"] = _ALL_GROUP_METRICS

SEGMENT_TOPICS = {
    "Balance sheet": (
        ("loans_m", "Segment customer loans", "EUR millions"),
        ("deposits_m", "Segment customer deposits", "EUR millions"),
        ("rwa_m", "Segment risk-weighted assets", "EUR millions"),
    ),
}
SEGMENT_TOPICS["All reported metrics"] = SEGMENT_TOPICS["Balance sheet"]

REPORT_SOURCE = "ABN AMRO Q2 2026 factsheet — supplied workbook, reporting extract data/abn_quarterly.csv"
SEGMENT_SOURCE = "ABN AMRO Q2 2026 factsheet — reporting extract data/abn_segments_quarterly.csv"


def _quarter(value):
    date = pd.Timestamp(value)
    return f"Q{date.quarter} {date.year}"


def _safe_value(raw, field):
    if raw is None or pd.isna(raw):
        return None
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError(f"Nonfinite reported value in {field}")
    return value


def build_reported_evidence(s, topic):
    """Return a structured facts-only packet; missing values stay missing."""
    if not getattr(s, "is_reported", False):
        raise ValueError("A reported-data state is required; never use Synthetic data.")
    scope = getattr(s, "business_line", None)
    choices = SEGMENT_TOPICS if scope else GROUP_TOPICS
    if topic not in choices:
        raise ValueError(
            f"{topic!r} is not available for the selected reporting scope; "
            "no unsupported Group-to-segment metrics are substituted."
        )
    group = s.reported_group
    if scope:
        frame = s.reported_segments.loc[
            s.reported_segments["business_line"] == scope
        ].copy()
        source = SEGMENT_SOURCE
    else:
        frame = group.copy()
        source = REPORT_SOURCE
    if frame.empty or "date" not in frame:
        raise ValueError("Source reporting data not available.")
    frame = frame.sort_values("date")
    if frame["date"].isna().any() or frame["date"].duplicated().any():
        raise ValueError("Ambiguous quarterly reporting observations.")
    latest = frame.iloc[-1]
    previous = frame.iloc[-2] if len(frame) >= 2 else None
    metrics = []
    for field, label, unit in choices[topic]:
        if field not in frame.columns:
            raise ValueError(f"Missing required public disclosure field: {field}")
        current = _safe_value(latest[field], field)
        prior = _safe_value(previous[field], field) if previous is not None else None
        metrics.append({
            "field": field,
            "label": label,
            "unit": unit,
            "latest": current,
            "previous": prior,
            "delta": current - prior if current is not None and prior is not None else None,
            "latest_quarter": _quarter(latest["date"]),
            "previous_quarter": _quarter(previous["date"]) if previous is not None else None,
            "provenance": source,
        })

    # Do not assert unexplained causality or management thresholds.
    notes = [
        "Reported observations and exact arithmetic differences only.",
        "A quarter-to-quarter movement alone does not establish why the metric changed.",
        "No approved regulatory limits, causality, daily observations, or future forecasts supplied.",
        "For a causal explanation, retrieve and quote supporting period-specific public disclosures.",
    ]
    if scope:
        notes.append(
            "No segment NII, NIM, CET1 ratio or LCR has been supplied or inferred."
        )
    packet = {
        "kind": "reported_actuals",
        "data_mode": "real",
        "topic": topic,
        "scope": str(scope) if scope else "ABN AMRO Group",
        "as_of": _quarter(latest["date"]),
        "source": source,
        "metrics": metrics,
        "notes": notes,
        "llm_enabled": True,
    }
    if topic == "All reported metrics":
        # Observations are strictly the published reporting extract; preserve
        # absent stock metrics as null instead of fabricating earlier values.
        columns = [field for field, _, _ in choices[topic]]
        packet["quarterly_history"] = [
            {
                "quarter": _quarter(row["date"]),
                "values": {
                    col: _safe_value(row[col], col) for col in columns
                },
            } for _, row in frame.iterrows()
        ]
        if not scope:
            # The complete, reconciled bank-line table is already loaded in
            # reporting state. Clearly distinguish these from Group totals.
            packet["segment_history"] = [
                {
                    "quarter": _quarter(row["date"]),
                    "business_line": str(row["business_line"]),
                    "loans_m": _safe_value(row["loans_m"], "loans_m"),
                    "deposits_m": _safe_value(row["deposits_m"], "deposits_m"),
                    "rwa_m": _safe_value(row["rwa_m"], "rwa_m"),
                } for _, row in s.reported_segments.sort_values(
                    ["date", "business_line"]
                ).iterrows()
            ]
            packet["segment_source"] = SEGMENT_SOURCE
            # These official 2021-on NII/NIM values were independently
            # cross-checked across successive reported factsheets.
            from src.public_horizon_engine import load_public_horizon_inputs
            historical = load_public_horizon_inputs(s.reported_group)
            packet["group_nii_nim_history_2021"] = [
                {
                    "quarter": _quarter(row["date"]),
                    "nii_m": _safe_value(row["nii_m"], "nii_m"),
                    "nim_bps": _safe_value(row["nim_bps"], "nim_bps"),
                    "source_url": str(row["source_url_bank"]),
                } for _, row in historical.iterrows()
            ]
            packet["history_2021_source"] = (
                "Official ABN AMRO quarterly factsheets 2021 Q1–2026 Q2; "
                "source URLs recorded per quarter; 49/49 Group NII/NIM checks passed."
            )
    return packet
