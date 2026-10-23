"""

News — public developments and their potential bank impact.

 

One concise view: headline metrics, an impact-level filter, a scrollable feed

split into All and per-country tabs, using the full window width.

 

The OpenAI signal extractor (load_extracted_signals) stays here because the

What-If and Horizon modules read it to offer rate/deposit signals there.

"""

 

import html

 

import pandas as pd

import streamlit as st

 

from src import cockpit_views as views

from src.hud import (

    clip_ui_text,

    render_html,

    safe_float,

)

from src.rag import confidence_badge, confidence_probability

from src.news_partner import extract_signals, load_articles

 

IMPACT_FILTERS = ["All", "High", "Medium", "Low"]

 

NEWS_SCROLL_CSS = """

<style>

.rn-news-scroll {

    max-height:min(590px,69vh);

    overflow-y:auto;

    overflow-x:hidden;

    padding:0 .85rem 0 0;

    scrollbar-width:thin;

    scrollbar-color:#46694f #102018;

}

</style>

"""

 

IMPACT_BADGE = {"HIGH": "alert-red", "MEDIUM": "alert-amber"}

 

def article_confidence(article):

    """How sure the classifier is about an article's potential bank impact."""

    return confidence_probability(

        safe_float(article.get("confidence_score"), 0.0),

        "Classifier confidence in the potential bank impact",

    )

 

@st.cache_data(show_spinner="Extracting overnight news signals…")

def load_extracted_signals():

    """

    Run the OpenAI signal extractor over the fixture articles.

 

    Cached so the model is called once per session rather than on every rerun.

    An article that fails extraction is skipped rather than failing the module.

    """

    signals = []

    for article in load_articles():

        try:

            extracted = extract_signals(article)

        except Exception:

            continue

        for signal in extracted:

            signal["_article"] = article

        signals.extend(extracted)

    return signals

 

def _news_card(article):

    escape = html.escape

    level = str(article.get("potential_impact_level", "")).upper()

    badge_class = IMPACT_BADGE.get(level, "alert-green")

 

    return f"""

    <div class="news-card">

        <div class="news-topline">

            <span class="news-badge">{escape(str(article.get('category', 'News')))}</span>

            <span class="news-meta">{escape(str(article['source']))} · {pd.to_datetime(article['published_date']).strftime('%d %b')} · {escape(str(article.get('geographic_scope', '')))}</span>

        </div>

        <div class="news-headline">{escape(str(article['headline']))}</div>

        <div class="news-context-grid">

            <div class="news-context-line">

                <span class="news-context-label">Why it matters</span>

                <span class="news-context-copy">{escape(clip_ui_text(article.get('bank_impact_summary', ''), 160))}</span>

            </div>

            <div class="news-context-line">

                <span class="news-context-label">Potential metric</span>

                <span class="news-context-copy">{escape(str(article['primary_affected_metric']))} · <span class="{badge_class}">{escape(level or 'UNRATED')}</span></span>

            </div>

            <div class="news-context-line">

                <span class="news-context-label">Confidence</span>

                <span class="news-context-copy">{confidence_badge(article_confidence(article))}</span>

            </div>

            <div class="news-context-line">

                <span class="news-context-label">Next</span>

                <span class="news-context-copy">{escape(clip_ui_text(article.get('suggested_action', ''), 140))}</span>

            </div>

        </div>

        <div class="news-footer">

            <a class="news-source-link" href="{escape(str(article['source_url']), quote=True)}" target="_blank" rel="noopener noreferrer">Open article ↗</a>

            <span class="news-public-note">Public source · bank impact is prototype analysis</span>

        </div>

    </div>

    """

 

def _newest_first(rows):

    return rows.sort_values(

        ["published_date", "relevance_score"], ascending=[False, False]

    ).reset_index(drop=True)

 

def _all_articles(intelligence):

    """One row per article (its highest geographic-impact country), newest first."""

    ranked = intelligence.sort_values(

        ["news_id", "geo_impact_score", "country"], ascending=[True, False, True]

    ).drop_duplicates(subset="news_id", keep="first")

    return _newest_first(ranked)

 

def _country_articles(intelligence):

    """Country-specific coverage per country, ordered by bank exposure."""

    countries = (

        intelligence.groupby("country")["bank_exposure_share_pct"]

        .max()

        .sort_values(ascending=False)

        .index

    )

    own = intelligence[intelligence["geographic_scope"] == intelligence["country"]]

    return {country: _newest_first(own[own["country"] == country]) for country in countries}

 

def _filter_impact(rows, level):

    if level == "All" or rows.empty:

        return rows

    return rows[rows["potential_impact_level"].astype(str).str.upper() == level.upper()]

 

def _render_feed(rows, empty_text):

    """A single bounded, scrollable list of news cards."""

    if rows.empty:

        st.info(empty_text)

        return

    cards = "".join(_news_card(article) for _, article in rows.iterrows())

    render_html(

        NEWS_SCROLL_CSS

        + '<section class="rn-news-scroll" aria-label="Scrollable news feed">'

        + cards

        + "</section>"

    )

 

def _render_country_tab(country, rows):

    """One country's own coverage; euro-area and EU-wide news stays under All."""

    if rows.empty:

        st.caption(f"No {country}-specific articles match this filter.")

        return

    exposure = safe_float(rows["bank_exposure_share_pct"].iloc[0])

    st.caption(

        f"{len(rows)} {country}-specific articles · {exposure:.1f}% of bank "

        f"exposure · euro-area and EU-wide news is under All."

    )

    _render_feed(rows, f"No {country}-specific articles match this filter.")

 

def render_news(s):

    render_html(

        """

        <div class="section-title">News Intelligence</div>

        <div class="section-subtitle">

            Public news mapped to the bank's country exposures, with a prepared

            view of the metric each development could touch. News is context for

            an investigation, never proven causality for an internal movement.

        </div>

        """

    )

 

    intelligence = views.cfo_news_intelligence()

    if intelligence is None or intelligence.empty:

        st.warning(

            "No news records available. Check data/news_signals.csv and "

            "data/news_geo_impact.csv."

        )

        return

 

    articles = _all_articles(intelligence)

    by_country = _country_articles(intelligence)

    focus = s.geo_focus

 

    c1, c2, c3 = st.columns(3)

    c1.metric("Articles", len(articles))

    c2.metric(

        "High impact",

        int((articles["potential_impact_level"].astype(str).str.upper() == "HIGH").sum()),

    )

    c3.metric("Highest attention", str(focus["country"]) if focus is not None else "—")

 

    first = pd.to_datetime(articles["published_date"]).min()

    last = pd.to_datetime(articles["published_date"]).max()

    st.caption(

        f"Public sources · published {first:%d %b} – {last:%d %b %Y} · "

        "bank-impact labels are prototype analysis. Not a live feed."

    )

 

    with st.expander("How are impact and attention defined?", expanded=False):

        st.markdown(

            "**High** — relevance score 80 or above: a direct possible effect on "

            "margin, funding, capital or credit quality.\n\n"

            "**Medium** — relevance 50 to 79: a plausible but indirect connection.\n\n"

            "**Low** — relevance below 50: background or broad sector context."

        )

        st.caption(

            "Relevance and confidence are prototype classifications layered on the "

            "public source, not statements by the publisher. A country's attention "

            "score combines relevance, classifier confidence and the bank's "

            "exposure to that country over the trailing 30 days of coverage. "

            "Country tabs hold country-specific coverage; euro-area and EU-wide "

            "news is under All."

        )

 

    level = st.selectbox("Impact level", IMPACT_FILTERS, key="news_filter_impact")

    visible_all = _filter_impact(articles, level)

    visible_by_country = {c: _filter_impact(r, level) for c, r in by_country.items()}

    st.caption(f"Showing {len(visible_all)} of {len(articles)} articles under All")

 

    st.markdown("#### Recent developments")

    tabs = st.tabs(

        [f"All ({len(visible_all)})"]

        + [f"{c} ({len(r)})" for c, r in visible_by_country.items()]

    )

    with tabs[0]:

        _render_feed(visible_all, "No articles match this filter. Select All.")

    for tab, (country, rows) in zip(tabs[1:], visible_by_country.items()):

        with tab:

            _render_country_tab(country, rows)
