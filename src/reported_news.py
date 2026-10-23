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
    load_curated_bank_news, REPORTED_NEWS_SEGMENTS, RELEVANCE_LEVELS,
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
    """Offline curated publisher selection. No ECB fetch from the ABN App.

    Retain historical name for backwards compatibility with Morning Brief.
    News is reviewed and saved on a given date, NOT automatically live.
    """
    bank_news, status=load_curated_bank_news()
    if bank_news:
        warnings=[]
        return (bank_news,warnings,status) if include_status else (bank_news,warnings)
    saved, old_status=load_official_news_snapshot()
    if saved:
        old_status["source"]="Archived official ECB headlines"
        warning=["Multi-publisher selection missing; only older ECB snapshot is available"]
        return (saved,warning,old_status) if include_status else (saved,warning)
    warnings=["No approved offline news sources installed"]
    return ([],warnings,{"mode":"none","count":0}) if include_status else ([],warnings)


def _effective_news_assessment(article, model_result=None):
    """Reviewed relevance governs curated selections; AI is optional context.

    Editorial relevance is based on short verified public news metadata.
    Model confidence is only displayed if AI independently agrees with that
    reviewed tier. Neither rating is a financial-impact probability.
    """
    ai=model_result if isinstance(model_result,dict) else {}
    editorial=article.get("editorial_relevance")
    if editorial in RELEVANCE_LEVELS:
        agreed=ai.get("relevance")==editorial
        return {
            "id":article["id"],
            "relevance":editorial,
            "metric":ai.get("metric") if agreed else "Not assessed",
            "reason":ai.get("reason") if agreed and ai.get("reason")
                     else article.get("editorial_reason",""),
            "confidence":ai.get("confidence") if agreed else None,
            "relevance_origin":"Editorial review",
            "ai_agrees":bool(agreed),
        }
    if ai.get("relevance") in RELEVANCE_LEVELS:
        return dict(ai,relevance_origin="AI only")
    return {"id":article["id"],"relevance":"UNRATED",
            "reason":"","metric":"Not assessed","confidence":None,
            "relevance_origin":"Not assessed"}


def filter_financial_news(articles, assessments, relevance="All",
                          segment="All segments"):
    """AND-combined relevance and *exact* published-business-line filters."""
    valid_filters=("All","High","Medium","Low","Not assessed")
    if relevance not in valid_filters:
        raise ValueError("Unknown relevance filter")
    if segment!="All segments" and segment not in REPORTED_NEWS_SEGMENTS:
        raise ValueError("Unknown reported segment")
    wanted=relevance.upper()
    filtered=[]
    for article in articles:
        assessment=assessments.get(article["id"],{})
        current=assessment.get("relevance","UNRATED")
        if wanted!="ALL" and (
            current!=("UNRATED" if wanted=="NOT ASSESSED" else wanted)
        ):
            continue
        if segment!="All segments" and segment not in article.get("segments",[]):
            continue
        filtered.append(article)
    return filtered


def official_article_classifications(articles):
    """Use the existing AI Gateway, while keeping editorial filter stable.

    The source catalogue has independently reviewed relevance tiers so every
    source-linked article remains filterable if the corporate LLM is offline.
    All article groups are classified (not just first eight). No internal ABN
    data are sent: model receives only verified public titles/short excerpts.
    """
    if not articles:
        return {},None
    model={}
    errors=0
    for idx in range(0,len(articles),8):
        batch=articles[idx:idx+8]
        try:
            rows=load_real_news_ai_classification(batch)
            model.update({x["id"]:x for x in rows if x.get("id") in {
                item["id"] for item in batch
            }})
        except Exception:
            errors+=1
    effective={
        article["id"]:_effective_news_assessment(article,model.get(article["id"]))
        for article in articles
    }
    return effective, (
        "AI comments unavailable for part of the selection; editorial relevance "
        "remains available." if errors else None
    )



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



NEWS_SCROLL_CSS = """
<style>
/* Single bounded source list: never extend the News dialog to 12 screens. */
.rn-news-scroll {
    max-height:min(590px,69vh);
    overflow-y:auto;
    overflow-x:hidden;
    padding:0 .85rem 0 0;
    scrollbar-width:thin;
    scrollbar-color:#46694f #102018;
}
.rn-news-scroll .rb-news-grid {display:block;}
.rn-news-scroll .rb-news-item {padding:14px 12px 14px 8px !important;}
.rn-subtle {font-size:.72rem;color:#A1BBA8;line-height:1.45;}
</style>
"""


def render_reported_news(s):
    """Source-linked offline financial news and existing AI relevance, concise UI."""
    render_html(BRIEF_CSS+NEWS_SCROLL_CSS)
    st.markdown("### Financial News Intelligence")
    articles,warnings,status=recent_official_articles(include_status=True)
    if not articles:
        st.warning("No verified news catalogue is installed. Check data/abn_news_curated.json.")
        return
    from src.hud import navigate_to_module
    with st.spinner("Ranking verified headlines with Jarvis AI…"):
        classified,ai_error=official_article_classifications(articles)
    c1,c2,c3=st.columns(3)
    c1.metric("Curated articles",len(articles))
    c2.metric(
        "High relevance",
        sum(classified.get(a["id"],{}).get("relevance")=="HIGH"
            for a in articles),
    )
    c3.metric("Publishers",len({a["source"].split(" · ")[0] for a in articles}))
    note="Verified publisher links · saved selection as of "+status.get(
        "retrieved_at_utc","unknown")[:10]+". Not a live feed."
    st.caption(note)
    if ai_error:
        st.caption("AI commentary was partly unavailable; reviewed relevance and segment filters still work.")
    if warnings:
        st.caption("Source note: "+"; ".join(warnings[:2]))
    # Relevance is a reviewed, three-level editorial assessment for the
    # offline selection. A model may add explanation/uncalibrated confidence,
    # but cannot silently redefine the reviewer's published filter tier.
    with st.expander("How is relevance defined?", expanded=False):
        st.markdown(
            "**High** — Direct possible strategic, regulatory, capital, risk or "
            "control implications for ABN or a reported business line.\n\n"
            "**Medium** — Plausible but indirect financial, operational or "
            "sector connection.\n\n"
            "**Low** — Background, broad sector trends or sponsored themes "
            "without a specific immediate decision implication."
        )
        st.caption(
            "Reviewed from linked headlines and short summaries, not full "
            "publisher articles. Business-line tags indicate possible relevance, "
            "not proven exposure. Optional AI confidence is an uncalibrated "
            "agreement assessment—not a probability of actual bank impact."
        )
    filter_left,filter_right=st.columns(2,gap="medium")
    with filter_left:
        selected_relevance=st.selectbox(
            "Relevance",
            ["All","High","Medium","Low","Not assessed"],
            key="rn_filter_relevance",
        )
    with filter_right:
        selected_segment=st.selectbox(
            "Business segment",
            ["All segments"]+list(REPORTED_NEWS_SEGMENTS),
            key="rn_filter_segment",
        )
    visible=filter_financial_news(
        articles,classified,relevance=selected_relevance,
        segment=selected_segment,
    )
    st.caption(f"Showing {len(visible)} of {len(articles)} articles · "
               "relevance and segment filters are combined")
    feed,aside=st.columns([1.8,1],gap="large")
    with feed:
        st.markdown("#### Recent developments")
        # One controlled div owns the scrollbar; compatible with older
        # Streamlit (st.container(height=) is unavailable in ABN).
        if not visible:
            st.info("No articles match those filters. Select All relevance or All segments.")
        else:
            card_html="".join(
                '<div class="rb-news-grid">'+_card(
                    article,classified.get(article["id"],{}),saved=True,
                )+'</div>'
                for article in visible
            )
            render_html('<section class="rn-news-scroll" aria-label="Scrollable financial news">'
                        +card_html+'</section>')
    with aside:
        st.markdown("#### From news to What-If")
        st.write(
            "News informs potential financial drivers. The Real Data model "
            "currently supports rate-related NII/NIM scenarios."
        )
        st.caption(
            "No stress amount is inferred from press coverage. "
            "Apply your own explicit assumptions in What-If; it uses "
            "the validated reported-series forecast model."
        )
        if st.button("Open What-If →",key="rn_manual_scenario",use_container_width=True):
            navigate_to_module("scenario")
        st.markdown("#### Source coverage")
        st.caption(
            "Bloomberg, Financial Times, Yahoo Finance, FD partner content "
            "and Dutch banking coverage. Some sources may require subscriptions. "
            "The FD partner item is sponsored, not independent reporting."
        )
