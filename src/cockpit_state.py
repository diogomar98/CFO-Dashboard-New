"""
Derived cockpit state.

One pass over the certified views produces every value the HUD renders: the
headline ratios, the month-on-month and 30-day changes, the change/why/impact/
next narrative strings, and the slices each module charts.

Keeping this in one place means the shell and the modules read the same numbers,
and the presentation layer never reaches into a dataframe itself.
"""

import html
import math
from types import SimpleNamespace

import pandas as pd
import streamlit as st

from src import cockpit_views as views
from src.engines import build_horizon_baseline
from src.extended_data_loader import load_bank_daily_signals
from src.hud import BL_TO_DATA, clip_ui_text, safe_float
from src.rag import (
    AMBER,
    GREEN,
    HIGH,
    LOW,
    MEDIUM,
    confidence_fixed,
    confidence_probability,
    confidence_within,
    normal_cdf,
    rag,
    rag_from_status,
)

# The reference cockpit's lookback windows.
DEPOSIT_LOOKBACK_DAYS = 30
CREDIT_LOOKBACK_DAYS = 30
DAILY_RATE_LOOKBACK_DAYS = 30
NEWS_LOOKBACK_DAYS = 13

# The baseline runs to the end of the reporting year.
HORIZON_MONTHS_AHEAD = 4

# Basel III floors the executive KPI cards measure their headroom against.
REGULATORY_CET1_REQUIREMENT_PCT = 10.5
REGULATORY_LCR_REQUIREMENT_PCT = 100.0

# RAG thresholds shared by more than one reading: (green from, red below).
NIM_RAG_PCT = (1.75, 1.55)

# Tolerances the prediction confidence is measured against: the band a CFO
# would still call "on the projection".
NIM_TOLERANCE_BPS = 10.0
FY_NII_TOLERANCE_PCT = 2.0
ASSET_GROWTH_TOLERANCE_PP = 0.25

# Composite-score noise assumed on the synthetic strategy assessments.
STRATEGY_SCORE_NOISE_PTS = 3.0

# Days of silence that separate one anomaly episode from the next.
ANOMALY_EPISODE_GAP_DAYS = 3


def _latest_rows(frame, date_column="date"):
    """Rows on the most recent observed date."""
    if frame is None or frame.empty:
        return frame
    return frame[frame[date_column] == frame[date_column].max()]


def _deposit_by_country(business_line=None):
    """Latest deposit balance and 30-day change, aggregated to country."""
    signals = _latest_rows(views.cfo_deposit_signals(business_line=business_line))
    if signals is None or signals.empty:
        return pd.DataFrame()

    by_country = signals.groupby("country", as_index=False).agg(
        deposit_balance_m=("deposit_balance_m", "sum"),
        deposit_change_30d_m=("deposit_change_30d_m", "sum"),
    )

    prior = by_country["deposit_balance_m"] - by_country["deposit_change_30d_m"]
    by_country["deposit_change_30d_pct"] = (
        100.0 * by_country["deposit_change_30d_m"] / prior.replace(0, pd.NA)
    ).astype(float)

    return by_country.sort_values("deposit_change_30d_pct", ascending=False)


def _credit_detail(business_line=None):
    """Latest country / business-line credit rows, worst first."""
    detail = _latest_rows(views.cfo_credit_signals(business_line=business_line))
    if detail is None or detail.empty:
        return pd.DataFrame()

    return detail.sort_values(
        [
            "credit_watch_flag",
            "weighted_stage_2_share_pct",
            "weighted_stage_3_share_pct",
        ],
        ascending=[False, False, False],
    )


def _credit_trend(business_line=None):
    """The latest credit observation and its counterpart 30 days earlier."""
    signals = views.cfo_credit_signals(business_line=business_line)
    if signals is None or signals.empty:
        return pd.DataFrame()

    latest_date = signals["date"].max()
    prior_date = latest_date - pd.Timedelta(days=CREDIT_LOOKBACK_DAYS)

    return signals[signals["date"].isin([latest_date, prior_date])]


def _recent_news():
    """
    One row per article over the trailing news window.

    A story maps to several countries; the certified feed keeps the highest
    geographic impact row so the same headline is not listed repeatedly.
    """
    intelligence = views.cfo_news_intelligence()
    if intelligence is None or intelligence.empty:
        return pd.DataFrame()

    latest = intelligence["published_date"].max()
    recent = intelligence[
        intelligence["published_date"]
        >= latest - pd.Timedelta(days=NEWS_LOOKBACK_DAYS)
    ]

    ranked = recent.sort_values(
        ["news_id", "geo_impact_score", "country"], ascending=[True, False, True]
    ).drop_duplicates(subset="news_id", keep="first")

    return ranked.sort_values(
        ["relevance_score", "published_date"], ascending=[False, False]
    ).reset_index(drop=True)


@st.cache_data
def build_state(business_line=None):
    """Compute every derived cockpit value. Cached; returns a namespace."""
    s = SimpleNamespace()
    s.business_line = business_line
    s.business_line_label = business_line or "Group"

    # Map the display name to the value stored in the data column.
    data_bl = BL_TO_DATA.get(business_line, business_line) if business_line else None
    s.business_line_data = data_bl

    # ----------------------------------------------------------
    # Current position
    # ----------------------------------------------------------
    current_position = views.cfo_current_position().iloc[0]

    s.reporting_date_ts = pd.to_datetime(current_position["as_of_date"])
    s.reporting_date = s.reporting_date_ts.strftime("%d %B %Y")

    # The ratios above are a certified month-end close, but the cockpit also
    # runs on the daily signal table, which carries on past that close into the
    # open month. The header shows both so a reading is never mistaken for the
    # other: the live date is where the deposit, rate and credit signals end.
    daily = views.cfo_daily_bank(business_line=data_bl)
    s.live_date_ts = (
        pd.to_datetime(daily["date"].max())
        if daily is not None and not daily.empty
        else s.reporting_date_ts
    )
    s.live_date = s.live_date_ts.strftime("%d %B %Y")
    s.close_date = s.reporting_date_ts.strftime("%d %b %Y")

    s.cet1_ratio = safe_float(current_position["cet1_ratio_pct"])
    s.total_capital_ratio = safe_float(current_position["total_capital_ratio_pct"])
    s.lcr_ratio = safe_float(current_position["lcr_pct"])
    s.loan_to_deposit_ratio = safe_float(current_position["loan_to_deposit_pct"])
    s.ytd_roe_proxy = safe_float(current_position["annualised_ytd_roe_proxy_pct"])
    s.ytd_cost_income = safe_float(current_position["ytd_cost_income_ratio_pct"])
    s.ytd_nii = safe_float(current_position["ytd_nii_m"])
    s.ytd_operating_income = safe_float(current_position["ytd_operating_income_m"])
    s.current_loans_m = safe_float(current_position["loans_m"])
    s.current_deposits_m = safe_float(current_position["deposits_m"])
    s.total_assets = safe_float(current_position["total_assets_m"])
    s.cet1_capital = safe_float(current_position["cet1_capital_m"])
    s.hqla = safe_float(current_position["hqla_m"])
    s.months_observed = int(safe_float(current_position["months_observed"], 0))
    s.stage_2_share_pct = safe_float(current_position["stage_2_share_pct"])
    s.stage_3_share_pct = safe_float(current_position["stage_3_share_pct"])
    s.ecb_rate_pct = safe_float(current_position["ecb_rate_pct"])

    # ----------------------------------------------------------
    # Month-on-month change context
    # ----------------------------------------------------------
    history = views.cfo_financial_history().sort_values("date").reset_index(drop=True)
    s.history = history

    latest_history = history.iloc[-1]
    previous_history = history.iloc[-2] if len(history) >= 2 else latest_history

    s.latest_history = latest_history
    s.previous_history = previous_history
    s.previous_month_label = pd.to_datetime(previous_history["date"]).strftime("%b")
    s.cet1_mom_pp = s.cet1_ratio - safe_float(previous_history["cet1_ratio_pct"])
    s.lcr_mom_pp = s.lcr_ratio - safe_float(previous_history["lcr_pct"])

    prev_roe, prev_ci = ytd_metrics_through(history, previous_history["date"])
    s.ytd_roe_delta_pp = s.ytd_roe_proxy - safe_float(prev_roe, s.ytd_roe_proxy)
    s.ytd_ci_delta_pp = s.ytd_cost_income - safe_float(prev_ci, s.ytd_cost_income)

    # ----------------------------------------------------------
    # Certified NIM
    # ----------------------------------------------------------
    monthly_nim = views.cfo_monthly_nim(business_line=data_bl)
    valid_nim = monthly_nim.dropna(subset=["nim_pct"]).sort_values("month")
    s.monthly_nim = monthly_nim

    latest_nim_row = valid_nim.iloc[-1]
    previous_nim_row = valid_nim.iloc[-2] if len(valid_nim) >= 2 else latest_nim_row

    s.previous_cert_nim = safe_float(previous_nim_row["nim_pct"])
    s.cert_current_nim = safe_float(latest_nim_row["nim_pct"])
    s.cert_nim_months = int(monthly_nim["month"].nunique())
    s.nim_mom_bps = (s.cert_current_nim - s.previous_cert_nim) * 100.0

    # The cockpit now reads into the open month, so the newest row can hold a
    # handful of days against a full prior month. NIM already annualises on
    # days observed, but NII is a sum: comparing it raw would read a part-month
    # as a collapse in income. Both sides are lifted to a full-month run rate.
    def _nii_run_rate(row):
        days_observed = safe_float(row["days_observed"])
        if days_observed <= 0:
            return 0.0
        month_start = pd.to_datetime(row["month"])
        days_in_month = month_start.days_in_month
        return safe_float(row["monthly_nii_m"]) * days_in_month / days_observed

    s.cert_current_month_days = int(safe_float(latest_nim_row["days_observed"]))
    s.cert_current_month_is_partial = (
        s.cert_current_month_days
        < pd.to_datetime(latest_nim_row["month"]).days_in_month
    )
    s.cert_current_monthly_nii = _nii_run_rate(latest_nim_row)
    s.monthly_nii_change_m = s.cert_current_monthly_nii - _nii_run_rate(previous_nim_row)
    s.nii_basis_label = (
        f"run rate, {s.cert_current_month_days} days observed"
        if s.cert_current_month_is_partial
        else "full month"
    )

    # ----------------------------------------------------------
    # Daily pricing signals
    # ----------------------------------------------------------
    daily = views.cfo_daily_bank(business_line=data_bl).sort_values("date")
    s.daily = daily

    s.latest_daily_nim = s.cert_current_nim
    s.latest_daily_nii = 0.0
    s.daily_anomaly_flag = 0
    s.loan_rate_30d_bps = 0.0
    s.deposit_rate_30d_bps = 0.0
    s.spread_30d_bps = 0.0

    if not daily.empty:
        latest_daily = daily.iloc[-1]
        s.latest_daily_nim = safe_float(latest_daily["annualised_daily_nim_pct"])
        s.latest_daily_nii = safe_float(latest_daily["daily_nii_m"])
        s.daily_anomaly_flag = int(safe_float(latest_daily["has_anomaly"], 0))

        # When viewing a business line, override balance-sheet aggregates with
        # the BL-specific values from the latest daily signal row.
        if business_line is not None:
            s.current_loans_m = safe_float(latest_daily["interest_earning_assets_m"])
            s.current_deposits_m = safe_float(latest_daily["deposit_balance_m"])
            if s.current_deposits_m:
                s.loan_to_deposit_ratio = (
                    s.current_loans_m / s.current_deposits_m * 100.0
                )

        window_start = daily["date"].max() - pd.Timedelta(
            days=DAILY_RATE_LOOKBACK_DAYS
        )
        recent = daily[daily["date"] >= window_start].dropna(
            subset=["weighted_loan_rate_pct", "weighted_deposit_rate_pct"]
        )

        if not recent.empty:
            first, last = recent.iloc[0], recent.iloc[-1]
            s.loan_rate_30d_bps = (
                safe_float(last["weighted_loan_rate_pct"])
                - safe_float(first["weighted_loan_rate_pct"])
            ) * 100.0
            s.deposit_rate_30d_bps = (
                safe_float(last["weighted_deposit_rate_pct"])
                - safe_float(first["weighted_deposit_rate_pct"])
            ) * 100.0
            s.spread_30d_bps = s.loan_rate_30d_bps - s.deposit_rate_30d_bps

    # ----------------------------------------------------------
    # Product-level data for BL-specific KPI cards
    # ----------------------------------------------------------
    s.bl_rwa_m = 0.0
    s.bl_rwa_30d_change_pct = 0.0
    s.bl_product_detail = {}
    s.bl_mortgage_m = 0.0
    s.bl_mortgage_30d_change_pct = 0.0
    s.bl_consumer_loan_m = 0.0
    s.bl_lombard_m = 0.0
    s.bl_lombard_30d_change_pct = 0.0
    s.bl_corp_loan_30d_change_pct = 0.0
    s.bl_corp_loan_m = 0.0
    s.bl_lombard_rate_pct = 0.0
    s.ld_30d_change_pp = 0.0
    s.bl_stage_2_rank = None
    s.bl_count = 0

    if business_line is not None:
        # Every figure below reads from a certified view; nothing here
        # touches the raw signal table directly.
        if not daily.empty:
            s.bl_rwa_m = safe_float(daily.iloc[-1]["rwa_m"])

            # Loan-to-deposit 30 days ago, from the same certified daily view.
            prior_daily = daily[
                daily["date"]
                <= daily["date"].max() - pd.Timedelta(days=DEPOSIT_LOOKBACK_DAYS)
            ]
            if not prior_daily.empty:
                prior_row = prior_daily.iloc[-1]
                prior_deposits = safe_float(prior_row["deposit_balance_m"])
                if prior_deposits:
                    prior_ld = (
                        safe_float(prior_row["interest_earning_assets_m"])
                        / prior_deposits
                        * 100.0
                    )
                    s.ld_30d_change_pp = s.loan_to_deposit_ratio - prior_ld

        products = _latest_rows(views.cfo_product_signals(business_line=data_bl))
        if products is not None and not products.empty:
            s.bl_product_detail = {
                row["product"]: row.to_dict() for _, row in products.iterrows()
            }

            rwa_now = products["rwa_m"].sum()
            rwa_prior = rwa_now - products["rwa_change_30d_m"].sum()
            if rwa_prior:
                s.bl_rwa_30d_change_pct = (rwa_now - rwa_prior) / rwa_prior * 100

            def _lending_product(name):
                """(balance, 30D change %, weighted rate) for one loan product."""
                row = s.bl_product_detail.get(name)
                if row is None:
                    return 0.0, 0.0, 0.0
                return (
                    safe_float(row["loan_balance_m"]),
                    safe_float(row["loan_change_30d_pct"]),
                    safe_float(row["weighted_rate_pct"]),
                )

            s.bl_mortgage_m, s.bl_mortgage_30d_change_pct, _ = _lending_product("Mortgage")
            s.bl_consumer_loan_m, _, _ = _lending_product("Consumer Loan")
            (
                s.bl_lombard_m,
                s.bl_lombard_30d_change_pct,
                s.bl_lombard_rate_pct,
            ) = _lending_product("Lombard Loan")
            s.bl_corp_loan_m, s.bl_corp_loan_30d_change_pct, _ = _lending_product(
                "Corporate Loan"
            )

        # Where this business line's Stage 2 share ranks against the others,
        # so the narrative states a computed fact rather than an assumption.
        all_credit = _latest_rows(views.cfo_credit_signals())
        if all_credit is not None and not all_credit.empty:
            weighted = all_credit.assign(
                _s2_x_loans=all_credit["weighted_stage_2_share_pct"]
                * all_credit["loan_balance_m"]
            )
            by_bl = weighted.groupby("business_line")[
                ["_s2_x_loans", "loan_balance_m"]
            ].sum()
            stage_2_by_bl = (
                by_bl["_s2_x_loans"] / by_bl["loan_balance_m"].replace(0, pd.NA)
            ).dropna().astype(float).sort_values(ascending=False)
            s.bl_count = len(stage_2_by_bl)
            if data_bl in stage_2_by_bl.index:
                s.bl_stage_2_rank = list(stage_2_by_bl.index).index(data_bl) + 1

    # ----------------------------------------------------------
    # Deposits by country
    # ----------------------------------------------------------
    deposit_country = _deposit_by_country(business_line=data_bl)
    s.deposit_country = deposit_country

    s.deposit_leader = None
    s.deposit_laggard = None
    s.negative_deposit_countries = 0
    s.total_deposit_30d_change_m = 0.0
    s.total_deposit_30d_change_pct = 0.0

    if not deposit_country.empty:
        s.deposit_leader = deposit_country.iloc[0]
        s.deposit_laggard = deposit_country.iloc[-1]
        s.negative_deposit_countries = int(
            (deposit_country["deposit_change_30d_pct"] < 0).sum()
        )
        current_deposits = deposit_country["deposit_balance_m"].sum()
        s.total_deposit_30d_change_m = deposit_country["deposit_change_30d_m"].sum()
        prior_deposits = current_deposits - s.total_deposit_30d_change_m
        if prior_deposits:
            s.total_deposit_30d_change_pct = (
                s.total_deposit_30d_change_m / prior_deposits * 100.0
            )

    # ----------------------------------------------------------
    # Credit migration
    # ----------------------------------------------------------
    credit_detail = _credit_detail(business_line=data_bl)
    s.credit_detail = credit_detail

    s.current_credit_watch_count = 0
    s.credit_hotspot = None
    s.credit_hotspot_stage2_delta_pp = None

    if not credit_detail.empty:
        s.current_credit_watch_count = int(credit_detail["credit_watch_flag"].sum())
        s.credit_hotspot = credit_detail.iloc[0]

        # BL-level weighted credit quality for the KPI cards.
        total_bl_loans = credit_detail["loan_balance_m"].sum()
        if total_bl_loans > 0:
            s.bl_stage_2_pct = float(
                (credit_detail["weighted_stage_2_share_pct"]
                 * credit_detail["loan_balance_m"]).sum()
                / total_bl_loans
            )
            s.bl_stage_3_pct = float(
                (credit_detail["weighted_stage_3_share_pct"]
                 * credit_detail["loan_balance_m"]).sum()
                / total_bl_loans
            )
        else:
            s.bl_stage_2_pct = s.stage_2_share_pct
            s.bl_stage_3_pct = s.stage_3_share_pct

        trend = _credit_trend(business_line=data_bl)
        if not trend.empty:
            match = trend[
                (trend["country"] == s.credit_hotspot["country"])
                & (trend["business_line"] == s.credit_hotspot["business_line"])
            ].sort_values("date")
            if len(match) >= 2:
                s.credit_hotspot_stage2_delta_pp = safe_float(
                    match.iloc[-1]["weighted_stage_2_share_pct"]
                ) - safe_float(match.iloc[0]["weighted_stage_2_share_pct"])

            # BL-aggregate Stage 2 change over the same 30-day window.
            dates = sorted(trend["date"].unique())
            if len(dates) >= 2:
                def _bl_s2(on_date):
                    snap = trend[trend["date"] == on_date]
                    w = snap["loan_balance_m"].sum()
                    return float(
                        (snap["weighted_stage_2_share_pct"] * snap["loan_balance_m"]).sum() / w
                    ) if w else 0.0
                s.bl_stage_2_delta_pp = _bl_s2(dates[-1]) - _bl_s2(dates[0])
            else:
                s.bl_stage_2_delta_pp = 0.0
        else:
            s.bl_stage_2_delta_pp = 0.0

    # ----------------------------------------------------------
    # External intelligence
    # ----------------------------------------------------------
    news_recent = _recent_news()
    geo_news = views.cfo_geo_news_summary()
    if not geo_news.empty:
        geo_news = geo_news.sort_values("geo_attention_score", ascending=False)

    s.news_recent = news_recent
    s.geo_news = geo_news
    s.high_impact_news_count = 0
    s.top_news = None
    s.geo_focus = None

    if not news_recent.empty:
        levels = news_recent["potential_impact_level"].fillna("").astype(str).str.upper()
        s.high_impact_news_count = int((levels == "HIGH").sum())
        s.top_news = news_recent.iloc[0]

    if not geo_news.empty:
        s.geo_focus = geo_news.iloc[0]

    # ----------------------------------------------------------
    # Treasury
    # ----------------------------------------------------------
    treasury_summary_df = views.cfo_treasury_summary()
    s.treasury_summary = (
        treasury_summary_df.iloc[0] if not treasury_summary_df.empty else None
    )
    s.treasury_market_value_m = 0.0
    s.treasury_unrealised_pnl_m = 0.0
    s.treasury_duration = 0.0
    s.treasury_dv01 = 0.0

    if s.treasury_summary is not None:
        s.treasury_market_value_m = safe_float(s.treasury_summary["market_value_m"])
        s.treasury_unrealised_pnl_m = safe_float(
            s.treasury_summary["unrealized_pnl_m"]
        )
        s.treasury_duration = safe_float(
            s.treasury_summary["weighted_modified_duration"]
        )
        s.treasury_dv01 = safe_float(s.treasury_summary["portfolio_dv01_m_per_bp"])

    scenarios = views.cfo_treasury_scenarios()
    s.treasury_scenarios = scenarios

    s.treasury_rate50_impact_m = 0.0
    rate50 = scenarios[scenarios["scenario_name"].str.contains("50bps", na=False)]
    rate50 = rate50[rate50["rate_shock_bps"] == 50]
    rate50 = rate50[rate50["credit_spread_shock_bps"].fillna(0).abs() < 0.001]
    if not rate50.empty:
        s.treasury_rate50_impact_m = safe_float(
            rate50.iloc[0]["economic_value_impact_m"]
        )

    impact = s.treasury_rate50_impact_m
    s.treasury_rate50_text = (
        f"-€{abs(impact) / 1000:.2f}bn"
        if impact < 0
        else f"+€{impact / 1000:.2f}bn"
        if impact > 0
        else "—"
    )

    # The local portfolio carries a single snapshot, so no day-over-day move
    # exists yet. The UI shows the change automatically once one does.
    s.treasury_market_change_m = None
    s.treasury_market_change_pct = None
    s.treasury_market_trend_label = "Prior snapshot"
    s.treasury_market_trend_css = "trend-flat"
    s.treasury_market_trend_text = "— / unavailable"

    s.hedge_options = views.cfo_hedge_options()
    s.strongest_hedge = (
        s.hedge_options.sort_values("dv01_reduction_pct", ascending=False).iloc[0]
        if s.hedge_options is not None and not s.hedge_options.empty
        else None
    )

    # ----------------------------------------------------------
    # Peers
    # ----------------------------------------------------------
    peers = views.cfo_peer_benchmark()
    s.peer_benchmark = peers
    s.peer_count = len(peers) if peers is not None else 0
    s.peer_profitability_median = 0.0
    s.peer_cet1_median = 0.0
    s.peer_cost_income_median = 0.0
    s.peer_plot = pd.DataFrame()

    if peers is not None and not peers.empty:
        for column, attribute in [
            ("profitability_peer_median_pct", "peer_profitability_median"),
            ("cet1_peer_median_pct", "peer_cet1_median"),
            ("cost_income_peer_median_pct", "peer_cost_income_median"),
        ]:
            values = peers[column].dropna()
            if not values.empty:
                setattr(s, attribute, safe_float(values.iloc[0]))

        plot = peers[
            [
                "bank_name",
                "reported_return_pct",
                "cet1_ratio_pct",
                "cost_income_ratio_pct",
                "total_assets_m",
                "return_metric_type",
            ]
        ].copy()
        plot["is_our_bank"] = "Peer"

        our_row = pd.DataFrame(
            [
                {
                    "bank_name": "Our Bank",
                    "reported_return_pct": s.ytd_roe_proxy,
                    "cet1_ratio_pct": s.cet1_ratio,
                    "cost_income_ratio_pct": s.ytd_cost_income,
                    "total_assets_m": s.total_assets,
                    "return_metric_type": "Annualised YTD ROE proxy",
                    "is_our_bank": "Our Bank",
                }
            ]
        )
        s.peer_plot = pd.concat([plot, our_row], ignore_index=True)

    s.roe_peer_gap_pp = s.ytd_roe_proxy - s.peer_profitability_median
    s.cet1_peer_gap_pp = s.cet1_ratio - s.peer_cet1_median
    s.efficiency_peer_advantage_pp = s.peer_cost_income_median - s.ytd_cost_income

    # ----------------------------------------------------------
    # Strategy
    # ----------------------------------------------------------
    radar = views.cfo_strategic_radar()
    gaps = views.cfo_capability_gaps()
    s.strategic_radar = radar
    s.capability_gaps = gaps
    s.top_strategy = radar.iloc[0] if radar is not None and not radar.empty else None
    s.top_capability_gap = (
        gaps.sort_values("capability_gap", ascending=False).iloc[0]
        if gaps is not None and not gaps.empty
        else None
    )

    s.second_strategy = None
    s.strategy_score_gap = 0.0
    s.strategy_delta = pd.DataFrame()
    s.strategy_advantage_pills = []

    if radar is not None and len(radar) >= 2:
        s.second_strategy = radar.iloc[1]
        s.strategy_score_gap = safe_float(
            s.top_strategy["overall_opportunity_score"]
        ) - safe_float(s.second_strategy["overall_opportunity_score"])

        # The opportunity map plots only fit against attractiveness; the rank
        # itself is this seven-factor composite, so the gap is broken out.
        component_spec = [
            ("Strategic fit", "strategic_fit_score", 0.30, False),
            ("Financial attractiveness", "financial_attractiveness_score", 0.15, False),
            ("Integration feasibility", "integration_feasibility_score", 0.15, False),
            ("Affordability", "affordability_score", 0.10, False),
            ("Innovation", "innovation_score", 0.15, False),
            ("Time to value", "time_to_value_score", 0.10, False),
            ("Regulatory simplicity", "regulatory_complexity_score", 0.05, True),
        ]

        rows = []
        for label, column, weight, inverse in component_spec:
            top_value = safe_float(s.top_strategy[column])
            second_value = safe_float(s.second_strategy[column])
            if inverse:
                top_value, second_value = 100.0 - top_value, 100.0 - second_value
            rows.append(
                {"Component": label, "Weighted delta": weight * (top_value - second_value)}
            )

        s.strategy_delta = pd.DataFrame(rows)
        positive = s.strategy_delta[s.strategy_delta["Weighted delta"] > 0]
        for _, row in positive.sort_values(
            "Weighted delta", ascending=False
        ).head(3).iterrows():
            s.strategy_advantage_pills.append(
                f"{row['Component']} +{row['Weighted delta']:.1f} pts"
            )

    # ----------------------------------------------------------
    # Horizon baseline
    # ----------------------------------------------------------
    s.current_loan_rate_pct = 0.0
    s.current_deposit_rate_pct = 0.0
    if not daily.empty:
        latest_rates = daily.iloc[-1]
        s.current_loan_rate_pct = safe_float(latest_rates["weighted_loan_rate_pct"])
        s.current_deposit_rate_pct = safe_float(
            latest_rates["weighted_deposit_rate_pct"]
        )

    s.horizon_baseline, horizon_metrics = build_horizon_baseline(
        s.monthly_nim,
        months_ahead=HORIZON_MONTHS_AHEAD,
        current_loans_m=s.current_loans_m,
        current_deposits_m=s.current_deposits_m,
        current_loan_rate_pct=s.current_loan_rate_pct,
        current_deposit_rate_pct=s.current_deposit_rate_pct,
        loan_rate_30d_bps=s.loan_rate_30d_bps,
        deposit_rate_30d_bps=s.deposit_rate_30d_bps,
        deposit_growth_30d_pct=s.total_deposit_30d_change_pct,
    )

    s.horizon_metrics = horizon_metrics
    s.horizon_year_end_nim = safe_float(
        horizon_metrics.get("year_end_nim_pct"), s.cert_current_nim
    )
    s.horizon_change_bps = safe_float(
        horizon_metrics.get("current_to_year_end_bps"), 0.0
    )
    s.horizon_first_month_bps = safe_float(
        horizon_metrics.get("first_month_nim_change_bps"), 0.0
    )
    s.horizon_full_year_nii_m = safe_float(
        horizon_metrics.get("full_year_nii_m"), s.ytd_nii
    )
    s.horizon_remaining_nii_m = safe_float(
        horizon_metrics.get("forecast_nii_remaining_m"), 0.0
    )
    s.horizon_asset_growth_pct = safe_float(
        horizon_metrics.get("trailing_asset_growth_pct"), 0.0
    )
    s.horizon_deposit_growth_pct = safe_float(
        horizon_metrics.get("deposit_growth_run_rate_pct"), 0.0
    )
    s.horizon_method_text = str(horizon_metrics.get("baseline_method", ""))

    _build_narrative(s)
    _build_kpi_explainers(s)
    _build_domain_grid(s)
    _build_predictions(s)
    _build_ratings(s)
    _build_internal_news(s)

    return s


def ytd_metrics_through(history, cutoff_date):
    """
    Year-to-date ROE proxy and cost/income as they stood at a past month-end.

    Recomputing the YTD aggregates at the cutoff is what makes the headline
    deltas honest: comparing a YTD figure against a single prior month would
    mix two different bases.
    """
    cutoff_date = pd.to_datetime(cutoff_date)
    local = history[
        (history["date"].dt.year == cutoff_date.year)
        & (history["date"] <= cutoff_date)
    ]

    if local.empty:
        return None, None

    months = int(local["date"].dt.month.nunique())
    avg_cet1 = local["cet1_capital_m"].mean()
    net_profit = local["net_profit_m"].sum()
    operating_income = local["operating_income_m"].sum()
    operating_costs = local["operating_costs_m"].sum()

    roe = (
        None
        if not avg_cet1 or months <= 0
        else net_profit * (12.0 / months) / avg_cet1 * 100.0
    )
    cost_income = (
        None if not operating_income else operating_costs / operating_income * 100.0
    )

    return roe, cost_income


def _direction(value, up="rose", down="fell", flat="was unchanged"):
    return up if value > 0 else down if value < 0 else flat


def _build_bl_kpi_explainers(s):
    """BL-specific headline cards, tailored to each business line.

    Routes to a dedicated function per business line so each tab shows
    the metrics most relevant to its domain.

    Escaping: each builder escapes the business-line name and any data-sourced
    text (countries) once, up front. The why / impact / next strings are built
    only from those escaped pieces, numbers and fixed copy, so they are not
    escaped again (doing so rendered "&" as "&amp;amp;").
    """
    bl = s.business_line
    if bl == "Personal & Business Banking":
        _build_pbb_kpi_explainers(s)
    elif bl == "Wealth Management":
        _build_wm_kpi_explainers(s)
    elif bl == "Corporate Banking":
        _build_cb_kpi_explainers(s)
    else:
        _build_generic_bl_kpi_explainers(s)


def _build_pbb_kpi_explainers(s):
    """Personal & Business Banking: NIM, Mortgage Book, Deposit Base, Credit Quality."""
    escape = html.escape
    bl = escape(s.business_line)

    spread_dir = (
        "widened" if s.spread_30d_bps > 0
        else "narrowed" if s.spread_30d_bps < 0
        else "was unchanged"
    )

    if s.deposit_leader is not None and s.deposit_laggard is not None:
        dep_context = (
            f"{escape(str(s.deposit_leader['country']))} leads "
            f"{safe_float(s.deposit_leader['deposit_change_30d_pct']):+.1f}%"
        )
    else:
        dep_context = "country detail unavailable"

    bl_s2 = getattr(s, "bl_stage_2_pct", s.stage_2_share_pct)
    bl_s3 = getattr(s, "bl_stage_3_pct", s.stage_3_share_pct)
    bl_s2_delta = getattr(s, "bl_stage_2_delta_pp", 0.0)

    mortgage_share = (
        f"{s.bl_mortgage_m / s.current_loans_m * 100:.0f}% of loan book"
        if s.current_loans_m else "loan book data unavailable"
    )

    s.kpi_cards = [
        {
            "label": "NET INTEREST MARGIN",
            "value": f"{s.cert_current_nim:.2f}%",
            "delta_pp": s.nim_mom_bps,
            "delta_unit": "bps",
            "context": f"{bl} · pricing spread {s.spread_30d_bps:+.1f} bps over 30D",
            "module": "brief",
            "rag": rag(s.cert_current_nim, *NIM_RAG_PCT, unit="%", precision=2),
            "why": (
                f"The loan-versus-deposit pricing spread {spread_dir} by "
                f"{abs(s.spread_30d_bps):.1f} bps over 30 days for {bl}."
            ),
            "impact": (
                f"At {s.cert_current_nim:.2f}%, {bl} carries "
                f"€{s.current_loans_m / 1000:,.1f}bn of earning assets "
                f"generating €{s.cert_current_monthly_nii:,.0f}m of monthly NII."
            ),
            "next": (
                f"Trace {bl} pricing drivers by country in Morning Brief."
            ),
        },
        {
            "label": "MORTGAGE BOOK",
            "value": f"€{s.bl_mortgage_m / 1000:,.1f}bn",
            "delta_pp": s.bl_mortgage_30d_change_pct,
            "delta_unit": "%",
            "delta_label": "over 30D",
            "context": f"{bl} · {mortgage_share}",
            "module": "brief",
            "rag": rag(s.bl_mortgage_30d_change_pct, 0.0, -1.0, unit="% 30D"),
            "why": (
                f"Mortgages account for €{s.bl_mortgage_m / 1000:,.1f}bn of "
                f"the €{s.current_loans_m / 1000:,.1f}bn {bl} loan book "
                f"({mortgage_share})."
            ),
            "impact": (
                f"Mortgage book moved {s.bl_mortgage_30d_change_pct:+.2f}% over "
                f"30 days. Consumer loans add "
                f"€{s.bl_consumer_loan_m / 1000:,.1f}bn."
            ),
            "next": (
                f"Review mortgage pricing and repayment dynamics by country "
                f"in Morning Brief."
            ),
        },
        {
            "label": "DEPOSIT BASE",
            "value": f"€{s.current_deposits_m / 1000:,.1f}bn",
            "delta_pp": s.total_deposit_30d_change_pct,
            "delta_unit": "%",
            "delta_label": "over 30D",
            "context": f"{bl} · {dep_context}",
            "module": "treasury",
            "rag": rag(s.total_deposit_30d_change_pct, 0.0, -1.0, unit="% 30D"),
            "why": (
                f"{bl} deposits moved "
                f"€{s.total_deposit_30d_change_m / 1000:+,.2f}bn "
                f"({s.total_deposit_30d_change_pct:+.2f}%) over the last "
                f"30 days."
            ),
            "impact": (
                f"€{s.current_deposits_m / 1000:,.1f}bn of {bl} deposits fund "
                f"€{s.current_loans_m / 1000:,.1f}bn of loans "
                f"(L/D {s.loan_to_deposit_ratio:.1f}%)."
            ),
            "next": (
                f"Review {bl} deposit pricing and country mix in Morning "
                f"Brief."
            ),
        },
        {
            "label": "CREDIT QUALITY",
            "value": f"{bl_s2:.2f}%",
            "delta_pp": bl_s2_delta,
            "delta_unit": "pp",
            "delta_label": "over 30D",
            "context": (
                f"{bl} Stage 2 · Stage 3 {bl_s3:.2f}% · "
                f"{s.current_credit_watch_count} watch(es)"
            ),
            "module": "brief",
            "rag": rag(
                bl_s2, 8.0, 12.0,
                higher_is_better=False, unit="% in Stage 2",
            ),
            "why": (
                f"Weighted Stage 2 share for {bl} is {bl_s2:.2f}% of the "
                f"loan book, {bl_s2_delta:+.2f}pp over 30 days."
            ),
            "impact": (
                f"Stage 2 exposure in {bl} is roughly "
                f"€{s.current_loans_m * bl_s2 / 100 / 1000:,.1f}bn under "
                f"heightened monitoring."
            ),
            "next": (
                f"Investigate {bl} migration drivers by country before "
                f"adjusting provisioning."
            ),
        },
    ]


def _build_wm_kpi_explainers(s):
    """Wealth Management: Client Cash, Lombard Book, Loan-to-Deposit, NII."""
    escape = html.escape
    bl = escape(s.business_line)

    nii_change_pct = (
        s.monthly_nii_change_m
        / max(abs(s.cert_current_monthly_nii - s.monthly_nii_change_m), 1)
        * 100.0
    )

    if s.deposit_leader is not None and s.deposit_laggard is not None:
        dep_context = (
            f"{escape(str(s.deposit_leader['country']))} leads "
            f"{safe_float(s.deposit_leader['deposit_change_30d_pct']):+.1f}%"
        )
    else:
        dep_context = "country detail unavailable"

    lombard_share_pct = (
        s.bl_lombard_m / s.current_loans_m * 100 if s.current_loans_m else 0.0
    )
    unlent_m = s.current_deposits_m - s.current_loans_m
    if unlent_m >= 0:
        ld_context = f"€{unlent_m / 1000:,.1f}bn of client cash not lent out"
        ld_impact = (
            f"Client cash exceeds lending by €{unlent_m / 1000:,.1f}bn in {bl}; "
            f"that surplus is capacity for Lombard growth or redeployment."
        )
    else:
        ld_context = f"lending exceeds client cash by €{-unlent_m / 1000:,.1f}bn"
        ld_impact = (
            f"Lending exceeds client cash by €{-unlent_m / 1000:,.1f}bn in {bl}, "
            f"so the gap is funded from elsewhere in the group."
        )

    s.kpi_cards = [
        {
            "label": "CLIENT CASH",
            "value": f"€{s.current_deposits_m / 1000:,.1f}bn",
            "delta_pp": s.total_deposit_30d_change_pct,
            "delta_unit": "%",
            "delta_label": "over 30D",
            "context": f"{bl} · {dep_context}",
            "module": "treasury",
            "rag": rag(s.total_deposit_30d_change_pct, 0.0, -1.0, unit="% 30D"),
            "why": (
                f"Client cash balances in {bl} moved "
                f"€{s.total_deposit_30d_change_m / 1000:+,.2f}bn "
                f"({s.total_deposit_30d_change_pct:+.2f}%) over the last "
                f"30 days."
            ),
            "impact": (
                f"€{s.current_deposits_m / 1000:,.1f}bn of {bl} client cash "
                f"at a weighted cost of {s.current_deposit_rate_pct:.2f}%."
            ),
            "next": (
                f"Review {bl} cash flows and client retention by country."
            ),
        },
        {
            "label": "LOMBARD BOOK",
            "value": f"€{s.bl_lombard_m / 1000:,.1f}bn",
            "delta_pp": s.bl_lombard_30d_change_pct,
            "delta_unit": "%",
            "delta_label": "over 30D",
            "context": f"{bl} · {lombard_share_pct:.0f}% of loan book",
            "module": "brief",
            "rag": rag(s.bl_lombard_30d_change_pct, 0.0, -2.0, unit="% 30D"),
            "why": (
                f"{bl} has €{s.bl_lombard_m / 1000:,.1f}bn of Lombard loans "
                f"outstanding, {lombard_share_pct:.0f}% of its "
                f"€{s.current_loans_m / 1000:,.1f}bn loan book."
            ),
            "impact": (
                f"Lombard book moved "
                f"{s.bl_lombard_30d_change_pct:+.2f}% over 30 days at a "
                f"weighted lending rate of {s.bl_lombard_rate_pct:.2f}%."
            ),
            "next": (
                f"Review {bl} Lombard utilisation rates and collateral "
                f"coverage."
            ),
        },
        {
            "label": "LOAN-TO-DEPOSIT",
            "value": f"{s.loan_to_deposit_ratio:.1f}%",
            "delta_pp": s.ld_30d_change_pp,
            "delta_unit": "pp",
            "delta_label": "over 30D",
            "context": f"{bl} · {ld_context}",
            "module": "treasury",
            "rag": rag(
                s.loan_to_deposit_ratio, 80.0, 95.0,
                higher_is_better=False, unit="%",
            ),
            "why": (
                f"{bl} has €{s.current_loans_m / 1000:,.1f}bn of Lombard "
                f"loans against €{s.current_deposits_m / 1000:,.1f}bn of "
                f"client cash — a {s.loan_to_deposit_ratio:.1f}% ratio."
            ),
            "impact": (
                f"{ld_impact} The ratio moved {s.ld_30d_change_pp:+.2f}pp "
                f"over 30 days."
            ),
            "next": (
                f"Consider {bl} deposit redeployment strategies and Lombard "
                f"pricing adjustments."
            ),
        },
        {
            "label": "NET INTEREST INCOME",
            "value": f"€{s.cert_current_monthly_nii:,.0f}m",
            "delta_pp": s.monthly_nii_change_m,
            "delta_unit": "m",
            "context": f"{bl} · {s.nii_basis_label}",
            "module": "brief",
            "rag": rag(nii_change_pct, 0.0, -3.0, unit="% MoM"),
            "why": (
                f"Monthly net interest income for {bl} on a "
                f"{s.nii_basis_label} basis."
            ),
            "impact": (
                f"€{s.cert_current_monthly_nii * 12 / 1000:,.2f}bn of "
                f"annualised NII at the current run rate for {bl}."
            ),
            "next": (
                f"Compare {bl} NII contribution against other business "
                f"lines."
            ),
        },
    ]


def _build_cb_kpi_explainers(s):
    """Corporate Banking: Credit Quality, RWA, NIM, Loan Book."""
    escape = html.escape
    bl = escape(s.business_line)

    bl_s2 = getattr(s, "bl_stage_2_pct", s.stage_2_share_pct)
    bl_s3 = getattr(s, "bl_stage_3_pct", s.stage_3_share_pct)
    bl_s2_delta = getattr(s, "bl_stage_2_delta_pp", 0.0)

    spread_dir = (
        "widened" if s.spread_30d_bps > 0
        else "narrowed" if s.spread_30d_bps < 0
        else "was unchanged"
    )

    rwa_density = (
        s.bl_rwa_m / s.current_loans_m * 100 if s.current_loans_m else 0.0
    )

    if s.bl_stage_2_rank is None or s.bl_count < 2:
        rank_text = ""
    elif s.bl_stage_2_rank == 1:
        rank_text = f" — the highest of the {s.bl_count} business lines"
    elif s.bl_stage_2_rank == s.bl_count:
        rank_text = f" — the lowest of the {s.bl_count} business lines"
    else:
        rank_text = (
            f" — ranked {s.bl_stage_2_rank} of {s.bl_count} business lines"
        )

    ld_label = (
        "lending exceeds deposits"
        if s.loan_to_deposit_ratio > 100
        else "deposit-funded"
    )

    s.kpi_cards = [
        {
            "label": "CREDIT QUALITY",
            "value": f"{bl_s2:.2f}%",
            "delta_pp": bl_s2_delta,
            "delta_unit": "pp",
            "delta_label": "over 30D",
            "context": (
                f"{bl} Stage 2 · Stage 3 {bl_s3:.2f}% · "
                f"{s.current_credit_watch_count} watch(es)"
            ),
            "module": "brief",
            "rag": rag(
                bl_s2, 8.0, 12.0,
                higher_is_better=False, unit="% in Stage 2",
            ),
            "why": (
                f"Weighted Stage 2 share for {bl} is {bl_s2:.2f}% of the "
                f"loan book, {bl_s2_delta:+.2f}pp over 30 days{rank_text}."
            ),
            "impact": (
                f"Stage 2 exposure in {bl} is roughly "
                f"€{s.current_loans_m * bl_s2 / 100 / 1000:,.1f}bn under "
                f"heightened monitoring, with Stage 3 at "
                f"€{s.current_loans_m * bl_s3 / 100 / 1000:,.1f}bn."
            ),
            "next": (
                f"Investigate {bl} migration drivers by country and sector "
                f"before adjusting provisioning."
            ),
        },
        {
            "label": "RISK-WEIGHTED ASSETS",
            "value": f"€{s.bl_rwa_m / 1000:,.1f}bn",
            "delta_pp": s.bl_rwa_30d_change_pct,
            "delta_unit": "%",
            "delta_label": "over 30D",
            "context": f"{bl} · RWA density {rwa_density:.0f}%",
            "module": "brief",
            "rag": rag(
                rwa_density, 55.0, 70.0,
                higher_is_better=False, unit="% density",
            ),
            "why": (
                f"{bl} holds €{s.bl_rwa_m / 1000:,.1f}bn of RWA against "
                f"€{s.current_loans_m / 1000:,.1f}bn of loans, giving a "
                f"{rwa_density:.1f}% density."
            ),
            "impact": (
                f"RWA moved {s.bl_rwa_30d_change_pct:+.2f}% over 30 days. "
                f"Higher density consumes more capital per unit of lending."
            ),
            "next": (
                f"Review {bl} RWA optimisation and portfolio rebalancing "
                f"options."
            ),
        },
        {
            "label": "NET INTEREST MARGIN",
            "value": f"{s.cert_current_nim:.2f}%",
            "delta_pp": s.nim_mom_bps,
            "delta_unit": "bps",
            "context": (
                f"{bl} · pricing spread "
                f"{s.spread_30d_bps:+.1f} bps over 30D"
            ),
            "module": "brief",
            "rag": rag(
                s.cert_current_nim, *NIM_RAG_PCT, unit="%", precision=2,
            ),
            "why": (
                f"The loan-versus-deposit pricing spread {spread_dir} by "
                f"{abs(s.spread_30d_bps):.1f} bps over 30 days for {bl}."
            ),
            "impact": (
                f"At {s.cert_current_nim:.2f}%, {bl} carries "
                f"€{s.current_loans_m / 1000:,.1f}bn of earning assets "
                f"generating €{s.cert_current_monthly_nii:,.0f}m of monthly "
                f"NII."
            ),
            "next": (
                f"Trace {bl} pricing drivers by country in Morning Brief."
            ),
        },
        {
            "label": "CORPORATE LOAN BOOK",
            "value": f"€{s.bl_corp_loan_m / 1000:,.1f}bn",
            "delta_pp": s.bl_corp_loan_30d_change_pct,
            "delta_unit": "%",
            "delta_label": "over 30D",
            "context": f"{bl} · L/D {s.loan_to_deposit_ratio:.1f}%",
            "module": "brief",
            "rag": rag(
                s.bl_corp_loan_30d_change_pct, -1.0, -3.0, unit="% 30D",
            ),
            "why": (
                f"{bl} corporate lending stands at "
                f"€{s.bl_corp_loan_m / 1000:,.1f}bn, against "
                f"€{s.current_deposits_m / 1000:,.1f}bn of deposits."
            ),
            "impact": (
                f"Loan book moved {s.bl_corp_loan_30d_change_pct:+.2f}% over "
                f"30 days. The L/D ratio of "
                f"{s.loan_to_deposit_ratio:.1f}% indicates {ld_label}."
            ),
            "next": (
                f"Review {bl} lending pipeline and credit concentration by "
                f"sector."
            ),
        },
    ]


def _build_generic_bl_kpi_explainers(s):
    """Fallback BL-specific headline cards: NIM, NII, deposit base, credit quality."""
    escape = html.escape
    bl = escape(s.business_line)

    # --- NIM ---
    spread_dir = (
        "widened" if s.spread_30d_bps > 0
        else "narrowed" if s.spread_30d_bps < 0
        else "was unchanged"
    )
    nii_change_pct = (
        s.monthly_nii_change_m
        / max(abs(s.cert_current_monthly_nii - s.monthly_nii_change_m), 1)
        * 100.0
    )

    # --- Credit ---
    bl_s2 = getattr(s, "bl_stage_2_pct", s.stage_2_share_pct)
    bl_s3 = getattr(s, "bl_stage_3_pct", s.stage_3_share_pct)
    bl_s2_delta = getattr(s, "bl_stage_2_delta_pp", 0.0)

    # --- Deposit detail text ---
    if s.deposit_leader is not None and s.deposit_laggard is not None:
        dep_context = (
            f"{escape(str(s.deposit_leader['country']))} leads "
            f"{safe_float(s.deposit_leader['deposit_change_30d_pct']):+.1f}%"
        )
    else:
        dep_context = "country detail unavailable"

    s.kpi_cards = [
        {
            "label": "NET INTEREST MARGIN",
            "value": f"{s.cert_current_nim:.2f}%",
            "delta_pp": s.nim_mom_bps,
            "delta_unit": "bps",
            "context": (
                f"{bl} · pricing spread {s.spread_30d_bps:+.1f} bps over 30D"
            ),
            "module": "brief",
            "rag": rag(s.cert_current_nim, *NIM_RAG_PCT, unit="%", precision=2),
            "why": (
                f"The loan-versus-deposit pricing spread {spread_dir} by "
                f"{abs(s.spread_30d_bps):.1f} bps over 30 days for {bl}."
            ),
            "impact": (
                f"At {s.cert_current_nim:.2f}%, {bl} carries "
                f"€{s.current_loans_m / 1000:,.1f}bn of earning assets "
                f"generating €{s.cert_current_monthly_nii:,.0f}m of monthly NII."
            ),
            "next": (
                f"Trace {bl} pricing drivers by country in Morning Brief."
            ),
        },
        {
            "label": "NET INTEREST INCOME",
            "value": f"€{s.cert_current_monthly_nii:,.0f}m",
            "delta_pp": s.monthly_nii_change_m,
            "delta_unit": "m",
            "context": (
                f"{bl} · {s.nii_basis_label}"
            ),
            "module": "brief",
            "rag": rag(nii_change_pct, 0.0, -3.0, unit="% MoM"),
            "why": (
                f"Monthly net interest income for {bl} on a "
                f"{s.nii_basis_label} basis. Average earning assets of "
                f"€{s.current_loans_m / 1000:,.1f}bn carried at a "
                f"{s.cert_current_nim:.2f}% margin."
            ),
            "impact": (
                f"€{s.cert_current_monthly_nii * 12 / 1000:,.2f}bn of annualised "
                f"NII at the current run rate for {bl}. The month-on-month move "
                f"is worth €{s.monthly_nii_change_m * 12:+,.0f}m a year if it holds."
            ),
            "next": (
                f"Compare {bl} NII against other business lines before "
                f"adjusting pricing."
            ),
        },
        {
            "label": "DEPOSIT BASE",
            "value": f"€{s.current_deposits_m / 1000:,.1f}bn",
            "delta_pp": s.total_deposit_30d_change_pct,
            "delta_unit": "%",
            "delta_label": "over 30D",
            "context": (
                f"{bl} · {dep_context}"
            ),
            "module": "treasury",
            "rag": rag(s.total_deposit_30d_change_pct, 0.0, -1.0, unit="% 30D"),
            "why": (
                f"{bl} deposits moved €{s.total_deposit_30d_change_m / 1000:+,.2f}bn "
                f"({s.total_deposit_30d_change_pct:+.2f}%) over the last 30 days."
            ),
            "impact": (
                f"€{s.current_deposits_m / 1000:,.1f}bn of {bl} deposits fund "
                f"€{s.current_loans_m / 1000:,.1f}bn of loans "
                f"(L/D {s.loan_to_deposit_ratio:.1f}%)."
            ),
            "next": (
                f"Review {bl} deposit pricing and country mix in Morning Brief."
            ),
        },
        {
            "label": "CREDIT QUALITY",
            "value": f"{bl_s2:.2f}%",
            "delta_pp": bl_s2_delta,
            "delta_unit": "pp",
            "delta_label": "over 30D",
            "context": (
                f"{bl} Stage 2 · Stage 3 {bl_s3:.2f}% · "
                f"{s.current_credit_watch_count} watch(es)"
            ),
            "module": "brief",
            "rag": rag(
                bl_s2, 8.0, 12.0,
                higher_is_better=False, unit="% in Stage 2",
            ),
            "why": (
                f"Weighted Stage 2 share for {bl} is {bl_s2:.2f}% of the "
                f"loan book, {bl_s2_delta:+.2f}pp over 30 days."
            ),
            "impact": (
                f"Stage 2 exposure in {bl} is roughly "
                f"€{s.current_loans_m * bl_s2 / 100 / 1000:,.1f}bn under "
                f"heightened monitoring."
            ),
            "next": (
                f"Investigate {bl} migration drivers by country before "
                f"adjusting provisioning."
            ),
        },
    ]


def _build_kpi_explainers(s):
    """
    The why / impact / next reading behind each executive KPI.

    When a business line is selected, the four headline cards switch to
    BL-relevant metrics (NIM, NII, deposits, credit quality) so the
    selection is immediately visible.
    """
    if s.business_line is not None:
        return _build_bl_kpi_explainers(s)

    escape = html.escape

    cet1_buffer_pp = s.cet1_ratio - REGULATORY_CET1_REQUIREMENT_PCT
    lcr_buffer_pp = s.lcr_ratio - REGULATORY_LCR_REQUIREMENT_PCT
    annualisation = (
        f"{s.months_observed} month{'s' if s.months_observed != 1 else ''} observed, "
        f"annualised"
    )

    s.kpi_cards = [
        {
            "label": "CET1 RATIO",
            "value": f"{s.cet1_ratio:.1f}%",
            "delta_pp": s.cet1_mom_pp,
            "context": (
                f"{s.cet1_peer_gap_pp:+.1f}pp vs peer median · "
                f"€{s.cet1_capital / 1000:.1f}bn CET1"
            ),
            "module": "brief",
            "rag": rag(s.cet1_ratio, 13.0, 11.5, unit="%"),
            "why": (
                f"CET1 capital of €{s.cet1_capital / 1000:.2f}bn {_direction(s.cet1_mom_pp)} "
                f"against €{s.latest_history['rwa_m'] / 1000:.1f}bn of risk-weighted assets, "
                f"moving the ratio {s.cet1_mom_pp:+.2f}pp since {s.previous_month_label}."
            ),
            "impact": (
                f"{cet1_buffer_pp:+.1f}pp of headroom over the "
                f"{REGULATORY_CET1_REQUIREMENT_PCT:.1f}% requirement, worth roughly "
                f"€{abs(cet1_buffer_pp) / 100 * s.latest_history['rwa_m'] / 1000:.1f}bn of "
                f"distributable capital, and {s.cet1_peer_gap_pp:+.1f}pp against the "
                f"{s.peer_count}-bank peer median."
            ),
            "next": (
                "Test the buffer against the stressed capital paths in What-If before "
                "committing to distribution or RWA growth."
            ),
        },
        {
            "label": "LIQUIDITY COVERAGE",
            "value": f"{s.lcr_ratio:.1f}%",
            "delta_pp": s.lcr_mom_pp,
            "context": (
                f"HQLA €{s.hqla / 1000:.1f}bn · "
                f"L/D {s.loan_to_deposit_ratio:.1f}%"
            ),
            "module": "treasury",
            "rag": rag(s.lcr_ratio, 130.0, 110.0, unit="%", precision=0),
            "why": (
                f"€{s.hqla / 1000:.1f}bn of high-quality liquid assets against 30-day net "
                f"outflows, while the deposit base moved "
                f"€{s.total_deposit_30d_change_m / 1000:+.2f}bn over the last 30 days."
            ),
            "impact": (
                f"{lcr_buffer_pp:+.1f}pp over the "
                f"{REGULATORY_LCR_REQUIREMENT_PCT:.0f}% minimum. Loan-to-deposit at "
                f"{s.loan_to_deposit_ratio:.1f}% sets how much further lending the "
                f"current funding base can carry."
            ),
            "next": (
                "Check the funding and hedge position in Treasury, and the slowest "
                "deposit markets in Morning Brief."
            ),
        },
        {
            "label": "ANNUALISED YTD ROE PROXY",
            "value": f"{s.ytd_roe_proxy:.1f}%",
            "delta_pp": s.ytd_roe_delta_pp,
            "context": (
                f"{s.roe_peer_gap_pp:+.1f}pp vs peer median · directional comparison"
            ),
            "module": "peers",
            "rag": rag(s.ytd_roe_proxy, 10.0, 6.0, unit="%"),
            "why": (
                f"Year-to-date net profit over average CET1 capital "
                f"({annualisation}). Net interest margin is "
                f"{s.cert_current_nim:.2f}% and {s.nim_mom_bps:+.1f} bps month on month, "
                f"which is the largest single driver."
            ),
            "impact": (
                f"{abs(s.roe_peer_gap_pp):.1f}pp "
                f"{'above' if s.roe_peer_gap_pp >= 0 else 'below'} the peer median. "
                f"A proxy on CET1 "
                f"rather than reported equity, so it is directional: use it to rank "
                f"movement, not to state a reported return."
            ),
            "next": (
                "Compare the return and its drivers against the peer set in Peer "
                "Benchmarking before setting a target."
            ),
        },
        {
            "label": "YTD COST / INCOME",
            "value": f"{s.ytd_cost_income:.1f}%",
            "delta_pp": s.ytd_ci_delta_pp,
            "context": (
                f"{s.efficiency_peer_advantage_pp:+.1f}pp efficiency advantage vs peer median"
            ),
            "module": "peers",
            "lower_is_better": True,
            "rag": rag(s.ytd_cost_income, 55.0, 65.0, higher_is_better=False, unit="%"),
            "why": (
                f"Year-to-date operating costs over operating income across "
                f"{annualisation.split(',')[0]}. The ratio {_direction(s.ytd_ci_delta_pp)} "
                f"{abs(s.ytd_ci_delta_pp):.1f}pp since {s.previous_month_label}; a rising "
                f"ratio means costs are outpacing income."
            ),
            "impact": (
                f"{abs(s.efficiency_peer_advantage_pp):.1f}pp "
                f"{'better' if s.efficiency_peer_advantage_pp >= 0 else 'worse'} than the "
                f"peer median. One point of cost/income is roughly "
                f"€{s.ytd_operating_income / max(s.months_observed, 1) * 12 / 100:,.0f}m of "
                f"annualised operating income at the current run rate."
            ),
            "next": (
                "Hold the efficiency gap against the peer quadrant before approving "
                "new cost commitments."
            ),
        },
    ]

    for card in s.kpi_cards:
        for field in ("why", "impact", "next"):
            card[field] = escape(card[field])


def _build_narrative(s):
    """Attach the change / why / impact / next copy the HUD panels render."""
    escape = html.escape

    # --- Margin -------------------------------------------------
    s.nim_signal_primary = f"NIM {s.cert_current_nim:.2f}% / {s.nim_mom_bps:+.1f} bps MoM"
    s.nim_signal_secondary = (
        f"Monthly NII €{s.cert_current_monthly_nii:,.0f}m ({s.nii_basis_label}) · "
        f"pricing spread {s.spread_30d_bps:+.1f} bps over 30D"
    )
    spread_direction = (
        "widened"
        if s.spread_30d_bps > 0
        else "narrowed"
        if s.spread_30d_bps < 0
        else "was unchanged"
    )
    s.nim_why = (
        f"Loan-versus-deposit pricing spread {spread_direction} by "
        f"{abs(s.spread_30d_bps):.1f} bps over 30D."
    )
    s.nim_impact = (
        f"Monthly NII run rate is €{s.cert_current_monthly_nii:,.0f}m "
        f"({s.monthly_nii_change_m:+,.0f}m vs prior month, {s.nii_basis_label})."
    )
    s.nim_next = (
        "Inspect country and business-line pricing/pass-through drivers in "
        "Morning Brief or Copilot."
    )

    # --- Funding ------------------------------------------------
    if s.deposit_leader is not None and s.deposit_laggard is not None:
        s.deposit_signal_primary = (
            f"{s.total_deposit_30d_change_pct:+.2f}% / "
            f"€{s.total_deposit_30d_change_m / 1000:+.2f}bn over 30D"
        )
        s.deposit_signal_secondary = (
            f"{escape(str(s.deposit_leader['country']))} leads "
            f"{safe_float(s.deposit_leader['deposit_change_30d_pct']):+.1f}% · "
            f"{escape(str(s.deposit_laggard['country']))} lowest "
            f"{safe_float(s.deposit_laggard['deposit_change_30d_pct']):+.1f}%"
        )
        s.deposit_why = (
            f"Growth is uneven: {escape(str(s.deposit_leader['country']))} leads "
            f"while {escape(str(s.deposit_laggard['country']))} is slowest."
        )
    else:
        s.deposit_signal_primary = "Deposit movement unavailable"
        s.deposit_signal_secondary = "No latest country deposit observation"
        s.deposit_why = "No country-level deposit observation is available."

    s.deposit_impact = (
        f"Funding base changed by €{s.total_deposit_30d_change_m / 1000:+.2f}bn over 30D."
    )
    s.deposit_next = (
        "Review slower-growth markets and business lines before changing deposit pricing."
    )

    # --- Credit -------------------------------------------------
    if s.credit_hotspot is not None:
        delta_text = (
            "30D comparison unavailable"
            if s.credit_hotspot_stage2_delta_pp is None
            else f"{s.credit_hotspot_stage2_delta_pp:+.2f}pp vs 30D"
        )
        s.credit_signal_primary = (
            f"{escape(str(s.credit_hotspot['country']))} / "
            f"{escape(str(s.credit_hotspot['business_line']))} Stage 2 "
            f"{safe_float(s.credit_hotspot['weighted_stage_2_share_pct']):.1f}%"
        )
        s.credit_signal_secondary = (
            f"{delta_text} · {s.current_credit_watch_count} current watch(es)"
        )
        s.credit_impact = (
            f"Stage 2 is "
            f"{safe_float(s.credit_hotspot['weighted_stage_2_share_pct']):.1f}%"
        )
    else:
        s.credit_signal_primary = "Credit movement unavailable"
        s.credit_signal_secondary = "No latest credit observation"
        s.credit_impact = "Credit impact unavailable"

    s.credit_why = (
        "Stage 2 concentration is highest in the identified country/business line; "
        "the data does not establish the underlying cause."
    )
    s.credit_next = (
        "Investigate migration drivers and provisioning exposure before taking action."
    )

    # --- External news ------------------------------------------
    if s.top_news is not None:
        s.news_signal_primary = escape(clip_ui_text(s.top_news["headline"], 58))
        s.news_signal_secondary = (
            f"{escape(str(s.top_news['source']))} · potential metric: "
            f"{escape(str(s.top_news['primary_affected_metric']))}"
        )
        s.news_why = escape(
            clip_ui_text(s.top_news.get("bank_impact_summary", ""), 120)
        )
        s.news_impact = escape(str(s.top_news["primary_affected_metric"]))
        s.news_next = escape(clip_ui_text(s.top_news.get("suggested_action", ""), 105))
    else:
        s.news_signal_primary = "External intelligence unavailable"
        s.news_signal_secondary = "No recent public-source item in the window"
        s.news_why = "No current external-development context available."
        s.news_impact = "—"
        s.news_next = "Review the external-intelligence feed when new items arrive."

    # Margin, funding and credit: the three movements the brief opens on.
    s.executive_change_count = 3


# ------------------------------------------------------------------
# Domain grid — the executive readout behind Morning Brief
# ------------------------------------------------------------------

def _pct_change(now, before):
    """Percentage movement, or None when there is no comparable base."""
    now = safe_float(now)
    before = safe_float(before)
    if not before:
        return None
    return (now - before) / abs(before) * 100.0


def _movement(value, unit="pp", lower_is_better=False):
    """Arrow, magnitude and the tone class a KPI tile renders."""
    arrow = "↑" if value > 0 else "↓" if value < 0 else "→"
    magnitude = abs(value)
    precision = 2 if 0 < magnitude < 0.1 else 1
    improving = (value < 0) if lower_is_better else (value > 0)
    tone = "is-flat" if value == 0 else "is-up" if improving else "is-down"
    return f"{arrow} {magnitude:,.{precision}f}{unit}", tone


def _tile(label, value, delta_text, tone, why, impact, next_copy, topic, reading):
    return {
        "label": label,
        "value": value,
        "delta": delta_text,
        "tone": tone,
        "why": why,
        "impact": impact,
        "next": next_copy,
        "topic": topic,
        "rag": reading,
    }


def _loan_book_30d(business_line=None):
    """
    Loan book now and 30 days ago, bank-wide and by business line.

    The daily signal table is the only source that carries the loan book past
    the certified month-end close, so the 30-day comparison is taken there and
    on the same basis on both sides of the window.
    """
    detail = views.cfo_daily_business_country(business_line=business_line)
    if detail is None or detail.empty:
        return None

    latest_date = detail["date"].max()
    prior_date = latest_date - pd.Timedelta(days=CREDIT_LOOKBACK_DAYS)
    if prior_date not in set(detail["date"]):
        return None

    def _by_line(on_date):
        return detail[detail["date"] == on_date].groupby(
            "business_line", as_index=False
        )["interest_earning_assets_m"].sum()

    now, before = _by_line(latest_date), _by_line(prior_date)
    merged = now.merge(before, on="business_line", suffixes=("_now", "_before"))
    if merged.empty:
        return None

    merged["change_m"] = (
        merged["interest_earning_assets_m_now"]
        - merged["interest_earning_assets_m_before"]
    )
    merged["change_pct"] = (
        100.0
        * merged["change_m"]
        / merged["interest_earning_assets_m_before"].replace(0, pd.NA)
    ).astype(float)
    merged = merged.sort_values("change_pct", ascending=False)

    total_now = float(merged["interest_earning_assets_m_now"].sum())
    total_before = float(merged["interest_earning_assets_m_before"].sum())

    return {
        "total_now_m": total_now,
        "total_before_m": total_before,
        "change_m": total_now - total_before,
        "change_pct": _pct_change(total_now, total_before) or 0.0,
        "leader": merged.iloc[0],
        "laggard": merged.iloc[-1],
    }


def _earnings_tiles(s):
    """Domain 01 — what the bank earned and what it cost to earn it."""
    annual_nii_m = s.cert_current_monthly_nii * 12.0
    annual_nii_change_m = s.monthly_nii_change_m * 12.0
    nii_delta, nii_tone = _movement(s.monthly_nii_change_m, "m")
    ci_delta, ci_tone = _movement(s.ytd_ci_delta_pp, "pp", lower_is_better=True)
    nim_delta, nim_tone = _movement(s.nim_mom_bps, "bps")

    monthly_income = s.ytd_operating_income / max(s.months_observed, 1)
    one_point_of_ci_m = monthly_income * 12.0 / 100.0
    ytd_costs_m = s.ytd_operating_income * s.ytd_cost_income / 100.0
    nii_change_pct = (
        _pct_change(
            s.cert_current_monthly_nii,
            s.cert_current_monthly_nii - s.monthly_nii_change_m,
        )
        or 0.0
    )

    return [
        _tile(
            "Net interest margin",
            f"{s.cert_current_nim:.2f}%",
            f"{nim_delta} vs {s.previous_month_label}",
            nim_tone,
            s.nim_why,
            s.nim_impact,
            s.nim_next,
            "nim",
            rag(s.cert_current_nim, *NIM_RAG_PCT, unit="%", precision=2),
        ),
        _tile(
            "Net interest income",
            f"€{s.cert_current_monthly_nii:,.0f}m",
            f"{nii_delta} vs {s.previous_month_label}",
            nii_tone,
            (
                f"Monthly net interest income on a {s.nii_basis_label} basis: "
                f"average earning assets of "
                f"€{s.cert_current_monthly_nii * 1200.0 / max(s.cert_current_nim, 0.01) / 1000:,.1f}bn "
                f"carried at a {s.cert_current_nim:.2f}% margin. The observed "
                f"loan-versus-deposit pricing spread moved "
                f"{s.spread_30d_bps:+.1f} bps over 30 days."
            ),
            (
                f"€{annual_nii_m / 1000:,.2f}bn of annualised net interest income at "
                f"the current run rate. The month-on-month move is worth "
                f"€{annual_nii_change_m:+,.0f}m a year if it holds."
            ),
            (
                "Trace the margin into country and business-line pricing before "
                "reading the run rate as a forecast."
            ),
            "nim",
            rag(nii_change_pct, 0.0, -3.0, unit="% MoM"),
        ),
        _tile(
            "Cost / income ratio",
            f"{s.ytd_cost_income:.1f}%",
            f"{ci_delta} vs prior YTD",
            ci_tone,
            (
                f"Year-to-date operating costs of €{ytd_costs_m:,.0f}m "
                f"against €{s.ytd_operating_income:,.0f}m of operating income over "
                f"{s.months_observed} month{'s' if s.months_observed != 1 else ''}. "
                f"The ratio {_direction(s.ytd_ci_delta_pp)} "
                f"{abs(s.ytd_ci_delta_pp):.2f}pp since {s.previous_month_label}."
            ),
            (
                f"One point of cost/income is roughly €{one_point_of_ci_m:,.0f}m of "
                f"annualised operating income at the current run rate, and the ratio "
                f"sits {abs(s.efficiency_peer_advantage_pp):.1f}pp "
                f"{'better' if s.efficiency_peer_advantage_pp >= 0 else 'worse'} than the "
                f"{s.peer_count}-bank peer median."
            ),
            (
                "Hold the efficiency gap against the peer quadrant before approving "
                "new cost commitments."
            ),
            "efficiency",
            rag(s.ytd_cost_income, 55.0, 65.0, higher_is_better=False, unit="%"),
        ),
    ]


def _balance_sheet_tiles(s):
    """Domain 02 — the funding base, the loan book and the gap between them."""
    deposit_total_m = (
        float(s.deposit_country["deposit_balance_m"].sum())
        if s.deposit_country is not None and not s.deposit_country.empty
        else s.current_deposits_m
    )
    deposit_delta, deposit_tone = _movement(s.total_deposit_30d_change_pct, "%")

    ltd_prior = safe_float(
        s.previous_history["loan_to_deposit_pct"], s.loan_to_deposit_ratio
    )
    ltd_delta_pp = s.loan_to_deposit_ratio - ltd_prior
    ltd_delta, ltd_tone = _movement(ltd_delta_pp, "pp", lower_is_better=True)
    funding_headroom_m = deposit_total_m - s.current_loans_m

    loans = _loan_book_30d(business_line=s.business_line_data)

    if loans is None:
        loan_growth_mom_pct = safe_float(s.latest_history["loan_growth_mom_pct"])
        loan_tile = _tile(
            "Loan book",
            f"€{s.current_loans_m / 1000:,.1f}bn",
            f"{_movement(loan_growth_mom_pct, '%')[0]} MoM",
            _movement(loan_growth_mom_pct, "%")[1],
            (
                "The daily signal table does not reach 30 days back, so the loan "
                "book is read at the certified month-end close."
            ),
            (
                f"€{s.current_loans_m / 1000:,.1f}bn of loans against "
                f"€{s.current_deposits_m / 1000:,.1f}bn of deposits at the close."
            ),
            "Open the funding view once the daily window is long enough to compare.",
            "balance_sheet",
            rag(loan_growth_mom_pct, 0.0, -1.0, unit="% MoM"),
        )
    else:
        loan_delta, loan_tone = _movement(loans["change_pct"], "%")
        leader, laggard = loans["leader"], loans["laggard"]
        loan_tile = _tile(
            "Loan book",
            f"€{loans['total_now_m'] / 1000:,.1f}bn",
            f"{loan_delta} over 30D",
            loan_tone,
            (
                f"Growth is uneven across the book: {leader['business_line']} leads at "
                f"{leader['change_pct']:+.2f}% while {laggard['business_line']} is "
                f"slowest at {laggard['change_pct']:+.2f}% over 30 days."
            ),
            (
                f"The loan book moved €{loans['change_m'] / 1000:+,.2f}bn over 30 days. "
                f"At the current {safe_float(s.latest_history['rwa_m']) / max(safe_float(s.latest_history['total_assets_m']), 1) * 100:.1f}% "
                f"RWA density that lending consumes roughly "
                f"€{abs(loans['change_m']) * safe_float(s.latest_history['rwa_m']) / max(safe_float(s.latest_history['total_assets_m']), 1) / 1000:,.2f}bn "
                f"of risk-weighted assets."
            ),
            (
                "Check whether the fastest-growing segment is priced for the capital "
                "it consumes before extending the book further."
            ),
            "balance_sheet",
            rag(loans["change_pct"], 0.0, -1.0, unit="% 30D"),
        )

    return [
        _tile(
            "Deposit base",
            f"€{deposit_total_m / 1000:,.1f}bn",
            f"{deposit_delta} over 30D",
            deposit_tone,
            s.deposit_why,
            s.deposit_impact,
            s.deposit_next,
            "deposits",
            rag(s.total_deposit_30d_change_pct, 0.0, -1.0, unit="% 30D"),
        ),
        loan_tile,
        _tile(
            "Loan-to-deposit ratio",
            f"{s.loan_to_deposit_ratio:.1f}%",
            f"{ltd_delta} vs {s.previous_month_label}",
            ltd_tone,
            (
                f"€{s.current_loans_m / 1000:,.1f}bn of loans against "
                f"€{deposit_total_m / 1000:,.1f}bn of deposits. The ratio "
                f"{_direction(ltd_delta_pp)} {abs(ltd_delta_pp):.2f}pp since "
                f"{s.previous_month_label}."
            ),
            (
                f"€{funding_headroom_m / 1000:,.1f}bn of deposits sit above the loan "
                f"book, which is what the current funding base can carry before "
                f"lending has to be funded in the market."
                if funding_headroom_m >= 0
                else f"The loan book runs €{abs(funding_headroom_m) / 1000:,.1f}bn ahead "
                f"of deposits, so that share of lending is funded in the market."
            ),
            (
                "Review the funding and hedge position in Treasury before committing "
                "the remaining deposit headroom to new lending."
            ),
            "balance_sheet",
            rag(
                s.loan_to_deposit_ratio, 90.0, 100.0,
                higher_is_better=False, unit="%", precision=0,
            ),
        ),
    ]


def _capital_tiles(s):
    """Domain 03 — capital and liquidity, read against their requirements."""
    cet1_card, lcr_card = s.kpi_cards[0], s.kpi_cards[1]

    cet1_delta, cet1_tone = _movement(s.cet1_mom_pp, "pp")
    lcr_delta, lcr_tone = _movement(s.lcr_mom_pp, "pp")

    total_capital_prior = safe_float(
        s.previous_history["total_capital_ratio_pct"], s.total_capital_ratio
    )
    tc_delta_pp = s.total_capital_ratio - total_capital_prior
    tc_delta, tc_tone = _movement(tc_delta_pp, "pp")

    own_funds_m = (
        safe_float(s.latest_history["cet1_capital_m"])
        + safe_float(s.latest_history["at1_capital_m"])
        + safe_float(s.latest_history["tier2_capital_m"])
    )
    rwa_m = safe_float(s.latest_history["rwa_m"])

    return [
        _tile(
            "CET1 ratio",
            f"{s.cet1_ratio:.2f}%",
            f"{cet1_delta} vs {s.previous_month_label}",
            cet1_tone,
            cet1_card["why"],
            cet1_card["impact"],
            cet1_card["next"],
            "capital",
            cet1_card["rag"],
        ),
        _tile(
            "Liquidity coverage ratio",
            f"{s.lcr_ratio:.1f}%",
            f"{lcr_delta} vs {s.previous_month_label}",
            lcr_tone,
            lcr_card["why"],
            lcr_card["impact"],
            lcr_card["next"],
            "liquidity",
            lcr_card["rag"],
        ),
        _tile(
            "Total capital ratio",
            f"{s.total_capital_ratio:.2f}%",
            f"{tc_delta} vs {s.previous_month_label}",
            tc_tone,
            (
                f"€{own_funds_m / 1000:,.2f}bn of total own funds — CET1, AT1 and "
                f"Tier 2 — against €{rwa_m / 1000:,.1f}bn of risk-weighted assets. "
                f"The AT1 and Tier 2 layers add "
                f"{s.total_capital_ratio - s.cet1_ratio:.2f}pp above the CET1 ratio."
            ),
            (
                f"€{(own_funds_m - safe_float(s.latest_history['cet1_capital_m'])) / 1000:,.2f}bn "
                f"of the stack is non-CET1 capital, which absorbs loss after CET1 and "
                f"is the cheaper layer to refill if risk-weighted assets grow."
            ),
            (
                "Test the total-capital path alongside CET1 in What-If before pricing "
                "new issuance."
            ),
            "capital",
            rag(s.total_capital_ratio, 17.0, 14.5, unit="%"),
        ),
    ]


def _risk_tiles(s):
    """Domain 04 — the exposure the balance sheet carries and what it is covered by."""
    latest, previous = s.latest_history, s.previous_history

    provisions_m = safe_float(latest["provisions_m"])
    provisions_prior_m = safe_float(previous["provisions_m"])
    gca_m = safe_float(latest["gross_carrying_amount_m"])
    gca_prior_m = safe_float(previous["gross_carrying_amount_m"])
    ead_m = safe_float(latest["ead_m"])
    ead_prior_m = safe_float(previous["ead_m"])
    rwa_m = safe_float(latest["rwa_m"])
    rwa_prior_m = safe_float(previous["rwa_m"])
    total_assets_m = safe_float(latest["total_assets_m"])
    cet1_capital_m = safe_float(latest["cet1_capital_m"])

    coverage_pct = provisions_m / gca_m * 100.0 if gca_m else 0.0
    coverage_prior_pct = (
        provisions_prior_m / gca_prior_m * 100.0 if gca_prior_m else coverage_pct
    )
    rwa_density_pct = rwa_m / total_assets_m * 100.0 if total_assets_m else 0.0
    ead_uplift_pct = (ead_m / gca_m - 1.0) * 100.0 if gca_m else 0.0
    stage_2_exposure_m = gca_m * s.stage_2_share_pct / 100.0
    stage_3_exposure_m = gca_m * s.stage_3_share_pct / 100.0

    # A pure RWA move, holding CET1 capital still: this is the capital cost of
    # the quarter's balance-sheet growth, separated from capital generation.
    cet1_from_rwa_pp = (
        (cet1_capital_m / rwa_m - cet1_capital_m / rwa_prior_m) * 100.0
        if rwa_m and rwa_prior_m
        else 0.0
    )

    prov_delta, _ = _movement(_pct_change(provisions_m, provisions_prior_m) or 0.0, "%")
    # The allowance on its own is neither good nor bad; what it is worth is the
    # cover it gives the book, so the tile takes its tone from coverage.
    _, prov_tone = _movement(coverage_pct - coverage_prior_pct, "pp")
    ead_delta, ead_tone = _movement(
        _pct_change(ead_m, ead_prior_m) or 0.0, "%", lower_is_better=True
    )
    gca_delta, gca_tone = _movement(_pct_change(gca_m, gca_prior_m) or 0.0, "%")
    rwa_delta, rwa_tone = _movement(
        _pct_change(rwa_m, rwa_prior_m) or 0.0, "%", lower_is_better=True
    )

    provisions_rag = (
        rag(provisions_m / stage_3_exposure_m * 100.0, 60.0, 45.0,
            unit="% of Stage 3", precision=0)
        if stage_3_exposure_m
        else rag(coverage_pct, 1.5, 1.0, unit="% of GCA")
    )

    return [
        _tile(
            "Provisions",
            f"€{provisions_m / 1000:,.2f}bn",
            f"{prov_delta} vs {s.previous_month_label}",
            prov_tone,
            (
                f"€{provisions_m / 1000:,.2f}bn of loan-loss allowance against "
                f"€{gca_m / 1000:,.1f}bn of gross carrying amount — a coverage ratio "
                f"of {coverage_pct:.2f}%, {coverage_pct - coverage_prior_pct:+.2f}pp "
                f"versus {s.previous_month_label}. The month's provision charge was "
                f"€{safe_float(latest['provision_charge_m']):,.0f}m."
            ),
            (
                f"Stage 3 exposure is €{stage_3_exposure_m / 1000:,.2f}bn at "
                f"{s.stage_3_share_pct:.2f}% of the book, so the allowance stands at "
                f"{provisions_m / stage_3_exposure_m * 100.0:.0f}% of it."
                if stage_3_exposure_m
                else f"Coverage stands at {coverage_pct:.2f}% of gross carrying amount."
            ),
            (
                "Check whether coverage is falling because exposure improved or "
                "because the charge was released, before reading it as good news."
            ),
            "credit",
            provisions_rag,
        ),
        _tile(
            "Exposure at default",
            f"€{ead_m / 1000:,.1f}bn",
            f"{ead_delta} vs {s.previous_month_label}",
            ead_tone,
            (
                f"€{ead_m / 1000:,.1f}bn of exposure at default against "
                f"€{gca_m / 1000:,.1f}bn drawn, so undrawn commitments and credit "
                f"conversion add {ead_uplift_pct:+.1f}% on top of the drawn book."
            ),
            (
                f"Risk weights apply to EAD, not to the drawn balance: at the current "
                f"{rwa_m / ead_m * 100.0:.1f}% average weight, "
                f"€{(ead_m - ead_prior_m) / 1000:+,.2f}bn of EAD movement is worth "
                f"€{(ead_m - ead_prior_m) * rwa_m / ead_m / 1000:+,.2f}bn of RWA."
                if ead_m
                else "No comparable exposure base is available."
            ),
            (
                "Review committed-but-undrawn lines alongside the drawn book before "
                "sizing new limits."
            ),
            "credit",
            rag(
                _pct_change(ead_m, ead_prior_m) or 0.0, 1.0, 2.5,
                higher_is_better=False, unit="% MoM",
            ),
        ),
        _tile(
            "Gross carrying amount",
            f"€{gca_m / 1000:,.1f}bn",
            f"{gca_delta} vs {s.previous_month_label}",
            gca_tone,
            (
                f"€{gca_m / 1000:,.1f}bn of gross loans before allowance. "
                f"Stage 1 holds {safe_float(latest['stage_1_share_pct']):.1f}%, "
                f"Stage 2 {s.stage_2_share_pct:.2f}% and Stage 3 "
                f"{s.stage_3_share_pct:.2f}% of the book."
            ),
            (
                f"€{stage_2_exposure_m / 1000:,.1f}bn sits in Stage 2 under heightened "
                f"monitoring — the population that would carry a lifetime expected-loss "
                f"charge if it migrated to Stage 3."
            ),
            (
                "Open the credit lens for the country and business line carrying the "
                "highest Stage 2 concentration."
            ),
            "credit",
            rag(
                s.stage_2_share_pct, 8.0, 12.0,
                higher_is_better=False, unit="% in Stage 2",
            ),
        ),
        _tile(
            "Risk-weighted assets",
            f"€{rwa_m / 1000:,.1f}bn",
            f"{rwa_delta} vs {s.previous_month_label}",
            rwa_tone,
            (
                f"€{rwa_m / 1000:,.1f}bn of risk-weighted assets on "
                f"€{total_assets_m / 1000:,.1f}bn of total assets — an RWA density of "
                f"{rwa_density_pct:.1f}%. RWA moved "
                f"€{(rwa_m - rwa_prior_m) / 1000:+,.2f}bn since "
                f"{s.previous_month_label}."
            ),
            (
                f"Holding CET1 capital still, that RWA movement alone is worth "
                f"{cet1_from_rwa_pp:+.2f}pp of CET1 ratio; the ratio actually moved "
                f"{s.cet1_mom_pp:+.2f}pp, so capital generation accounts for the "
                f"remaining {s.cet1_mom_pp - cet1_from_rwa_pp:+.2f}pp."
            ),
            (
                "Stress the RWA path in What-If before committing the CET1 buffer to "
                "growth or distribution."
            ),
            "capital",
            rag(
                _pct_change(rwa_m, rwa_prior_m) or 0.0, 1.0, 2.0,
                higher_is_better=False, unit="% MoM",
            ),
        ),
    ]


def _build_domain_grid(s):
    """
    The four supervisory domains the executive view opens on.

    Every tile carries the same reading the decision lenses use — the number,
    what moved it, what it is worth, and the one thing to do next — so the grid
    replaces a ratio wall with something a CFO can act on.
    """
    escape = html.escape

    s.domain_grid = [
        {
            "name": "Earnings",
            "metrics": "NII · NIM · cost / income",
            "tiles": _earnings_tiles(s),
        },
        {
            "name": "Balance sheet",
            "metrics": "Deposits · loans · funding mix",
            "tiles": _balance_sheet_tiles(s),
        },
        {
            "name": "Capital & Liquidity",
            "metrics": "CET1 · LCR · total capital",
            "tiles": _capital_tiles(s),
        },
        {
            "name": "Risk & Asset Quality",
            "metrics": "Provisions · EAD · GCA · RWA",
            "tiles": _risk_tiles(s),
        },
    ]

    # Some copy is reused from the narrative and KPI builders, which escape as
    # they go. Unescaping first makes the pass idempotent, so a reused string is
    # never double-escaped into visible entities.
    for domain in s.domain_grid:
        for field in ("name", "metrics"):
            domain[field] = escape(domain[field])

        for index, tile in enumerate(domain["tiles"], start=1):
            for field in ("label", "value", "delta"):
                tile[field] = escape(tile[field])

            tile["index"] = index
            for field in ("why", "impact", "next"):
                tile[field] = html.unescape(tile[field])
            tile["why_short"] = escape(clip_ui_text(tile["why"], 150))
            for field in ("why", "impact", "next"):
                tile[field] = escape(tile[field])


# ------------------------------------------------------------------
# Prediction confidence
# ------------------------------------------------------------------

def _robust_sigma(values):
    """
    1.4826 × the median absolute deviation.

    A standard-deviation estimate that one outlier month cannot set on its
    own, which matters with only a handful of monthly observations.
    """
    series = pd.Series(values, dtype=float).dropna()
    if len(series) < 2:
        return 0.0
    return 1.4826 * float((series - series.median()).abs().median())


def _full_months(monthly_nim):
    """Monthly rows with every day observed; the open month is noisier."""
    frame = monthly_nim.dropna(subset=["nim_pct"]).sort_values("month")
    days_in_month = pd.to_datetime(frame["month"]).dt.days_in_month
    return frame[frame["days_observed"] >= days_in_month]


def _build_predictions(s):
    """
    A confidence level for every forward-looking number the cockpit shows.

    The Horizon error is treated as a random walk: each projected month adds
    a surprise drawn from the observed month-to-month moves, so the spread
    grows with the square root of the months ahead. Confidence is then the
    probability of landing within a tolerance a CFO would still call "on the
    projection".
    """
    full = _full_months(s.monthly_nim)
    nim_sigma_bps = _robust_sigma(full["nim_pct"].diff() * 100.0)
    nii_sigma_m = _robust_sigma(full["monthly_nii_m"].diff())
    growth_sigma_pp = _robust_sigma(
        full["avg_interest_earning_assets_m"].pct_change() * 100.0
    )

    baseline = s.horizon_baseline.copy()
    months_ahead = (
        int((baseline["series"] == "Baseline").sum()) if not baseline.empty else 0
    )

    s.conf_horizon_first_step = confidence_within(
        nim_sigma_bps, NIM_TOLERANCE_BPS, f"±{NIM_TOLERANCE_BPS:.0f} bps"
    )
    s.conf_horizon_first_step["basis"] += (
        f" one month out (month-to-month σ {nim_sigma_bps:.0f} bps)"
    )

    s.conf_horizon_ye_nim = confidence_within(
        nim_sigma_bps * math.sqrt(max(months_ahead, 1)),
        NIM_TOLERANCE_BPS,
        f"±{NIM_TOLERANCE_BPS:.0f} bps",
    )
    s.conf_horizon_ye_nim["basis"] += (
        f" {months_ahead} months out (σ {nim_sigma_bps:.0f} bps per month, "
        f"compounding)"
    )

    # The FY figure is mostly booked actuals; only the projected months carry
    # error, and a random-walk level error sums to σ·√(n(n+1)(2n+1)/6).
    n = months_ahead
    nii_sum_sigma_m = nii_sigma_m * math.sqrt(n * (n + 1) * (2 * n + 1) / 6.0)
    nii_tolerance_m = FY_NII_TOLERANCE_PCT / 100.0 * s.horizon_full_year_nii_m
    s.conf_horizon_fy_nii = confidence_within(
        nii_sum_sigma_m,
        nii_tolerance_m,
        f"±{FY_NII_TOLERANCE_PCT:.0f}% (€{nii_tolerance_m:,.0f}m)",
    )
    s.conf_horizon_fy_nii["basis"] += (
        f" of the FY baseline ({s.months_observed} months already booked)"
    )

    s.conf_horizon_balance_sheet = confidence_within(
        growth_sigma_pp,
        ASSET_GROWTH_TOLERANCE_PP,
        f"±{ASSET_GROWTH_TOLERANCE_PP:.2f}pp",
    )
    s.conf_horizon_balance_sheet["basis"] += (
        f" of the monthly run rate (σ {growth_sigma_pp:.2f}pp per month)"
    )

    # Each projected month carries its own band and confidence on the chart.
    if not baseline.empty:
        steps = (baseline["series"] == "Baseline").cumsum().where(
            baseline["series"] == "Baseline"
        )
        sigma_pp = nim_sigma_bps * steps.pow(0.5) / 100.0
        baseline["nim_low_pct"] = baseline["nim_pct"] - 1.645 * sigma_pp
        baseline["nim_high_pct"] = baseline["nim_pct"] + 1.645 * sigma_pp
        baseline["confidence_pct"] = [
            None
            if pd.isna(sigma)
            else confidence_within(
                sigma * 100.0, NIM_TOLERANCE_BPS, ""
            )["pct"]
            for sigma in sigma_pp
        ]
    s.horizon_baseline = baseline
    s.nim_sigma_bps = nim_sigma_bps

    # Treasury: the +50bp figure is a revaluation, so its confidence is about
    # the method. The convexity share says how far a linear reading would miss.
    scenarios = s.treasury_scenarios
    pure = scenarios[scenarios["credit_spread_shock_bps"].fillna(0).abs() < 0.001]
    ev_by_shock = pure.groupby("rate_shock_bps")["economic_value_impact_m"].sum()

    if 25 in ev_by_shock.index and 50 in ev_by_shock.index and ev_by_shock[50]:
        convexity_share = abs(ev_by_shock[50] - 2.0 * ev_by_shock[25]) / abs(
            ev_by_shock[50]
        )
        level = HIGH if convexity_share < 0.05 else MEDIUM if convexity_share < 0.15 else LOW
        s.conf_treasury_rate50 = confidence_fixed(
            level,
            f"Full revaluation of a parallel shift; convexity is "
            f"{convexity_share:.1%} of the move. Curve twists and spread moves "
            f"are not captured.",
        )
    else:
        s.conf_treasury_rate50 = confidence_fixed(
            MEDIUM, "No +25bp scenario to check the revaluation's linearity against."
        )

    s.conf_hedges = confidence_fixed(
        MEDIUM,
        "Simplified DV01 hedge estimate; basis, curve and carry-path risk are "
        "not modelled.",
    )

    # Strategy: how likely the #1 rank survives the scoring noise.
    noise = STRATEGY_SCORE_NOISE_PTS
    s.conf_strategy_rank = (
        confidence_probability(
            normal_cdf(s.strategy_score_gap / (noise * math.sqrt(2))),
            f"Probability #1 stays ahead of #2 if each composite carries "
            f"±{noise:.0f} pts of assessment noise (gap {s.strategy_score_gap:.1f} pts)",
        )
        if s.second_strategy is not None
        else confidence_fixed(LOW, "Only one scored opportunity; no rank to test.")
    )


# ------------------------------------------------------------------
# Lens metric RAG
# ------------------------------------------------------------------

def _build_ratings(s):
    """RAG readings for the metrics the Treasury, Peers, News, Strategy and
    Horizon lenses show, shared with the home dock."""
    tier1_m = safe_float(s.latest_history["cet1_capital_m"]) + safe_float(
        s.latest_history["at1_capital_m"]
    )
    rate50_loss_pct = (
        abs(min(s.treasury_rate50_impact_m, 0.0)) / s.cet1_capital * 100.0
        if s.cet1_capital
        else 0.0
    )
    dv01_200bp_pct = s.treasury_dv01 * 200.0 / tier1_m * 100.0 if tier1_m else 0.0
    unrealised_pct = (
        s.treasury_unrealised_pnl_m / s.treasury_market_value_m * 100.0
        if s.treasury_market_value_m
        else 0.0
    )

    news = s.news_recent
    negative_share_pct = (
        float((news["impact_direction"].astype(str).str.lower() == "negative").mean() * 100.0)
        if news is not None and not news.empty
        else 0.0
    )
    focus = s.geo_focus
    attention = safe_float(focus["geo_attention_score"]) if focus is not None else 0.0
    exposure = safe_float(focus["bank_exposure_share_pct"]) if focus is not None else 0.0

    top, gap = s.top_strategy, s.top_capability_gap

    full = _full_months(s.monthly_nim)
    ytd_monthly_nii = float(full["monthly_nii_m"].mean()) if not full.empty else 0.0
    forward_months = (
        int((s.horizon_baseline["series"] == "Baseline").sum())
        if not s.horizon_baseline.empty
        else 0
    )
    forward_monthly_nii = s.horizon_remaining_nii_m / max(forward_months, 1)
    nii_vs_ytd_pct = _pct_change(forward_monthly_nii, ytd_monthly_nii) or 0.0

    s.ratings = {
        "treasury_value": rag(unrealised_pct, 0.0, -2.0, unit="% of MV unrealised"),
        "treasury_dv01": rag(
            dv01_200bp_pct, 10.0, 15.0, higher_is_better=False,
            unit="% of Tier 1 at ±200bp", precision=0,
        ),
        "treasury_duration": rag(
            s.treasury_duration, 4.0, 6.0, higher_is_better=False, unit="y"
        ),
        "treasury_rate50": rag(
            rate50_loss_pct, 5.0, 10.0, higher_is_better=False,
            unit="% of CET1 lost", precision=0,
        ),
        "peer_roe": rag(s.roe_peer_gap_pp, 0.0, -3.0, unit="pp vs median"),
        "peer_cet1": rag(s.cet1_peer_gap_pp, 0.0, -1.5, unit="pp vs median"),
        "peer_ci": rag(s.efficiency_peer_advantage_pp, 0.0, -5.0, unit="pp vs median"),
        "news_articles": rag(
            negative_share_pct, 40.0, 60.0, higher_is_better=False,
            unit="% negative", precision=0,
        ),
        "news_high": rag(
            s.high_impact_news_count, 0, 2, higher_is_better=False,
            unit=" high-impact", precision=0,
        ),
        "news_attention": rag(
            attention, 50.0, 75.0, higher_is_better=False, precision=0
        ),
        "news_exposure": rag(
            exposure, 30.0, 50.0, higher_is_better=False, unit="%", precision=0
        ),
        "strategy_top": (
            rag(safe_float(top["overall_opportunity_score"]), 75.0, 60.0, unit=" pts", precision=0)
            if top is not None
            else rag_from_status(AMBER, "No scored opportunity")
        ),
        "strategy_fit": (
            rag(safe_float(top["strategic_fit_score"]), 75.0, 60.0, unit=" pts", precision=0)
            if top is not None
            else rag_from_status(AMBER, "No scored opportunity")
        ),
        "strategy_gap": (
            rag(
                safe_float(gap["capability_gap"]), 15.0, 30.0,
                higher_is_better=False, unit=" pts", precision=0,
            )
            if gap is not None
            else rag_from_status(GREEN, "No capability gap recorded")
        ),
        "horizon_ye_nim": rag(s.horizon_year_end_nim, *NIM_RAG_PCT, unit="%", precision=2),
        "horizon_fy_nii": rag(
            nii_vs_ytd_pct, -1.0, -3.0, unit="% vs YTD monthly NII"
        ),
        "horizon_first_step": rag(s.horizon_first_month_bps, 0.0, -5.0, unit=" bps"),
        "horizon_balance_sheet": rag(
            s.horizon_asset_growth_pct, 0.0, -0.5, unit="% / month"
        ),
    }


# ------------------------------------------------------------------
# Internal news — what happened inside the bank
# ------------------------------------------------------------------

ANOMALY_COPY = {
    "TEMP_DEPOSIT_OUTFLOW": ("Deposits", "Temporary deposit outflow"),
    "DEPOSIT_STRESS": ("Deposits", "Deposit stress"),
    "CREDIT_WATCH": ("Credit", "Credit watch"),
}


def _join_names(values):
    names = sorted({str(value) for value in values})
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " & " + names[-1]


def _anomaly_episodes(daily):
    """The latest episode of each anomaly type the daily monitor flagged."""
    flagged = daily[daily["anomaly_flag"] == 1]
    episodes = []

    for anomaly_type, rows in flagged.groupby("anomaly_type"):
        dates = pd.Series(sorted(rows["date"].unique()))
        breaks = dates.diff().dt.days.fillna(0) > ANOMALY_EPISODE_GAP_DAYS
        episode_dates = dates[breaks.cumsum() == breaks.cumsum().max()]
        start, end = episode_dates.min(), episode_dates.max()
        episode = rows[rows["date"].between(start, end)]
        episodes.append((anomaly_type, start, end, episode))

    return episodes


def _episode_item(daily, anomaly_type, start, end, episode, live_date):
    tag, label = ANOMALY_COPY.get(
        anomaly_type, ("Signal", anomaly_type.replace("_", " ").title())
    )
    segments = episode[["country", "business_line", "product"]].drop_duplicates()
    in_scope = daily.merge(segments, on=["country", "business_line", "product"])
    before = in_scope[in_scope["date"] == start - pd.Timedelta(days=1)]
    at_end = in_scope[in_scope["date"] == end]

    if tag == "Deposits":
        # The deepest point of the episode, not its last day: an outflow that
        # partly reversed inside the window would otherwise read as small.
        balance_before = float(before["deposit_balance_m"].sum())
        during = in_scope[in_scope["date"].between(start, end)]
        trough_m = float(during.groupby("date")["deposit_balance_m"].sum().min())
        change_m = trough_m - balance_before
        change_pct = change_m / balance_before * 100.0 if balance_before else 0.0
        movement = (
            f"At the deepest point balances were {change_pct:+.1f}% "
            f"(€{change_m / 1000:+,.2f}bn) against the day before, across "
            f"{_join_names(segments['product']).lower()}."
        )
    else:
        def stage_2(frame):
            weight = frame["loan_balance_m"].sum()
            return (
                float((frame["stage_2_share_pct"] * frame["loan_balance_m"]).sum() / weight)
                if weight
                else 0.0
            )

        movement = (
            f"Stage 2 share on {_join_names(segments['product']).lower()} went "
            f"{stage_2(before):.1f}% → {stage_2(at_end):.1f}%."
        )

    open_episode = end >= live_date - pd.Timedelta(days=1)

    return {
        "sort": end,
        "date": (
            start.strftime("%d %b")
            if start == end
            else f"{start.strftime('%d %b')} – {end.strftime('%d %b')}"
        ),
        "tag": tag,
        "headline": (
            f"{label} flagged in {_join_names(segments['country'])} "
            f"{_join_names(segments['business_line']).lower()}"
        ),
        "detail": movement,
        "source": "Daily signal monitor",
        "status": "Open" if open_episode else "Closed",
    }


def _build_internal_news(s):
    """
    The bank's own developments, as a feed alongside the public news.

    Built from what the data records happening inside the bank: the certified
    close, the anomaly episodes the daily monitor flagged, and the latest
    treasury revaluation. Newest first.
    """
    items = [
        {
            "sort": s.reporting_date_ts,
            "date": s.reporting_date_ts.strftime("%d %b"),
            "tag": "Close",
            "headline": f"{s.reporting_date_ts.strftime('%B')} month-end close certified",
            "detail": (
                f"CET1 {s.cet1_ratio:.2f}%, LCR {s.lcr_ratio:.0f}%, YTD cost/income "
                f"{s.ytd_cost_income:.1f}% on {s.months_observed} months of actuals."
            ),
            "source": "Finance / certified close",
            "status": "Certified",
        }
    ]

    if s.treasury_summary is not None:
        as_of = pd.to_datetime(s.treasury_summary["as_of_date"])
        items.append(
            {
                "sort": as_of,
                "date": as_of.strftime("%d %b"),
                "tag": "Treasury",
                "headline": "Treasury portfolio revalued",
                "detail": (
                    f"Market value €{s.treasury_market_value_m / 1000:,.1f}bn, "
                    f"unrealised P&L €{s.treasury_unrealised_pnl_m:+,.0f}m, "
                    f"DV01 €{s.treasury_dv01:.1f}m per bp."
                ),
                "source": "Treasury / portfolio snapshot",
                "status": "Snapshot",
            }
        )

    daily = load_bank_daily_signals()
    if daily is not None and not daily.empty:
        daily = daily.copy()
        daily["date"] = pd.to_datetime(daily["date"])
        if s.business_line is not None:
            daily = daily[daily["business_line"] == s.business_line_data]
        for anomaly_type, start, end, episode in _anomaly_episodes(daily):
            items.append(
                _episode_item(daily, anomaly_type, start, end, episode, s.live_date_ts)
            )

    if s.current_credit_watch_count:
        items.append(
            {
                "sort": s.live_date_ts,
                "date": s.live_date_ts.strftime("%d %b"),
                "tag": "Credit",
                "headline": f"{s.current_credit_watch_count} credit watch flag(s) open",
                "detail": s.credit_signal_primary,
                "source": "Daily signal monitor",
                "status": "Open",
            }
        )

    items.sort(key=lambda item: item["sort"], reverse=True)
    for item in items:
        for field in ("date", "tag", "headline", "detail", "source", "status"):
            item[field] = html.escape(html.unescape(str(item[field])))

    s.internal_news = items
