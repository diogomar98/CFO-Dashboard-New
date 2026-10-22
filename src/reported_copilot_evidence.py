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
SEGMENT_TOPICS = {
    "Balance sheet": (
        ("loans_m", "Segment customer loans", "EUR millions"),
        ("deposits_m", "Segment customer deposits", "EUR millions"),
        ("rwa_m", "Segment risk-weighted assets", "EUR millions"),
    ),
}
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
    return {
        "kind": "reported_actuals",
        "data_mode": "real",
        "topic": topic,
        "scope": str(scope) if scope else "ABN AMRO Group",
        "as_of": _quarter(latest["date"]),
        "source": source,
        "metrics": metrics,
        "notes": notes,
        "llm_enabled": False,
    }
