"""Real Data News Intelligence: official-source scan → AI triage → reviewed ECB shock.

The Synthetic News module and fixture-scanning agent remain untouched.
"""
import html
from datetime import datetime, timezone

import streamlit as st

from src.hud import navigate_to_module, render_html
from src.reported_brief import BRIEF_CSS, _official_article_card, _prototype_article
from src.public_horizon_engine import load_public_horizon_inputs
from src.public_scenario_engine import NEUTRAL_INPUTS
from src.reported_news_partner import (
    DFR_URL, OFFICIAL_FEEDS, classify_headlines, fetch_ecb_articles,
    fetch_ecb_rate_events, verified_rate_scenario, load_official_news_snapshot,
    load_curated_bank_news, REPORTED_NEWS_SEGMENTS, RELEVANCE_LEVELS,
)
from src.reported_news_signals import COUNTRIES, load_prototype_news_signals


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
            "relevance_origin":article.get("relevance_origin","Editorial review"),
            "ai_agrees":bool(agreed),
        }
    if ai.get("relevance") in RELEVANCE_LEVELS:
        return dict(ai,relevance_origin="AI only")
    return {"id":article["id"],"relevance":"UNRATED",
            "reason":"","metric":"Not assessed","confidence":None,
            "relevance_origin":"Not assessed"}


def filter_financial_news(articles, assessments, relevance="All",
                          segment="All segments", country="All countries",
                          metric="All metrics", direction="All directions",
                          category="All categories"):
    """AND-combined relevance and *exact* published-business-line filters."""
    valid_filters=("All","High","Medium","Low","Not assessed")
    if relevance not in valid_filters:
        raise ValueError("Unknown relevance filter")
    if segment!="All segments" and segment not in REPORTED_NEWS_SEGMENTS:
        raise ValueError("Unknown reported segment")
    if country!="All countries" and country not in COUNTRIES:
        raise ValueError("Unknown country filter")
    if direction not in ("All directions","Positive","Negative","Mixed"):
        raise ValueError("Unknown impact direction")
    available_metrics={a.get("primary_affected_metric") for a in articles}
    if metric!="All metrics" and metric not in available_metrics:
        raise ValueError("Unknown financial metric filter")
    valid_categories={a.get("category") for a in articles if a.get("category")}
    if category!="All categories" and category not in valid_categories:
        raise ValueError("Unknown news category")
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
        if country!="All countries" and country!=article.get("country"):
            continue
        if metric!="All metrics" and metric!=article.get("primary_affected_metric"):
            continue
        if direction!="All directions" and direction!=article.get("impact_direction"):
            continue
        if category!="All categories" and category!=article.get("category"):
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
    """Preserve Synthetic/Real news card CSS and colours for both source types."""
    if not article.get("prototype"):
        return _official_article_card(article,classification,saved=saved)
    # The submitted CSV is unverified prototype input. Never misrepresent
    # scores as measured ABN exposure, AI confidence, or publisher validation.
    level=classification.get("relevance","UNRATED")
    marker="Prototype assessment · "+article.get("country","Unknown")
    html_card=_prototype_article({
        "news_origin":"official",
        "ai_assessed":"no",
        "relevance_origin":"Prototype classification",
        "category":marker+" · "+article.get("category","Uncategorised"),
        "headline":article["headline"],
        "source":article["source"],
        "published_date":article["published"],
        "source_url":article["url"],
        "bank_impact_summary":article.get("bank_impact_summary") or article["summary"],
        "primary_affected_metric":article.get("primary_affected_metric","Not assessed"),
        "potential_impact_level":level,
        "segments":article.get("segments",[]),
        # Never show the user-provided 0.99 confidence as verified certainty.
        "confidence_score":None,
        "source_note":(
            "User-supplied synthetic prototype classification; article claims, "
            "impact scores and business-line matching are unverified."
        ),
    })
    return html_card.replace(
        "<strong>Official excerpt</strong>",
        "<strong>Prototype assessment (unverified)</strong>",
    ).replace(
        "<strong>Potential business lines</strong>",
        "<strong>Illustrative business lines</strong>",
    )



NEWS_SCROLL_CSS = """
<style>
/* Real News inherits the original Synthetic cockpit palette and typography. */
.rn-news-scroll {
    max-height:min(620px,70vh);
    overflow-y:auto;
    overflow-x:hidden;
    padding:3px 12px 8px 2px;
    scrollbar-width:thin;
    scrollbar-color:#557c69 #142019;
}
.rn-news-scroll .rb-news-grid {
    display:grid;
    grid-template-columns:minmax(0,1fr);
    gap:12px;
    margin:10px 0 18px;
}
.rn-news-scroll .rb-news-item {
    position:relative;
    min-width:0;
    box-sizing:border-box;
    border:1px solid rgba(107,167,149,.38) !important;
    border-top:2px solid rgba(127,206,173,.7) !important;
    border-radius:11px;
    padding:15px 17px 13px !important;
    background:linear-gradient(135deg,rgba(26,49,48,.92),rgba(14,27,30,.94));
    box-shadow:0 4px 16px rgba(0,0,0,.13);
}
.rn-news-scroll .rb-news-item:before {
    content:"";
    position:absolute;left:0;top:13px;bottom:13px;width:3px;
    border-radius:0 3px 3px 0;
    background:#68b58b;
}
.rn-news-scroll .rb-news-item:has(.status-impact-high):before {background:#dc9f7a;}
.rn-news-scroll .rb-news-item:has(.status-impact-medium):before {background:#ddc58e;}
.rn-news-scroll .rb-news-item .feed-item-top {
    display:flex;gap:8px;align-items:center;
    padding-bottom:10px;margin-bottom:9px;
    border-bottom:1px solid rgba(173,203,194,.19);
}
.rn-news-scroll .rb-news-item .feed-headline {
    font-family:inherit;
    font-size:1rem;
    font-weight:750;
    line-height:1.43;
    letter-spacing:-.012em;
    color:#f3faf6;
    margin:7px 0 9px;
    overflow-wrap:anywhere;
}
.rn-news-scroll .rb-news-item .feed-detail {
    font-size:.78rem;
    line-height:1.55;
    color:#becfc8;
    margin:6px 0;
}
.rn-news-scroll .rb-news-item .feed-foot {
    margin-top:11px;
    padding-top:9px;
    border-top:1px solid rgba(173,203,194,.13);
}
.rn-news-scroll .rb-news-item > .feed-detail:last-child {
    display:none; /* provenance remains in the dedicated source information expander */
}
.rn-country-title {
    font-size:.82rem;
    font-weight:800;
    color:#d6eee1;
    padding:12px 2px 6px;
    margin:9px 0 4px;
    border-bottom:1px solid rgba(112,180,155,.42);
    letter-spacing:.05em;
    text-transform:uppercase;
}
.rn-news-subline {font-size:.75rem;color:#acc4b8;}
@media(max-width:700px) {
  .rn-news-scroll {padding-right:4px;}
  .rn-news-scroll .rb-news-item {padding:12px !important;}
}
</style>
"""


def render_reported_news(s):
    """Source-linked offline financial news and existing AI relevance, concise UI."""
    render_html(BRIEF_CSS+NEWS_SCROLL_CSS)
    st.markdown("### Financial News Intelligence")
    source_choice=st.selectbox(
        "News source",
        ["Country news signals · prototype", "Reviewed publisher selection"],
        key="rn_source_choice",
        help=(
            "Prototype: 26 user-supplied, unverified signals grouped by country. "
            "Reviewed: the previous publisher-linked curation."
        ),
    )
    is_prototype=source_choice.startswith("Country")
    if is_prototype:
        articles,status=load_prototype_news_signals()
        warnings=[]
    else:
        articles,warnings,status=recent_official_articles(include_status=True)
    if not articles:
        st.warning("Selected news catalogue is unavailable. Check data/news_signals.csv or data/abn_news_curated.json.")
        return
    from src.hud import navigate_to_module
    if is_prototype:
        # These are precomputed, synthetic/unverified relevance grades.
        # Do not call AI on them or mislabel them as independently reviewed.
        classified={article["id"]:_effective_news_assessment(article)
                    for article in articles}
        ai_error=None
    else:
        with st.spinner("Ranking verified headlines with Jarvis AI…"):
            classified,ai_error=official_article_classifications(articles)
    c1,c2,c3=st.columns(3)
    c1.metric("News signals" if is_prototype else "Curated articles",len(articles))
    c2.metric(
        "High relevance",
        sum(classified.get(a["id"],{}).get("relevance")=="HIGH"
            for a in articles),
    )
    c3.metric("Publishers",len({a["source"].split(" · ")[0] for a in articles}))
    if is_prototype:
        st.caption(
            "Prototype news · supplied public-source headlines and "
            "illustrative financial impact classifications · not a live feed"
        )
    else:
        st.caption(
            "Saved publisher selection · "+status.get("retrieved_at_utc","")[:10]
        )
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
            "Prototype relevance is taken from the supplied CSV and NOT "
            "independently reviewed." if is_prototype else
            "Reviewed from linked headlines and short summaries, not full "
            "publisher articles. Business-line tags indicate possible relevance, "
            "not proven exposure. Optional AI confidence is an uncalibrated "
            "agreement assessment—not a probability of actual bank impact."
        )
    filter_country,filter_relevance,filter_category=st.columns(3,gap="small")
    with filter_country:
        selected_country=st.selectbox(
            "Country",["All countries"]+list(COUNTRIES),
            key="rn_filter_country",disabled=not is_prototype,
        )
    with filter_relevance:
        selected_relevance=st.selectbox(
            "Relevance",["All","High","Medium","Low","Not assessed"],
            key="rn_filter_relevance",
        )
    with filter_category:
        categories=sorted({a.get("category","Uncategorised") for a in articles})
        selected_category=st.selectbox(
            "News category",["All categories"]+categories,
            key="rn_filter_category",
        )
    by_metric,by_direction=st.columns(2,gap="medium")
    with by_metric:
        selected_metric=st.selectbox(
            "Financial metric",["All metrics"]+sorted({
                a["primary_affected_metric"] for a in articles
                if a.get("primary_affected_metric")
            }),
            key="rn_filter_metric",disabled=not is_prototype,
        )
    with by_direction:
        selected_direction=st.selectbox(
            "Impact direction",["All directions","Positive","Negative","Mixed"],
            key="rn_filter_direction",disabled=not is_prototype,
        )
    visible=filter_financial_news(
        articles,classified,relevance=selected_relevance,
        category=selected_category,
        country=selected_country if is_prototype else "All countries",
        metric=selected_metric if is_prototype else "All metrics",
        direction=selected_direction if is_prototype else "All directions",
    )
    st.caption(f"{len(visible)} of {len(articles)} news items")
    feed,aside=st.columns([1.8,1],gap="large")
    with feed:
        st.markdown("#### Latest developments")
        # One controlled div owns the scrollbar; compatible with older
        # Streamlit (st.container(height=) is unavailable in ABN).
        if not visible:
            st.info("No news matches these filters.")
        else:
            if is_prototype:
                # Group each country's cards under a visible geographic heading.
                groups=[]
                visible_countries=(
                    [selected_country] if selected_country!="All countries"
                    else list(COUNTRIES)
                )
                for country in visible_countries:
                    subset=[a for a in visible if a.get("country")==country]
                    if not subset:
                        continue
                    groups.append(
                        '<div class="rn-country-title">'+
                        html.escape(country)+" · "+str(len(subset))+
                        ' signals</div><div class="rb-news-grid">'+
                        "".join(_card(a,classified.get(a["id"],{}),saved=True)
                                for a in subset)+
                        '</div>'
                    )
                card_html="".join(groups)
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
        if is_prototype and visible:
            st.markdown("#### Signal details")
            selected_id=st.selectbox(
                "Explore a news item",
                [a["id"] for a in visible],
                format_func=lambda item:next(
                    (a["country"]+" · "+a["headline"][:52] for a in visible
                     if a["id"]==item),item
                ),
                key="rn_selected_signal",
            )
            chosen=next(a for a in visible if a["id"]==selected_id)

            st.markdown("**Potential impact**")
            st.write(chosen["bank_impact_summary"] or "Not supplied.")
            st.markdown("**Affected metrics**")
            st.write(" · ".join([chosen["primary_affected_metric"]]+
                     chosen["secondary_metrics"]))
            st.markdown("**Suggested follow-up**")
            st.write(chosen["suggested_action"] or "Not supplied.")
            st.markdown("**Related scenario**")
            st.caption(
                (chosen["linked_scenario"] or "None")+
                " · "+(chosen["scenario_status"] or "Not supplied")
            )
            with st.expander("Prototype scores and provenance"):
                st.write("Relevance score: "+
                         str(chosen["relevance_score"])+"/100 (unvalidated)")
                st.write("Confidence score: "+
                         str(chosen["confidence_score"])+
                         " (user-supplied, uncalibrated)")
                st.write(chosen["classification_method"])
                st.write("Country from geo_profile: "+chosen["geo_profile"])
                st.write("Business-line tags: illustrative keyword mapping")
        st.markdown("#### From news to What-If")
        if st.button("Open What-If →",key="rn_manual_scenario",use_container_width=True):
            navigate_to_module("scenario")
        with st.expander("About sources & assessments",expanded=False):
            if is_prototype:
                st.write(
                    "Country news and financial-impact assessments are from "
                    "the uploaded prototype CSV. Figures, links, scores, "
                    "business-line relevance and suggested actions have not "
                    "been independently validated. Scenario associations are "
                    "labels only; no automatic model inputs are generated."
                )
            else:
                st.write(
                    "Publisher-linked editorial snapshot, not live news. "
                    "Some articles require subscriptions. AI relevance is "
                    "an interpretation, not an observed financial impact."
                )
