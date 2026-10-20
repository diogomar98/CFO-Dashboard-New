"""Factsheet-only quarterly CFO view. No synthetic observations or model assumptions."""
from pathlib import Path
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
GROUP_PATH = ROOT / "data" / "abn_quarterly.csv"
SEGMENT_PATH = ROOT / "data" / "abn_segments_quarterly.csv"
SOURCE = "ABN AMRO Q2 2026 factsheet · unaudited · consolidated and segment disclosures"
SEGMENTS = ["Group", "Personal & Business Banking", "Wealth Management", "Corporate Banking", "Group Functions"]

@st.cache_data
def _load_reported():
    group = pd.read_csv(GROUP_PATH, parse_dates=["date"]).sort_values("date")
    segment = pd.read_csv(SEGMENT_PATH, parse_dates=["date"]).sort_values(["date", "business_line"])
    for metric in ("loans_m", "deposits_m", "rwa_m"):
        totals = segment.groupby("date")[metric].sum()
        actual = group.set_index("date").loc[totals.index, metric]
        if not ((totals - actual).abs() < 0.01).all():
            raise ValueError(f"Segment {metric} does not reconcile to the factsheet group amount.")
    return group, segment

def _label_date(date):
    date = pd.Timestamp(date)
    return f"Q{date.quarter} {date.year}"

def _amount(value):
    return "Not disclosed" if pd.isna(value) else f"€{value:,.0f}m"

def _percent(value):
    return "Not disclosed" if pd.isna(value) else f"{value:,.2f}%"

def _quarterly_delta(current, previous, percentage=False):
    if previous is None or pd.isna(current) or pd.isna(previous):
        return None
    delta = current - previous
    return f"{delta:+.2f} pp QoQ" if percentage else f"{delta:+,.0f}m QoQ"

def _tile(name, value, previous=None, percentage=False):
    displayed = _percent(value) if percentage else _amount(value)
    delta = _quarterly_delta(value, previous, percentage)
    st.metric(name, displayed, delta=delta, delta_color="off")

def _series(frame, metrics):
    selected = frame.set_index("date")[metrics].apply(pd.to_numeric, errors="coerce")
    if selected.dropna(how="all").empty:
        st.info("No reported observations for this period.")
    else:
        st.line_chart(selected, use_container_width=True)

def _snapshot(frame, columns):
    values = frame[["date"] + columns].copy().sort_values("date", ascending=False)
    values["date"] = values["date"].map(_label_date)
    st.dataframe(values.rename(columns={"date": "Quarter"}), hide_index=True, use_container_width=True)

def _history_stats(group, metric):
    """Only compare adjacent actual observations; no synthetic bridging."""
    valid = group.dropna(subset=[metric]).sort_values("date")
    if valid.empty:
        return float("nan"), None
    return float(valid.iloc[-1][metric]), (float(valid.iloc[-2][metric]) if len(valid) > 1 else None)

def render_reported_dashboard():
    """Return False only if no reported dataset is installed."""
    if not GROUP_PATH.is_file() or not SEGMENT_PATH.is_file():
        return False
    try:
        group, segments = _load_reported()
    except Exception as error:
        st.error(f"ABN AMRO reported data could not be validated: {error}")
        st.stop()
    latest = group.iloc[-1]
    latest_date = latest["date"]
    st.markdown("""
    <style>
      .stApp {background: radial-gradient(ellipse at 55% 5%, #14281f 0%, #080f0d 63%, #080f0d 100%); color: #e7f4ec;}
      h1, h2, h3 {letter-spacing:-0.035em;}
      div[data-testid="stMetric"] {background:rgba(17,35,28,.82);border:1px solid #315442;padding:18px;border-radius:4px;}
      div[data-testid="stMetricLabel"] {color:#b5c9bd;}
      .stCaption {color:#b5c9bd;}
    </style>
    """, unsafe_allow_html=True)
    st.caption("A.R.C. / CFO COMMAND CENTER — REPORTED ACTUALS")
    st.title("ABN AMRO | Quarterly CFO Cockpit")
    st.caption(f"Latest financial close: {_label_date(latest_date)} · {latest_date:%d %B %Y} · Quarterly reported data, not live / daily data")
    st.caption(SOURCE)

    division = st.selectbox("Reporting scope", SEGMENTS, index=0)
    page = st.radio("Explore", ["Executive overview", "Earnings", "Balance sheet & capital", "Business segments", "Data quality & scope"], horizontal=True)
    if division != "Group" and page != "Business segments":
        st.info(f"Selected: {division}. Earnings and group capital disclosures shown below are GROUP data. Open Business segments for segment-specific loans, deposits and RWA.")

    if page == "Executive overview":
        st.subheader("Executive position")
        c = st.columns(4)
        fields = [("Net profit Q2", "net_profit_m", False), ("Net interest income Q2", "nii_m", False),
                  ("CET1 ratio", "cet1_ratio_pct", True), ("Cost / income ratio", "cost_income_ratio_pct", True)]
        for column, (label, metric, pct) in zip(c, fields):
            now, before = _history_stats(group, metric)
            with column: _tile(label, now, before, pct)
        c = st.columns(4)
        for column, (label, metric, pct) in zip(c, [
            ("Customer loans", "loans_m", False), ("Customer deposits", "deposits_m", False),
            ("LCR", "lcr_pct", True), ("Total assets", "total_assets_m", False)]):
            now, before = _history_stats(group, metric)
            with column: _tile(label, now, before, pct)
        st.subheader("Profitability over reported quarters")
        _series(group, ["net_profit_m", "nii_m"])
        st.caption("P&L metrics are flows for each quarter; balance-sheet and regulatory metrics are quarter-end values. QoQ compares adjacent reported quarters.")
    elif page == "Earnings":
        st.subheader("Quarterly income statement")
        c = st.columns(4)
        for column, (label, metric, pct) in zip(c, [
            ("NII", "nii_m", False), ("Net fee income", "net_fee_income_m", False),
            ("Operating income", "operating_income_m", False), ("Net profit", "net_profit_m", False)]):
            now, before = _history_stats(group, metric)
            with column: _tile(label, now, before, pct)
        st.caption("The net interest margin is reported directly by ABN AMRO in basis points; it is not estimated from total loans.")
        st.metric("Reported NIM", f"{latest['nim_bps']:.1f} bps", f"{latest['nim_bps'] - group.iloc[-2]['nim_bps']:+.1f} bps QoQ", delta_color="off")
        st.subheader("Income and costs (€m)")
        _series(group, ["operating_income_m", "operating_expenses_m", "net_profit_m"])
        _snapshot(group, ["nii_m", "net_fee_income_m", "operating_income_m", "operating_expenses_m", "impairment_charges_m", "net_profit_m", "nim_bps", "roe_pct", "cost_income_ratio_pct"])
    elif page == "Balance sheet & capital":
        st.subheader("Balance sheet and regulatory capital")
        c = st.columns(4)
        for column, (label, metric, pct) in zip(c, [
            ("Loans", "loans_m", False), ("Deposits", "deposits_m", False),
            ("RWA", "rwa_m", False), ("CET1", "cet1_ratio_pct", True)]):
            now, before = _history_stats(group, metric)
            with column: _tile(label, now, before, pct)
        st.subheader("Reported balances (€m)")
        _series(group, ["loans_m", "deposits_m", "rwa_m"])
        st.subheader("Reported ratios (%)")
        _series(group, ["cet1_ratio_pct", "lcr_pct", "nsfr_pct"])
        _snapshot(group, ["total_assets_m", "financial_investments_m", "loans_m", "deposits_m", "rwa_m", "cet1_capital_m", "cet1_ratio_pct", "lcr_pct", "nsfr_pct"])
        st.info("Treasury sensitivities, position-level duration and hedges are unavailable from the uploaded factsheet. Financial investments are a consolidated balance-sheet aggregate, not a trading-book position list.")
    elif page == "Business segments":
        st.subheader("Segment-level balance sheet")
        st.caption("The source contains three business segments plus Group Functions. Group Functions includes consolidation / reconciliation adjustments, which can be negative.")
        records = segments if division == "Group" else segments[segments["business_line"] == division]
        latest_segment = records[records["date"] == latest_date]
        st.dataframe(latest_segment.rename(columns={"date":"As of", "business_line":"Business line"}), hide_index=True, use_container_width=True)
        metric = st.selectbox("Reported metric (€m)", ["loans_m", "deposits_m", "rwa_m"], format_func=lambda x: {"loans_m":"Customer loans", "deposits_m":"Customer deposits", "rwa_m":"Risk weighted assets"}[x])
        pivot = records.pivot(index="date", columns="business_line", values=metric).sort_index()
        st.line_chart(pivot, use_container_width=True)
        st.caption("Segment values are taken from factsheet disclosures and reconcile to Group. No country/product or IFRS 9 stage allocations have been invented.")
    else:
        st.subheader("Provenance and unavailable datasets")
        st.success(f"Reported series: {len(group)} quarterly P&L observations, {group['loans_m'].notna().sum()} quarter-end balance-sheet observations.")
        st.write("Source: ABN AMRO Q2 2026 factsheet. Quarterly P&L dates Q1 2024–Q2 2026; consolidated balance sheets Q4 2024–Q2 2026. All monetary figures are €m unless stated.")
        st.write("Not populated: daily and monthly actuals; ECB daily rate; product-level yields; country allocations; daily credit/deposit signals; IFRS 9 stage splits; securities-level treasury DV01 and hedges; model scenarios and forecasts.")
        st.write("Peers, public news and strategy are outside the reported-data migration, so they are not displayed as verified ABN internal observations.")
        st.warning("Synthetic legacy views have been bypassed in reported mode to avoid false 'live', MoM and certified forecast labels.")
    return True
