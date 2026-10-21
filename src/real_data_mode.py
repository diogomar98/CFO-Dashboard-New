"""Factsheet-backed quarterly state and modules for the existing CFO HUD.

This is deliberately isolated from the synthetic daily generators and views.
No intermediate months, daily anomalies, forward returns, or securities positions
are inferred from quarterly disclosures.
"""
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import streamlit as st

from src.rag import rag_from_status

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_SOURCE = "ABN AMRO Q2 2026 Factsheet (uploaded workbook)"
_FIELDS = ("loans_m", "deposits_m", "rwa_m")
_NEUTRAL = rag_from_status("NOT_ASSESSED", "Reported observation; no management threshold supplied")
_UNAVAILABLE = rag_from_status("UNAVAILABLE", "This analysis is not supported by the quarterly factsheet")


def _quarter(date):
    date = pd.Timestamp(date)
    return f"Q{date.quarter} {date.year}"


def _money(value):
    return "—" if pd.isna(value) else f"€{float(value):,.0f}m"


def _percent(value):
    return "—" if pd.isna(value) else f"{float(value):.2f}%"


@st.cache_data
def load_reported():
    """Read only pre-extracted, source-backed CSVs (no Excel engine required)."""
    group_file = _DATA_DIR / "abn_quarterly.csv"
    segments_file = _DATA_DIR / "abn_segments_quarterly.csv"
    if not group_file.is_file() or not segments_file.is_file():
        raise FileNotFoundError(
            "ABN AMRO quarterly reporting CSVs are missing. Synthetic mode remains available."
        )
    group = pd.read_csv(group_file, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    segment = pd.read_csv(segments_file, parse_dates=["date"]).sort_values(["date", "business_line"]).reset_index(drop=True)
    required_group = {"date", "nii_m", "net_profit_m", "nim_bps", "lcr_pct", "cet1_ratio_pct"} | set(_FIELDS)
    required_segments = {"date", "business_line"} | set(_FIELDS)
    if not required_group.issubset(group.columns) or not required_segments.issubset(segment.columns):
        raise ValueError("One of the factsheet extracts has an incompatible schema.")
    if group["date"].duplicated().any() or segment[["date", "business_line"]].duplicated().any():
        raise ValueError("The quarterly factsheet extracts contain duplicate observations.")
    for metric in _FIELDS:
        published = group.set_index("date")[metric]
        rolled = segment.groupby("date")[metric].sum()
        if (rolled.index.difference(published.index).size
                or not ((rolled - published.reindex(rolled.index)).abs() < 0.01).all()):
            raise ValueError(f"Segment-level {metric} does not reconcile to Group; refusing to display results.")
    return group, segment


def _card(label, current, previous, formatter, module, why, impact, next_action, unit):
    # Deltas are from adjacent reported quarters, never daily or monthly.
    delta = float(current - previous) if pd.notna(current) and pd.notna(previous) else 0.0
    display = formatter(current)
    movement = (
        f"{delta:+,.2f}{unit} vs prior quarter"
        if pd.notna(current) and pd.notna(previous) else "Prior-quarter comparison unavailable"
    )
    return {
        "label": label, "value": display, "delta_pp": delta, "delta_unit": unit,
        "delta_label": "QoQ" if pd.notna(previous) else "No comparison",
        "context": movement, "module": module, "rag": _NEUTRAL,
        "why": why, "impact": impact, "next": next_action,
    }


def _group_card(frame, metric, label, formatter, module, unit, description):
    available = frame.dropna(subset=[metric])
    latest = available.iloc[-1] if not available.empty else None
    prev = available.iloc[-2] if len(available) >= 2 else None
    now = float(latest[metric]) if latest is not None else float("nan")
    before = float(prev[metric]) if prev is not None else float("nan")
    return _card(
        label, now, before, formatter, module,
        f"{description} is a reported ABN AMRO observation for {_quarter(latest['date']) if latest is not None else 'an unavailable period'}.",
        "Actual quarterly disclosure; no daily interpolation or fictional segment allocation.",
        "Review the source quarter and related line items in the detailed quarterly view.",
        unit,
    )


@st.cache_data
def build_reported_state(business_line=None):
    """Provide the same shell-facing state attributes as the prototype."""
    group, segments = load_reported()
    latest = group.iloc[-1]
    earlier = group.iloc[-2]
    s = SimpleNamespace()
    s.is_reported = True
    s.business_line = business_line
    s.business_line_label = business_line or "Group"
    s.reported_group = group
    s.reported_segments = segments
    s.close_date = pd.Timestamp(latest["date"]).strftime("%d %b %Y")
    s.live_date = _quarter(latest["date"]) + " reported close"
    s.previous_month_label = _quarter(earlier["date"])
    s.executive_change_count = 0
    s.cert_current_nim = float(latest["nim_bps"]) / 100.0
    s.nim_mom_bps = float(latest["nim_bps"] - earlier["nim_bps"])
    s.horizon_year_end_nim = float("nan")
    s.conf_horizon_ye_nim = {"level": "LOW", "pct": None, "basis": "No source-backed forecast"}
    s.geo_focus = None
    s.high_impact_news_count = 0
    s.treasury_rate50_text = "unavailable"
    s.conf_treasury_rate50 = None
    s.roe_peer_gap_pp = 0.0
    s.top_strategy = None
    s.conf_strategy_rank = None
    s.ratings = {
        "news_attention": _UNAVAILABLE, "treasury_rate50": _UNAVAILABLE,
        "peer_roe": _UNAVAILABLE, "strategy_top": _UNAVAILABLE,
    }

    if business_line:
        selected = segments.loc[segments["business_line"] == business_line].sort_values("date")
        if selected.empty:
            raise ValueError(f"No factsheet segment disclosures for {business_line}")
        current = selected.iloc[-1]
        previous = selected.iloc[-2] if len(selected) > 1 else None
        def bl_card(metric, title, module):
            now = float(current[metric])
            old = float(previous[metric]) if previous is not None else float("nan")
            return _card(
                title, now, old, _money, module,
                f"{title} for {business_line}: reported {_quarter(current['date'])} balance.",
                "The business-line amounts are source-reported and reconcile to Group when Group Functions are included.",
                "Compare this quarter with the preceding reported quarter in Morning Brief.", "m",
            )
        s.kpi_cards = [
            bl_card("loans_m", "CUSTOMER LOANS", "brief"),
            bl_card("deposits_m", "CUSTOMER DEPOSITS", "brief"),
            bl_card("rwa_m", "RISK-WEIGHTED ASSETS", "brief"),
        ]
        now_ld = 100.0 * float(current["loans_m"]) / float(current["deposits_m"])
        prev_ld = (100.0 * float(previous["loans_m"]) / float(previous["deposits_m"])
                   if previous is not None and previous["deposits_m"] else float("nan"))
        s.kpi_cards.append(_card(
            "LOAN / DEPOSIT RATIO", now_ld, prev_ld, _percent, "treasury",
            "Calculated from the reported segment customer loans and deposits.",
            "This is a calculated ratio, not a separately disclosed management metric.",
            "Review the underlying loans and deposits in the segment view.", "pp",
        ))
    else:
        s.kpi_cards = [
            _group_card(group, "cet1_ratio_pct", "CET1 RATIO", _percent, "brief", "pp", "CET1 ratio"),
            _group_card(group, "lcr_pct", "LIQUIDITY COVERAGE", _percent, "treasury", "pp", "Liquidity coverage ratio"),
            _group_card(group, "net_profit_m", "QUARTERLY NET PROFIT", _money, "brief", "m", "Net profit"),
            _group_card(group, "nii_m", "NET INTEREST INCOME", _money, "brief", "m", "Net interest income"),
        ]
    return s


def _chart(frame, fields):
    data = frame.set_index("date")[fields].apply(pd.to_numeric, errors="coerce").dropna(how="all")
    if data.empty:
        st.info("No reported observations for this metric.")
    else:
        st.line_chart(data, use_container_width=True)


def render_reported_module(module, s):
    """A real-data-safe renderer for the existing radial-window navigation."""
    group = s.reported_group
    segments = s.reported_segments
    latest = group.iloc[-1]
    st.caption(f"ABN AMRO reported actuals · {_quarter(latest['date'])} · Source: {_SOURCE}")
    if module == "brief":
        st.markdown("#### Quarterly financial health check")
        if s.business_line:
            selected = segments.loc[segments["business_line"] == s.business_line]
            st.write(f"Reported {s.business_line} loans, deposits and risk-weighted assets (€m).")
            _chart(selected, ["loans_m", "deposits_m", "rwa_m"])
            st.dataframe(selected.sort_values("date", ascending=False), hide_index=True, use_container_width=True)
        else:
            left, right = st.columns(2)
            with left:
                st.metric("Quarterly net profit", _money(latest["net_profit_m"]))
                st.metric("Quarterly NII", _money(latest["nii_m"]))
            with right:
                st.metric("Reported CET1", _percent(latest["cet1_ratio_pct"]))
                st.metric("Reported LCR", _percent(latest["lcr_pct"]))
            st.markdown("#### Quarterly income and profitability (€m)")
            _chart(group, ["nii_m", "net_profit_m"])
            st.markdown("#### Quarter-end balance sheet (€m)")
            _chart(group, ["loans_m", "deposits_m", "rwa_m"])
            st.dataframe(group.tail(7).sort_values("date", ascending=False), hide_index=True, use_container_width=True)
        st.caption("All changes in Real Data mode compare reported quarters (QoQ), not daily signals.")
        return

    if module == "horizon":
        st.markdown("#### Historical horizon | reported quarters")
        st.write("The actuals can be trended, but the factsheet does not provide a forecast or the daily/monthly inputs used by the synthetic Horizon engine.")
        _chart(group, ["nii_m", "net_profit_m"])
        st.info("Forward projections are not calculated until a separate, explicitly assumption-based quarterly forecasting model is implemented.")
        return

    if module == "treasury":
        st.markdown("#### Treasury | reported aggregates")
        cols = st.columns(3)
        for col, (label, field, fmt) in zip(cols, [
            ("Financial investments", "financial_investments_m", _money),
            ("LCR", "lcr_pct", _percent),
            ("NSFR", "nsfr_pct", _percent),
        ]):
            with col:
                st.metric(label, fmt(latest[field]))
        _chart(group, ["financial_investments_m"])
        st.info("Individual securities, duration, DV01, hedges and shocked portfolio valuations cannot be derived from this factsheet.")
        return

    if module == "scenario":
        st.markdown("#### What-If Engine | reporting baseline")
        st.write(f"Observed quarter-end loans: {_money(latest['loans_m'])}. Customer deposits: {_money(latest['deposits_m'])}.")
        st.info("The original scenario engine requires synthetic loan/deposit repricing rates and betas. It is intentionally not run on the reported actuals; a labelled assumptions interface can be added in a later phase.")
        return

    if module == "copilot":
        st.markdown("#### CFO Copilot | evidence controls")
        st.warning("Real-data Copilot is not yet connected. It will not query the prototype's synthetic views or use synthetic context when Real Data mode is selected.")
        st.dataframe(group.tail(4).sort_values("date", ascending=False), hide_index=True, use_container_width=True)
        return

    st.markdown(f"#### {module.title()} | pending data integration")
    st.info("This module is available in the synthetic prototype. Its real-data counterpart needs independently sourced inputs and validation before activation; no synthetic values are shown here.")
