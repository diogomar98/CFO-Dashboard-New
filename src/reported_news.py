"""Real Data News Intelligence: official-source scan → AI triage → reviewed ECB shock.

The Synthetic News module and fixture-scanning agent remain untouched.
"""
import html
from datetime import datetime, timezone

import streamlit as st

from src.hud import navigate_to_module, render_html
from src.reported_brief import BRIEF_CSS, _official_article_card
from src.public_horizon_engine import load_public_horizon_inputs
from src.public_scenario_engine import NEUTRAL_INPUTS
from src.reported_news_partner import (
    DFR_URL, OFFICIAL_FEEDS, classify_headlines, fetch_ecb_articles,
    fetch_ecb_rate_events, verified_rate_scenario, load_official_news_snapshot,
)


@st.cache_data(ttl=1800,show_spinner=False)
def load_real_public_news():
    return fetch_ecb_articles()


@st.cache_data(ttl=3600,show_spinner=False)
def load_real_news_ai_classification(article_batch):
    return classify_headlines(article_batch)


@st.cache_data(ttl=3600,show_spinner=False)
def load_verified_ecb_rate_events():
    return fetch_ecb_rate_events()


def recent_official_articles(*, include_status=False):
    """Official live RSS first, timestamped *real* ECB snapshot if blocked.

    This is never a Synthetic feed. The source mode must be visible in the UI
    so saved headlines cannot be mistaken for live monitoring.
    """
    live, warnings = load_real_public_news()
    if live:
        mode = {"mode":"live","retrieved_at_utc":None,"count":len(live)}
        return (live,warnings,mode) if include_status else (live,warnings)
    saved,meta=load_official_news_snapshot()
    if saved:
        warnings=list(warnings)+[
            "Live ECB feeds unavailable: displaying a point-in-time official snapshot, "
            "not current monitoring"
        ]
        return (saved,warnings,meta) if include_status else (saved,warnings)
    warnings=list(warnings)+[meta.get("error","No official-source news available")]
    mode={"mode":"none","retrieved_at_utc":None,"count":0}
    return ([],warnings,mode) if include_status else ([],warnings)


def official_article_classifications(articles):
    """Run the same existing corporate AI Gateway over locally saved articles.

    Uses only public title/excerpt, so ABN's blocked Internet does NOT block
    the classification call. A Gateway error keeps scores unrated; no fabricated
    relevance, confidence or financial effects are inserted.
    """
    if not articles:
        return {},None
    try:
        result=load_real_news_ai_classification(articles[:8])
        return {item["id"]:item for item in result},None
    except Exception:
        return {},"AI Gateway returned no usable classification"


def current_verified_ecb_change(reporting_frame, *, events=None, now=None):
    """The net *observed* ECB DFR move since model's Q2 2026 cutoff."""
    current=now or datetime.now(timezone.utc).date()
    dfr_close=float(reporting_frame.iloc[-1]["dfr_qend_pct"])
    rate_events=events if events is not None else load_verified_ecb_rate_events()
    valid=[(day,rate) for day,rate in rate_events
           if day<=current]
    if not valid:
        return None
    date_effect,observed=valid[-1]
    if date_effect<=datetime(2026,6,30).date():
        return None
    movement=(observed-dfr_close)*100
    rounded=round(movement)
    if abs(movement-rounded)>.05 or not -100<=rounded<=100 or not rounded:
        return None
    return {
        "rate_shock_bps":int(rounded),
        "rate_effective_date":date_effect.isoformat(),
        "latest_ecb_dfr_pct":observed,
        "q2_2026_dfr_pct":dfr_close,
        "official_data_url":DFR_URL,
        "status":"Official ECB rate observations; historic update since forecast cutoff",
    }


def _queue_rate_scenario(evidence):
    """No actual model run until CFO reviews choices in the What-If form."""
    shock=int(evidence["rate_shock_bps"])
    if not -100<=shock<=100:
        raise ValueError("ECB rate difference exceeds the reviewed shock range.")
    st.session_state["rs_public_options"]={
        **NEUTRAL_INPUTS,"method":"rate_arx","rate_shock_bps":float(shock),
    }
    st.session_state["rs_news_source"]={
        "rate_shock_bps":shock,
        "rate_effective_date":evidence["rate_effective_date"],
        "official_data_url":evidence["official_data_url"],
        "article_url":evidence.get("article_url"),
        "article_title":evidence.get("article_title"),
        "status":evidence["status"],
    }
    navigate_to_module("scenario")


def _card(article, classification, *, saved=False):
    """Same original coloured external-news card as Synthetic Morning Brief."""
    return _official_article_card(article,classification,saved=saved)



def render_reported_news(s):
    render_html(BRIEF_CSS)
    st.markdown("### News Intelligence · verified public sources")
    st.caption(
        "Official ECB news articles are read from the live feed or saved "
        "point-in-time source snapshot. The existing corporate AI Gateway "
        "can rank and assess the relevance of locally stored headlines. "
        "Neither confidence nor relevance establishes a bank impact."
    )
    report=load_public_horizon_inputs(s.reported_group)
    if st.button("↻ Retry live ECB connection",key="rn_retry_official_feeds"):
        load_real_public_news.clear()
        load_verified_ecb_rate_events.clear()
        st.rerun()
    fresh,warnings,status=recent_official_articles(include_status=True)
    if status["mode"]=="snapshot":
        st.warning(
            "Live ECB news is unavailable from this Databricks environment. "
            "Displaying **real ECB articles saved on "
            +status["retrieved_at_utc"][:16].replace("T"," ")+" UTC**. "
            "This is a dated snapshot, not up-to-date monitoring."
        )
    elif status["mode"]=="none":
        st.error("Neither the official ECB feeds nor the verified backup snapshot is available.")
    else:
        st.caption("News source status: live official ECB RSS feed.")
    if warnings:
        with st.expander("News connection diagnostics",expanded=status["mode"]!="live"):
            for warning in warnings:
                st.write("• "+warning)
            st.caption(
                "If this shows outbound HTTPS, proxy or TLS failures, request "
                "Databricks Apps egress approval for the official ECB RSS hosts. "
                "Do not disable TLS verification or upload credentials."
            )
    with st.spinner("Ranking official news with the existing AI Gateway…"):
        by_status,ai_error=official_article_classifications(fresh)
    if ai_error:
        st.warning(
            "The AI Gateway could not classify the locally available articles. "
            "Official news remains visible, but relevance and confidence "
            "are not assessed."
        )
    for warning in warnings:
        st.caption("Source status: "+warning)

    actionable_count=sum(
        1 for article in fresh
        if by_status.get(article["id"],{}).get("relevance")=="HIGH"
    )
    c1,c2,c3=st.columns(3)
    c1.metric(
        "Official headlines ("+("Live" if status["mode"]=="live" else "Saved" if status["mode"]=="snapshot" else "None")+")",
        str(len(fresh)),
    )
    c2.metric("AI high relevance",str(actionable_count) if by_status else "Unavailable")
    c3.metric("Rate-stress support","ECB DFR only")
    st.caption(
        "Sources: "+", ".join(x[0] for x in OFFICIAL_FEEDS)
        +". Feed summaries are not the same as complete articles. "
        "No user or bank-specific financial data are transmitted to the news classifier."
    )
    try:
        rate_events=load_verified_ecb_rate_events()
        official_change=current_verified_ecb_change(report,events=rate_events)
    except Exception:
        rate_events=None
        official_change=None
        st.caption(
            "ECB rate API request failed independently of the headlines. "
            "Scenario prefill is disabled until the official ECB rate API "
            "can be reached; saved headlines are never numerical shock evidence."
        )
    feed_col,scenario_col=st.columns([1.4,1],gap="large")
    with feed_col:
        st.markdown("#### Recent developments")
        if not fresh:
            st.info("No official ECB headlines are currently available. Nothing synthetic is shown.")
        for article in fresh[:10]:
            render_html('<div class="rb-news-grid">'+_card(
                article,by_status.get(article["id"],{}),
                saved=status["mode"]=="snapshot",
            )+'</div>')
            if rate_events is not None:
                reviewed=verified_rate_scenario(
                    article,rate_events,
                    reported_dfr=float(report.iloc[-1]["dfr_qend_pct"]),
                )
                if reviewed and st.button(
                    f"Review verified ECB rate move ({reviewed['rate_shock_bps']:+d} bps) ↗",
                    key="rn_event_"+article["id"],use_container_width=True,
                ):
                    _queue_rate_scenario(reviewed)

    with scenario_col:
        st.markdown("#### From public news to What-If")
        st.caption(
            "The only supported Real Data news lever is the ECB deposit "
            "facility rate. Other AI-detected topics remain watchlist items "
            "until a validated financial scenario model exists."
        )
        if rate_events is None:
            st.warning(
                "Official ECB rate verification is unavailable. "
                "No rate scenario can be prepared."
            )
        if official_change is None:
            st.info(
                "No new, independently verified ECB rate change within "
                "the model's ±100 bps scenario range was found after Q2 2026."
            )
        else:
            change=official_change["rate_shock_bps"]
            st.metric("Observed DFR change vs Q2 2026",f"{change:+d} bps")
            st.write(
                f"Q2 2026: **{official_change['q2_2026_dfr_pct']:.2f}%** → "
                f"latest verified: **{official_change['latest_ecb_dfr_pct']:.2f}%**"
            )
            st.caption(
                "ECB rate effective from "
                +official_change["rate_effective_date"]
                +". This is a historical rate update to the Q2-cutoff "
                "model—not a forecast, and not proof of ABN NII/NIM impact."
            )
            st.markdown(
                "[Inspect official ECB rate observations]("
                +official_change["official_data_url"]+")"
            )
            if st.button(
                f"Review {change:+d} bps scenario in What-If →",
                use_container_width=True,key="rn_news_to_whatif"
            ):
                _queue_rate_scenario(official_change)
        st.divider()
        st.markdown("#### What AI is doing")
        st.write(
            "1. Monitor a fixed set of official feeds.\n"
            "2. Classify relevance using public headlines and excerpts.\n"
            "3. Independently check rate observations against the ECB API.\n"
            "4. Prepare, but never silently execute, a scenario."
        )
        st.caption(
            "Live retrieval is cached for 30 minutes while in use. A saved "
            "snapshot is historical, not monitored. Continuous unattended "
            "monitoring needs an approved Databricks Job."
        )
