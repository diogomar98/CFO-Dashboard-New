"""Quarterly, factsheet-only Morning Brief for the existing dual-mode cockpit.

Reuses the existing Streamlit dialog, never calls synthetic views or news
fixtures, and never presents a projected result as an actual observation.
"""
import html

import pandas as pd
import streamlit as st

from src.hud import render_html
from src.kpi_sparklines import sparkline_html
from src.real_data_mode import _quarter
from src.extended_data_loader import load_news_signals, load_news_geo_impact
from src.rag import confidence_badge, confidence_probability
from urllib.parse import urlsplit

# The grid mirrors the supplied 'Figures at a glance' reference, with the
# bank's own verified statement lines and ratio units instead of guesses.
# Six indicators intentionally differ from Group's three headline metrics
# (net profit, CET1 and LCR). Every field is sourced from the factsheet CSV.
METRICS = (
    ("roe_pct", "Return on equity", "%"),
    ("cost_income_ratio_pct", "Cost / income ratio", "%"),
    ("nim_bps", "Net interest margin", "bps"),
    ("rwa_m", "Risk-weighted assets", "€m"),
    ("loans_m", "Customer loans", "€m"),
    ("deposits_m", "Customer deposits", "€m"),
)
EXTRA = (
    ("nii_m", "Net interest income", "€m"),
    ("net_fee_income_m", "Net fee income", "€m"),
    ("nsfr_pct", "Net stable funding ratio", "%"),
    ("operating_income_m", "Operating income", "€m"),
    ("operating_expenses_m", "Operating expenses", "€m"),
    ("cost_of_risk_bps", "Cost of risk", "bps"),
    ("financial_investments_m", "Financial investments", "€m"),
)
SEGMENT_METRICS = (
    ("loans_m", "Customer loans", "€m"),
    ("deposits_m", "Customer deposits", "€m"),
    ("rwa_m", "Risk-weighted assets", "€m"),
)
DEFS = {key: (name, unit) for key, name, unit in METRICS + EXTRA}


BRIEF_CSS = """
<style>
.rb-head {
    margin: 0.15rem 0 0.7rem;
    font-family: "Cascadia Mono", Consolas, monospace;
    font-size: 0.66rem;
    color: #74B58A;
    letter-spacing: .10em;
    text-transform: uppercase;
}
.rb-primary {
    position: relative;
    height: 158px;
    padding: 1rem 1.05rem 0.8rem;
    border: 1px solid rgba(86,160,106,0.29);
    background: linear-gradient(145deg, rgba(18,30,22,0.96), rgba(7,15,10,0.96));
    border-radius: 0;
    box-sizing: border-box;
    overflow: visible;
    transition: border-color 170ms ease, background 170ms ease;
}
.rb-primary:hover, .rb-primary:focus-visible {
    border-color: rgba(95,204,130,0.71);
    background: rgba(20,38,25,0.95);
}
.rb-primary-label {
    display: block; color: #92B99D; font-size: 0.68rem;
    font-weight: 750; letter-spacing: .075em; text-transform: uppercase;
}
.rb-primary-reading { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; }
.rb-primary-value {
    color: #EEF9F0; font-family: "Cascadia Mono",Consolas,monospace;
    font-size: clamp(1.5rem, 2vw, 2.1rem); font-weight: 700;
    white-space: nowrap;
}
.rb-primary-delta {
    display: block; margin-top: 0.25rem;
    color: #B8D6C0; font-family: "Cascadia Mono",Consolas,monospace;
    font-size: 0.67rem;
}
.rb-primary-help { margin-top: 0.3rem; color: #698D75; font-size: 0.6rem; }
.rb-hover-trend {
    width: 126px;
    opacity: 1;
    transform: none;
    pointer-events: auto;
}
.rb-primary:hover .rb-hover-trend, .rb-primary:focus-visible .rb-hover-trend {
    opacity: 1; transform: none;
}
.rb-hover-trend .kpi-sparkline { width: 116px; display: flex; flex-direction: column; align-items: center; gap:2px; }
.rb-hover-trend .kpi-mini-plot {
    position:relative; display:block; width:116px; height:42px;
    transform:none; margin:0; overflow:hidden;
    border-bottom:1px solid rgba(96,146,106,.18);
}
.rb-hover-trend .kpi-mini-bar {
    position:absolute;display:block;box-sizing:border-box;
    background:linear-gradient(180deg,rgba(93,183,119,.27),rgba(37,108,66,.10));
    border:1px solid rgba(82,166,104,.15);border-bottom:0;
}
.rb-hover-trend .kpi-mini-bar.is-latest {background:rgba(78,200,111,.47);}
.rb-hover-trend .kpi-mini-segment {
    position:absolute;display:block;height:2px;background:rgba(188,243,204,.75);
    transform-origin:left center;z-index:2;
}
.rb-hover-trend .kpi-mini-dot {
    position:absolute;display:block;width:5px;height:5px;
    border-radius:50%;box-sizing:border-box;
    background:rgba(188,243,204,.75);border:1px solid #32744A;z-index:3;
}
.rb-hover-trend .kpi-mini-dot.is-latest {width:6px;height:6px;background:#C3F2D1;}
.rb-hover-trend .kpi-sparkline-period {
    display:flex;justify-content:space-between;width:116px;
    color:#8ABA98;font-size:.51rem;font-family:"Cascadia Mono",Consolas,monospace;
}
.rb-commentary { padding: 0.8rem 1rem; background: rgba(31,63,38,0.10); border-left: 2px solid #3D9961; }
.rb-commentary-line { margin: .35rem 0; color:#D0E1D2; font-size:.82rem; line-height:1.46; }
.rb-plot-card {
    padding: 0.8rem .9rem .65rem;
    background: rgba(14,28,19,0.78);
    border: 1px solid rgba(71,125,82,0.25);
    box-sizing: border-box;
    height: 218px;
    border-radius: 0;
}
.rb-plot-head { display:flex; justify-content:space-between; align-items:baseline; gap:.4rem; }
.rb-plot-name { font-size:.76rem; font-weight:750; color:#C9E3CE; }
.rb-plot-unit { font-size:.58rem; color:#78A989; white-space:nowrap; }
.rb-plot {
    height: 130px; position: relative;
    margin: .55rem 0 .1rem;
    padding-bottom: 1px;
    border-bottom: 1px solid rgba(105,168,119,0.27);
}
.rb-plot-baseline { height:1px; background:rgba(145,177,153,.32); position:absolute;left:0;right:0; }
.rb-col { position:absolute;top:0;bottom:0; }
.rb-bar {
    position:absolute; width:60%; left:20%;
    background: rgba(79,188,115,0.28);
    border:1px solid rgba(116,209,141,0.22);
    box-sizing:border-box;
}
.rb-bar.is-latest {background:rgba(62,206,110,0.58);border-color:rgba(114,229,151,0.63);}
.rb-bar-value {
    display:block;position:absolute;left:-45%;width:190%;text-align:center;
    font-family:"Cascadia Mono",Consolas,monospace;
    color:#C6DFCC; font-size:.55rem; white-space:nowrap;
}
.rb-col.is-latest .rb-bar-value {color:#A1F2BA;font-weight:750;}
.rb-bar-date {
    position:absolute;bottom:-17px;left:-28%;width:156%;
    text-align:center; font-size:.53rem;color:#8CAF98; white-space:nowrap;
}
.rb-chart-caption {font-size:.56rem;color:#648670;}
.rb-section-break { margin:1.1rem 0 .6rem; border-top:1px solid rgba(95,165,112,.20);padding-top:.7rem; }
.rb-news-frame { padding:1rem 1.1rem; border:1px solid rgba(82,125,155,.30);background:rgba(15,25,29,.60); }
.rb-news-head { font-size:.76rem;color:#BBD4DB;font-weight:700; }
.rb-news-note { font-size:.7rem;color:#97AFB2;line-height:1.55; margin-top:.3rem; }
/* Existing external-news feed colours/classes, full-width responsive layout. */
.rb-news-wide {width:100%;box-sizing:border-box;padding:.85rem 1rem .9rem;}
.rb-news-clarifier {color:#91ABA1;font-size:.70rem;line-height:1.5;padding:.25rem 0 .75rem;}
.rb-news-clarifier strong {color:#B6CCE0;}
.rb-news-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:1.7rem;row-gap:.2rem;}
.rb-news-grid .rb-news-item {min-width:0;box-sizing:border-box;border-top:1px solid rgba(124,166,201,.18);padding:.8rem 0 .7rem;}
.rb-news-grid .feed-headline {overflow-wrap:anywhere;}
.rb-news-grid .feed-foot {flex-wrap:wrap;}
.rb-news-grid .feed-item-top {row-gap:.3rem;}
@media (max-width:820px) {
  .rb-news-grid {grid-template-columns:1fr;}
  .rb-news-wide .feed-frame-head {flex-wrap:wrap;}
}
@media (max-width:1000px){
    .rb-primary {height:175px;padding:.7rem;}
    .rb-primary-reading {display:flex;align-items:center;}
    .rb-hover-trend {display:block;width:116px;flex:0 0 116px;}
    .rb-primary-value {font-size:clamp(1.15rem,2.5vw,1.75rem);}

}
</style>
"""


def chart_rows(frame, metric, quarters=5):
    """Five latest *non-null* reported quarters; no synthetic interpolation."""
    if metric not in frame:
        return []
    clean = frame[["date", metric]].dropna().sort_values("date").tail(quarters)
    return [(_quarter(row["date"]), float(row[metric])) for _, row in clean.iterrows()]


def compare_actuals(frame, metric):
    """Latest actual, prior-quarter actual and same-quarter last year, if present."""
    clean = frame[["date", metric]].dropna().sort_values("date")
    if clean.empty:
        return None
    latest = clean.iloc[-1]
    # Quarter comparisons use accounting periods rather than subtracting
    # calendar months (30 June - 3 months is 30 March, not 31 March).
    current_quarter = pd.Timestamp(latest["date"]).to_period("Q")
    quarters = clean["date"].dt.to_period("Q")
    earlier = clean.loc[quarters == current_quarter - 1]
    year_ago = clean.loc[quarters == current_quarter - 4]
    return {
        "quarter": _quarter(latest["date"]),
        "now": float(latest[metric]),
        "previous": float(earlier.iloc[0][metric]) if not earlier.empty else None,
        "year_ago": float(year_ago.iloc[0][metric]) if not year_ago.empty else None,
    }


def _amount(value, unit, rounded=False):
    if value is None or pd.isna(value):
        return "—"
    if unit == "€m":
        return f"€{value:,.0f}m" if rounded else f"€{value:,.1f}m"
    if unit == "%":
        return f"{value:.2f}%"
    return f"{value:.1f}bps"


def _delta(value, prev, unit):
    if prev is None or pd.isna(prev):
        return "Prior period unavailable"
    change = value - prev
    suffix = "pp" if unit == "%" else ("bps" if unit == "bps" else "m")
    if suffix == "m":
        return f"{change:+,.1f}m"
    return f"{change:+.2f}{suffix}"


def _metric_bar_chart(rows, name, unit):
    """Accessible HTML/CSS five-quarter bars with a zero-including y-axis."""
    if len(rows) < 1:
        return '<div class="rb-plot-card">No reported values available.</div>'
    observed = [v for _, v in rows]
    lo, hi = min(0.0, *observed), max(0.0, *observed)
    if lo == hi:
        hi = lo + 1.0
    pad = (hi - lo) * 0.075
    lo = lo - pad if lo < 0 else lo
    hi = hi + pad if hi > 0 else hi
    span = hi - lo
    baseline_pct = 100 * hi / span  # measured from top of plot
    cols = []
    n = len(rows)
    for idx, (quarter, val) in enumerate(rows):
        # y is measured downward from chart top.
        y_pct = 100 * (hi - val) / span
        top_pct = min(y_pct, baseline_pct)
        h_pct = max(0.5, abs(baseline_pct - y_pct))
        x_pct = 100 * idx / n
        col_w = 100 / n
        latest_class = " is-latest" if idx == n - 1 else ""
        # value label sits near the top of each bar, but never above the plot.
        label_top = max(1.0, top_pct - 13.0) if val >= 0 else min(86.0, baseline_pct + h_pct + 2.0)
        quarter_short = html.escape(quarter.replace(" 20", " '"))
        value_label = html.escape(_amount(val, unit, rounded=True))
        tooltip = html.escape(f"{quarter}: {_amount(val, unit)}", quote=True)
        cols.append(
            f'<div class="rb-col{latest_class}" title="{tooltip}" '
            f'style="left:{x_pct:.3f}%;width:{col_w:.3f}%">'
            f'<span class="rb-bar{latest_class}" '
            f'style="top:{top_pct:.3f}%;height:{h_pct:.3f}%"></span>'
            f'<span class="rb-bar-value" style="top:{label_top:.3f}%">{value_label}</span>'
            f'<span class="rb-bar-date">{quarter_short}</span>'
            '</div>'
        )
    safe_name = html.escape(name)
    return (
        '<div class="rb-plot-card">'
        f'<div class="rb-plot-head"><span class="rb-plot-name">{safe_name}</span>'
        f'<span class="rb-plot-unit">{html.escape(unit)}</span></div>'
        f'<div class="rb-plot" role="img" aria-label="{safe_name}: '
        f'{len(rows)} reported quarters, latest {_amount(observed[-1], unit)}">'
        f'<span class="rb-plot-baseline" style="top:{baseline_pct:.3f}%"></span>'
        + "".join(cols)
        + '</div></div>'
    )


def _primary_card(title, value, comparison, dates, values, detail):
    chart = sparkline_html(values, label=title, dates=dates)
    return (
        '<div class="rb-primary" tabindex="0">'
        f'<span class="rb-primary-label">{html.escape(title)}</span>'
        '<div class="rb-primary-reading">'
        f'<span class="rb-primary-value">{html.escape(value)}</span>'
        f'<span class="rb-hover-trend">{chart}</span>'
        '</div>'
        f'<span class="rb-primary-delta">{html.escape(comparison)} QoQ</span>'
        f'<div class="rb-primary-help">{html.escape(detail)} · reported quarterly trend</div>'
        '</div>'
    )


def _key_insights(s):
    """Derived descriptions only from actual source-backed card narratives."""
    if s.business_line:
        return [
            f"{card['label'].title()}: {card['context']}"
            for card in s.kpi_cards[:3]
        ]
    by_label = {card["label"]: card for card in s.kpi_cards}
    return [
        "Profitability: " + by_label["QUARTERLY NET PROFIT"]["why"],
        "Capital: " + by_label["CET1 RATIO"]["why"],
        "Liquidity: " + by_label["LIQUIDITY COVERAGE"]["why"],
    ]


def _primary_cards(s, data):
    if s.business_line:
        headline = (
            ("loans_m", "Customer loans", "€m"),
            ("deposits_m", "Customer deposits", "€m"),
            ("rwa_m", "Risk-weighted assets", "€m"),
        )
    else:
        headline = (
            ("net_profit_m", "Net profit", "€m"),
            ("cet1_ratio_pct", "CET1 ratio", "%"),
            ("lcr_pct", "Liquidity coverage", "%"),
        )
    cols = st.columns(3, gap="medium")
    for col, (metric, name, unit) in zip(cols, headline):
        history = chart_rows(data, metric, quarters=10)
        stat = compare_actuals(data, metric)
        with col:
            if stat is None:
                st.caption("Not reported")
                continue
            summary = _amount(stat["now"], unit, rounded=True)
            values = [v for _, v in history]
            dates = [d for d, _ in history]
            render_html(_primary_card(
                name, summary, _delta(stat["now"], stat["previous"], unit),
                dates, values,
                "Selected business line" if s.business_line else "ABN AMRO Group",
            ))
            if st.button(
                "Inspect quarterly trend ↗", key=f"rb_primary_{metric}",
                use_container_width=True,
            ):
                st.session_state["rb_focus"] = metric
                st.session_state["rb_expanded"] = True
            if not s.business_line and metric == "cet1_ratio_pct":
                if st.button(
                    "Ask Copilot about CET1 ↗",
                    key="rb_ask_cet1_copilot",use_container_width=True,
                ):
                    from src.reported_copilot_balloon import prepare_cet1_investigation
                    prepare_cet1_investigation()
                    st.caption("CET1 question prepared in the floating Copilot.")


def _details(frame, key, unit, name, s):
    stat = compare_actuals(frame, key)
    if stat is None:
        st.info("No source-backed data available for this metric.")
        return
    st.markdown(f"#### {name} · historical drilldown")
    st.caption(f"{stat['quarter']} · Actual reported figures, not estimated or forecast")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Reported actual", _amount(stat["now"], unit))
    with c2:
        st.metric("Change QoQ", _delta(stat["now"], stat["previous"], unit))
    with c3:
        st.metric("Change YoY", _delta(stat["now"], stat["year_ago"], unit))

    hist = frame[["date", key]].dropna().sort_values("date")
    chart_data = hist.set_index("date")[key]
    st.bar_chart(chart_data, use_container_width=True, height=230)
    table = hist.copy()
    table["quarter"] = table["date"].map(_quarter)
    table["value"] = table[key].map(lambda x: _amount(x, unit))
    table["QoQ"] = table[key].diff().map(lambda v: _delta(v, 0, unit) if pd.notna(v) else "—")
    table["YoY"] = (table[key] - table[key].shift(4)).map(
        lambda v: _delta(v, 0, unit) if pd.notna(v) else "—"
    )
    st.dataframe(
        table[["quarter", "value", "QoQ", "YoY"]].iloc[::-1],
        hide_index=True, use_container_width=True,
    )

    # Reuse the existing CFO explanations only for the matching Group KPI,
    # rather than fabricating attribution for other reported series.
    kpi_by_field = {
        "net_profit_m": "QUARTERLY NET PROFIT",
        "cet1_ratio_pct": "CET1 RATIO",
        "lcr_pct": "LIQUIDITY COVERAGE",
        "nii_m": "NET INTEREST INCOME",
    }
    if not s.business_line and key in kpi_by_field:
        match = next(
            (card for card in s.kpi_cards if card["label"] == kpi_by_field[key]), None
        )
        if match:
            st.markdown("**Why**")
            st.write(match["why"])
            st.markdown("**Impact**")
            st.write(match["impact"])
            st.markdown("**Next**")
            st.write(match["next"])
            return
    st.caption(
        "This analysis is limited to sourced quarterly levels and their calculated "
        "QoQ/YoY movements. Causal attribution and management thresholds are "
        "not inferred from the factsheet."
    )


def _expanded_grid(s, frame):
    metrics = () if s.business_line else METRICS
    st.markdown("### Figures at a glance")
    if s.business_line:
        st.info(
            "Only segment loans, deposits and RWA are disclosed in this data package "
            "and those are already shown above. Use the headline cards' Inspect "
            "quarterly trend action for the complete segment history; additional "
            "segment KPIs have not been invented."
        )
    else:
        st.caption(
            "Six additional KPIs · last five reported quarters · "
            "bar heights include zero · latest quarter highlighted"
        )

    for start in range(0, len(metrics), 3):
        cols = st.columns(3, gap="medium")
        for col, (metric, name, unit) in zip(cols, metrics[start:start + 3]):
            with col:
                render_html(_metric_bar_chart(chart_rows(frame, metric), name, unit))
                if st.button("Explore metric ↗", key=f"rb_grid_{metric}", use_container_width=True):
                    st.session_state["rb_focus"] = metric
    if not s.business_line:
        options = {f"{name} ({unit})": key for key, name, unit in EXTRA}
        picked = st.selectbox(
            "Explore another reported financial metric",
            ["Select metric"] + list(options), key="rb_extra_metric",
        )
        if picked != "Select metric":
            if st.button("Open selected metric ↗", key="rb_select_extra"):
                st.session_state["rb_focus"] = options[picked]

    focus = st.session_state.get("rb_focus")
    available = {metric: (name, unit) for metric, name, unit in metrics}
    if s.business_line:
        available.update({metric: (name, unit) for metric, name, unit in SEGMENT_METRICS})
    else:
        available.update({
            "net_profit_m": ("Net profit", "€m"),
            "cet1_ratio_pct": ("CET1 ratio", "%"),
            "lcr_pct": ("Liquidity coverage", "%"),
        })
    if not s.business_line:
        available.update({metric: (name, unit) for metric, name, unit in EXTRA})
    if focus in available:
        name, unit = available[focus]
        st.markdown('<div class="rb-section-break"></div>', unsafe_allow_html=True)
        if st.button("Close detailed analysis ×", key="rb_detail_close"):
            st.session_state.pop("rb_focus", None)
        else:
            _details(frame, focus, unit, name, s)


def load_existing_news():
    """The same CSV-backed external feed and ranking as Synthetic Morning Brief.

    This returns *prototype* news, not factsheet financials or verified live news.
    """
    news = load_news_signals()
    geo = load_news_geo_impact()
    if news is None or news.empty:
        return pd.DataFrame()
    if not {"news_id", "published_date", "headline"}.issubset(news.columns):
        return pd.DataFrame()
    news = news.copy()
    news["published_date"] = pd.to_datetime(news["published_date"], errors="coerce")
    news = news.dropna(subset=["published_date", "headline"])
    if news.empty:
        return news
    if geo is not None and not geo.empty and "news_id" in geo.columns:
        side = geo.drop(columns=["published_date", "impact_direction"], errors="ignore")
        news = news.merge(side, on="news_id", how="inner")
    if news.empty:
        return news
    latest = news["published_date"].max()
    recent = news[news["published_date"] >= latest - pd.Timedelta(days=13)].copy()
    if recent.empty:
        return recent
    if {"geo_impact_score", "country"}.issubset(recent.columns):
        recent = recent.sort_values(
            ["news_id", "geo_impact_score", "country"],
            ascending=[True, False, True],
        )
    recent = recent.drop_duplicates(subset="news_id", keep="first")
    ordering = [k for k in ("relevance_score", "published_date") if k in recent]
    return recent.sort_values(ordering, ascending=[False] * len(ordering)).reset_index(drop=True)


def _prototype_article(article):
    """The original external news layout, colours, links and confidence badge."""
    def val(key, default=""):
        item = article.get(key, default)
        return default if pd.isna(item) else str(item)

    category = html.escape(val("category", "News"))
    headline = html.escape(val("headline"))
    source = html.escape(val("source", "External source"))
    level = val("potential_impact_level", "UNRATED").upper()
    if level not in {"HIGH", "MEDIUM", "LOW"}:
        level = "UNRATED"
    date = pd.to_datetime(article["published_date"]).strftime("%d %b %Y")
    detail = html.escape(val("bank_impact_summary")[:200])
    metric = html.escape(val("primary_affected_metric", "Not classified"))
    try:
        confidence = float(article.get("confidence_score", float("nan")))
    except (TypeError, ValueError):
        confidence = float("nan")
    if pd.notna(confidence):
        conf = confidence_badge(confidence_probability(
            confidence, "Prototype classifier confidence in potential bank impact"
        ))
    else:
        conf = '<span class="feed-source">Confidence unavailable</span>'
    url = val("source_url").strip()
    parsed = urlsplit(url)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        source_link = (
            f'<a class="news-source-link" href="{html.escape(url, quote=True)}" '
            f'target="_blank" rel="noopener noreferrer">{source} ↗</a>'
        )
    else:
        source_link = f'<span class="feed-source">{source} · source link unavailable</span>'
    return (
        '<article class="feed-item rb-news-item">'
        '<div class="feed-item-top">'
        f'<span class="feed-tag">{category}</span>'
        f'<span class="feed-date">{date}</span>'
        f'<span class="feed-status status-impact-{level.lower()}">{html.escape(level.title())} impact</span>'
        '</div>'
        f'<div class="feed-headline">{headline}</div>'
        f'<div class="feed-detail">{detail}</div>'
        f'<div class="feed-detail"><strong>Potential metric</strong> {metric}</div>'
        '<div class="feed-foot">' + conf + source_link + '</div></article>'
    )


def _external_news():
    """Use official public ECB sources, preserving the original wide news layout.

    Source excerpts have not been checked for bank-specific economic impact.
    News relevance is separately evaluated on the News Intelligence page.
    """
    from src.reported_news import recent_official_articles
    st.markdown("### External news & developments")
    articles, warnings = recent_official_articles()
    cards=[]
    for article in articles[:4]:
        headline=html.escape(article["headline"])
        summary=html.escape(article["summary"][:190])
        source=html.escape(article["source"])
        day=html.escape(article["published"][:10])
        url=html.escape(article["url"],quote=True)
        cards.append(
            '<article class="feed-item rb-news-item">'
            '<div class="feed-item-top">'
            '<span class="feed-tag">ECB / public</span>'
            f'<span class="feed-date">{day}</span>'
            '<span class="feed-status status-impact-low">Unrated</span>'
            '</div>'
            f'<div class="feed-headline">{headline}</div>'
            f'<div class="feed-detail">{summary}</div>'
            '<div class="feed-detail"><strong>Potential metric</strong> '
            'See News Intelligence for AI relevance classification</div>'
            '<div class="feed-foot">'
            '<span class="feed-source">Official public news · unverified bank impact</span>'
            f'<a class="news-source-link" href="{url}" target="_blank" '
            f'rel="noopener noreferrer">{source} ↗</a>'
            '</div></article>'
        )
    if cards:
        content='<div class="rb-news-grid">'+"".join(cards)+'</div>'
        last_update=html.escape(articles[0]["published"][:10])
    else:
        content=(
            '<div class="feed-empty">Official ECB feeds unavailable. '
            'No synthetic news records have been substituted. '
            +html.escape("; ".join(warnings[:2]))+'</div>'
        )
        last_update="Official source unavailable"
    render_html(
        '<section class="feed-frame is-external rb-news-wide">'
        '<div class="feed-frame-head">'
        '<span class="feed-frame-title">External news</span>'
        f'<span class="feed-frame-note">Official ECB RSS · {last_update}</span>'
        '</div>'
        '<div class="rb-news-clarifier">'
        'Headlines are live public information and are not evidence of '
        'causal impact on ABN financials. See News Intelligence for AI '
        'relevance and an independently verified ECB-rate scenario.'
        '</div>'+content+'</section>'
    )



def render_reported_brief(s):
    """Top three KPIs → commentary → optional expanded charts → external news."""
    render_html(BRIEF_CSS)
    frame = (
        s.reported_segments.loc[
            s.reported_segments["business_line"] == s.business_line
        ].sort_values("date")
        if s.business_line else s.reported_group
    )
    scope = s.business_line or "ABN AMRO Group"
    latest = frame.iloc[-1]
    render_html(
        '<div class="rb-head">Executive health check / '
        + html.escape(scope) + " / " + _quarter(latest["date"]) + '</div>'
    )
    _primary_cards(s, frame)
    st.markdown("#### Executive commentary")
    for sentence in _key_insights(s):
        st.write("• " + sentence)
    st.caption("Figures are quarterly reported actuals. Momentum signals are not bank-approved RAG thresholds.")

    open_now = st.session_state.get("rb_expanded", False)
    if st.button(
        "Collapse financial view ▲" if open_now else "Expand financial view ▼",
        key="rb_toggle_expanded", use_container_width=True,
    ):
        st.session_state["rb_expanded"] = not open_now
        if open_now:
            # Close the detail as well: an old focus must not re-open the
            # financial grid immediately after pressing Collapse.
            st.session_state.pop("rb_focus", None)
    if st.session_state.get("rb_expanded", False):
        _expanded_grid(s, frame)

    render_html('<div class="rb-section-break"></div>')
    _external_news()
    st.caption("Source: ABN AMRO Q2 2026 factsheet · Quarterly P&L and quarter-end balances.")
