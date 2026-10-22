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


def _signed_money(value, digits=0):
    return f"{'+' if value >= 0 else '−'}€{abs(float(value)):,.{digits}f}m"


def _signed_pp(value):
    return f"{float(value):+.2f}pp"


def _pct_change(now, previous):
    return 100.0 * (float(now) / float(previous) - 1.0) if previous else float("nan")


def _directional_rag(values):
    """QoQ momentum screening only; *not* an ABN regulatory/risk appetite test.

    Income and capital/liquidity ratios use higher-is-favourable direction
    solely for descriptive momentum screening. No hard-coded bank limits.
    """
    series = [float(x) for x in values if pd.notna(x)]
    if len(series) < 2:
        return _NEUTRAL
    move = series[-1] - series[-2]
    last_move = series[-2] - series[-3] if len(series) >= 3 else float("nan")
    if move > 0:
        status = "GREEN"
    elif move < 0 and pd.notna(last_move) and last_move < 0:
        status = "RED"
    else:
        status = "AMBER"
    return {
        "status": status,
        "basis": "directional_momentum",
        "rule": (
            "Quarterly directional MONITORING (not ABN-approved RAG limits): "
            "Green = latest quarter improves; Amber = flat or first decline; "
            "Red = two consecutive declines. This is not a risk-appetite or "
            "regulatory compliance conclusion."
        ),
    }


def _card(label, current, previous, formatter, module, why, impact, next_action,
          unit, *, reading=None, trend_values=None, trend_dates=None, context=None):
    # Never substitute daily/monthly data or interpolate missing reporting periods.
    delta = float(current - previous) if pd.notna(current) and pd.notna(previous) else 0.0
    movement = (
        f"{delta:+,.2f}{unit} vs prior quarter"
        if pd.notna(current) and pd.notna(previous) else "Prior-quarter comparison unavailable"
    )
    return {
        "label": label, "value": formatter(current), "delta_pp": delta,
        "delta_unit": unit, "delta_label": "QoQ" if pd.notna(previous) else "No comparison",
        "context": context if context else movement, "module": module,
        "rag": reading if reading is not None else _NEUTRAL,
        "why": why, "impact": impact, "next": next_action,
        "trend_values": list(trend_values) if trend_values is not None else [],
        "trend_dates": list(trend_dates) if trend_dates is not None else [],
    }


def _group_card(frame, metric, label, formatter, module, unit, description, segments=None):
    available = frame.dropna(subset=[metric]).sort_values("date")
    if available.empty:
        return _card(
            label, float("nan"), float("nan"), formatter, module,
            f"{description} is not disclosed.", "No actual observations available.",
            "Obtain reported disclosures before further analysis.", unit,
        )
    latest = available.iloc[-1]
    previous = available.iloc[-2] if len(available) >= 2 else latest
    now, before = float(latest[metric]), float(previous[metric])
    diff = now - before
    q = _quarter(latest["date"])
    prev_q = _quarter(previous["date"])
    growth = _pct_change(now, before)
    yoy = available.loc[
        available["date"] == latest["date"] - pd.DateOffset(years=1), metric
    ]
    yoy_value = float(yoy.iloc[0]) if not yoy.empty else float("nan")
    yoy_detail = (
        f"{_signed_pp(now - yoy_value)} YoY" if unit == "pp"
        else f"{_signed_money(now - yoy_value)} YoY"
    ) if pd.notna(yoy_value) else "Year-on-year comparison unavailable"
    context = f"{_signed_pp(diff) if unit == 'pp' else _signed_money(diff)} QoQ · {yoy_detail}"
    why = f"{description} changed from {formatter(before)} in {prev_q} to {formatter(now)} in {q}."
    impact = "Quarterly reported actual. Its movement must not be treated as a forecast."
    next_action = "Review the period-specific source detail before setting management actions."

    if metric == "cet1_ratio_pct":
        capital_change = latest["cet1_capital_m"] - previous["cet1_capital_m"]
        rwa_change = latest["rwa_m"] - previous["rwa_m"]
        why = (
            f"CET1 rose {_signed_pp(diff)} QoQ to {_percent(now)}. "
            f"Disclosed CET1 capital increased {_signed_money(capital_change)} "
            f"to {_money(latest['cet1_capital_m'])}, while RWA moved "
            f"{_signed_money(rwa_change)} to {_money(latest['rwa_m'])}."
        )
        impact = (
            f"The reported capital-to-RWA ratio is {yoy_detail}. "
            "Higher capital and slightly lower RWA support the quarterly ratio increase. "
            "The factsheet does not establish ABN's binding capital requirement or internal buffer."
        )
        rwa_watch = ""
        if segments is not None:
            latest_segment = segments[segments["date"] == latest["date"]].set_index("business_line")
            previous_segment = segments[segments["date"] == previous["date"]].set_index("business_line")
            changes = (latest_segment["rwa_m"] - previous_segment["rwa_m"]).dropna()
            if not changes.empty:
                leaders = changes.reindex(changes.abs().sort_values(ascending=False).index).head(2)
                rwa_watch = "; ".join(
                    f"{name} {_signed_money(movement)}" for name, movement in leaders.items()
                )
        next_action = (
            f"Trace CET1 capital movements and the largest segment RWA shifts "
            f"({rwa_watch})." if rwa_watch else
            "Trace the CET1 capital bridge and the segment-level RWA movements."
        )
    elif metric == "lcr_pct":
        nsfr_change = latest["nsfr_pct"] - previous["nsfr_pct"]
        deposits_change = latest["deposits_m"] - previous["deposits_m"]
        why = (
            f"Reported LCR rose {_signed_pp(diff)} to {_percent(now)}. "
            f"Over the same quarter, NSFR moved {_signed_pp(nsfr_change)} "
            f"to {_percent(latest['nsfr_pct'])}, and customer deposits moved "
            f"{_signed_money(deposits_change)} to {_money(latest['deposits_m'])}."
        )
        impact = (
            "The short-term liquidity coverage measure improved despite lower "
            "customer deposits, while NSFR decreased. The direction is mixed; "
            "the factsheet does not separately disclose all LCR inflow/outflow drivers."
        )
        next_action = (
            "Review the HQLA and stressed-net-outflow bridge underlying LCR, "
            "and reconcile deposit changes by business line and NSFR movement."
        )
    elif metric == "net_profit_m":
        income_change = latest["operating_income_m"] - previous["operating_income_m"]
        expense_change = latest["operating_expenses_m"] - previous["operating_expenses_m"]
        impairment_change = latest["impairment_charges_m"] - previous["impairment_charges_m"]
        ci_change = latest["cost_income_ratio_pct"] - previous["cost_income_ratio_pct"]
        why = (
            f"Quarterly net profit increased {_signed_money(diff, 1)} "
            f"({growth:+.1f}%) QoQ to {_money(now)}. Reported operating income "
            f"moved {_signed_money(income_change)}; operating expenses "
            f"{_signed_money(expense_change)}; impairment charges "
            f"{_signed_money(impairment_change)}."
        )
        impact = (
            f"Cost/income improved {_signed_pp(ci_change)} to "
            f"{_percent(latest['cost_income_ratio_pct'])}; profit was "
            f"{_pct_change(now, yoy_value):+.1f}% YoY. "
            "The listed operating movements do not constitute a full net-profit bridge."
        ) if pd.notna(yoy_value) else (
            "The observable changes in income, costs and impairments "
            "do not by themselves fully reconcile net profit."
        )
        next_action = (
            "Reconcile taxes and other P&L items, then check whether income "
            "and impairment movements are recurring before extrapolating Q2 earnings."
        )
    elif metric == "nii_m":
        loan_change = latest["loans_m"] - previous["loans_m"]
        nim_change = latest["nim_bps"] - previous["nim_bps"]
        share = 100 * now / latest["operating_income_m"] if latest["operating_income_m"] else float("nan")
        why = (
            f"NII grew {_signed_money(diff, 1)} ({growth:+.1f}%) QoQ. "
            f"Reported NIM was {latest['nim_bps']:.2f}bps "
            f"({nim_change:+.2f}bps QoQ), while quarter-end customer loans "
            f"increased {_signed_money(loan_change)}."
        )
        impact = (
            f"NII represents {share:.1f}% of reported Q2 operating income; "
            f"its movement is {yoy_detail}. "
            "Flat NIM alongside higher loans is consistent with a possible volume effect, "
            "but it does not establish causal rate/volume attribution."
        )
        next_action = (
            "Obtain average interest-earning assets and loan/deposit yields to "
            "separate volume, mix and repricing effects rather than estimating "
            "NIM from quarter-end loan balances."
        )

    return _card(
        label, now, before, formatter, module, why, impact, next_action, unit,
        reading=_directional_rag(available[metric].tolist()),
        trend_values=available[metric].tolist(),
        trend_dates=[_quarter(date) for date in available["date"]],
        context=context,
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
        group_at_close = group.loc[group["date"] == current["date"]].iloc[0]

        def bl_card(metric, title, module):
            now = float(current[metric])
            old = float(previous[metric]) if previous is not None else float("nan")
            diff = now - old if pd.notna(old) else float("nan")
            group_total = float(group_at_close[metric])
            share = 100.0 * now / group_total if group_total else float("nan")
            why = (
                f"{title.title()} for {business_line} moved "
                f"{_signed_money(diff)} from {_money(old)} in "
                f"{_quarter(previous['date'])} to {_money(now)} in "
                f"{_quarter(current['date'])}."
            ) if pd.notna(diff) else f"Reported {title.lower()}: {_money(now)}."
            impact = (
                f"This segment represents {share:.1f}% of reported Group "
                f"{metric.replace('_m', '').replace('_', ' ')}. "
                "The percentage is a calculated share; the underlying amounts "
                "are disclosed. The movement alone does not establish quality or risk."
            )
            next_actions = {
                "loans_m": "Check lending composition and sector/product changes in a more detailed source before attributing loan growth.",
                "deposits_m": "Reconcile the quarterly segment deposit movement to Group funding movements and check customer/product mix.",
                "rwa_m": "Reconcile segment RWA changes and compare movement with segment loan balances; require risk-weight details before interpreting drivers.",
            }
            context = (
                f"{_signed_money(diff)} QoQ · {share:.1f}% of Group"
                if pd.notna(diff) else f"{share:.1f}% of Group"
            )
            return _card(
                title, now, old, _money, module, why, impact,
                next_actions[metric], "m", reading=_NEUTRAL,
                trend_values=selected[metric].dropna().tolist(),
                trend_dates=[_quarter(date) for date in selected.loc[selected[metric].notna(), "date"]],
                context=context,
            )

        s.kpi_cards = [
            bl_card("loans_m", "CUSTOMER LOANS", "brief"),
            bl_card("deposits_m", "CUSTOMER DEPOSITS", "brief"),
            bl_card("rwa_m", "RISK-WEIGHTED ASSETS", "brief"),
        ]
        ld_series = 100.0 * selected["loans_m"] / selected["deposits_m"].replace(0, float("nan"))
        now_ld = float(ld_series.iloc[-1])
        prev_ld = float(ld_series.iloc[-2]) if len(ld_series) > 1 else float("nan")
        s.kpi_cards.append(_card(
            "LOAN / DEPOSIT RATIO", now_ld, prev_ld, _percent, "treasury",
            f"The {business_line} loan/deposit ratio is {_percent(now_ld)}, "
            f"{_signed_pp(now_ld - prev_ld)} from the previous quarter. "
            "This is calculated from reported segment balances, not a standalone disclosure.",
            "Shows the relative reported lending and deposit balances of this segment. "
            "A higher ratio is not automatically positive or negative without funding context.",
            "Review the segment deposit outflow/inflow drivers and whether loan growth "
            "and funding remained balanced.", "pp", reading=_NEUTRAL,
            trend_values=ld_series.dropna().tolist(),
            trend_dates=[_quarter(date) for date in selected.loc[ld_series.notna(), "date"]],
            context=f"{_signed_pp(now_ld - prev_ld)} QoQ · calculated ratio",
        ))
    else:
        s.kpi_cards = [
            _group_card(group, "cet1_ratio_pct", "CET1 RATIO", _percent, "brief", "pp", "CET1 ratio", segments),
            _group_card(group, "lcr_pct", "LIQUIDITY COVERAGE", _percent, "treasury", "pp", "Liquidity coverage ratio", segments),
            _group_card(group, "net_profit_m", "QUARTERLY NET PROFIT", _money, "brief", "m", "Net profit", segments),
            _group_card(group, "nii_m", "NET INTEREST INCOME", _money, "brief", "m", "Net interest income", segments),
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
        # Isolated factsheet-only presentation; the original Synthetic module
        # (src/modules/brief.py) remains untouched.
        from src.reported_brief import render_reported_brief
        render_reported_brief(s)
        return

    if module == "horizon":
        # Preserve the original Synthetic src/modules/horizon.py without changes.
        # The separately governed quarterly engine operates on published actuals.
        from src.reported_horizon import render_reported_horizon
        render_reported_horizon(s)
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
        # Real Group scenario uses ONLY the public 2021+ Group NII/NIM and ECB
        # rates. Original src/modules/scenario.py stays untouched for Synthetic.
        from src.reported_scenario import render_reported_scenario
        render_reported_scenario(s)
        return

    if module == "copilot":
        # Phase 1: read-only source-grounded evidence. NEVER invoke the
        # Synthetic Copilot, its Genie agent or its legacy AI client.
        from src.reported_copilot import render_reported_copilot
        render_reported_copilot(s)
        return

    st.markdown(f"#### {module.title()} | pending data integration")
    st.info("This module is available in the synthetic prototype. Its real-data counterpart needs independently sourced inputs and validation before activation; no synthetic values are shown here.")
