"""Source-backed quarterly Horizon with the same executive layout as Synthetic.

Four top-line cards, actual-to-baseline NIM trajectory, a forward lens,
assumptions and What-If handoff. Does not touch the Synthetic renderer.
"""
import html

import altair as alt
import pandas as pd
import streamlit as st

from src.hud import module_url, render_html
from src.reported_horizon_engine import (
    FORECAST_QUARTERS, CAPS, build_quarterly_horizon,
    default_quarterly_assumptions,
)


HORIZON_CSS = """
<style>
.rh-description {font-size:.79rem;color:#A2B9AA;line-height:1.5;max-width:1100px;margin:.25rem 0 .85rem;}
.rh-pill {display:inline-flex;margin:.55rem 0 .5rem;padding:.25rem .5rem;border:1px solid rgba(211,176,97,.42);
 color:#E8CF92;background:rgba(143,117,55,.09);font-size:.64rem;font-weight:700;letter-spacing:.045em;}
.rh-metric {min-height:136px;padding:1rem 1rem .7rem;background:linear-gradient(145deg,rgba(20,31,24,.85),rgba(7,13,10,.87));
 border:1px solid rgba(106,158,116,.28);box-sizing:border-box;}
.rh-metric-name {font-size:.64rem;letter-spacing:.06em;font-weight:750;color:#93B69E;text-transform:uppercase;}
.rh-metric-value {margin:.36rem 0;font-size:clamp(1.2rem,1.65vw,1.92rem);
 font-weight:750;color:#F0F7F1;font-family:"Cascadia Mono",Consolas,monospace;white-space:nowrap;}
.rh-metric-detail {font-size:.63rem;color:#A1BEAA;line-height:1.4;}
.rh-metric-foot {margin-top:.4rem;font-size:.54rem;letter-spacing:.055em;color:#E1C991;text-transform:uppercase;}
.rh-model-label {font-family:"Cascadia Mono",Consolas,monospace;font-size:.65rem;color:#87B49A;letter-spacing:.06em;}
.rh-note {font-size:.72rem;color:#9CBAA6;line-height:1.55;}
.rh-legend {display:flex;align-items:center;gap:1.2rem;flex-wrap:wrap;margin:.35rem 0 1rem;}
.rh-legend span {display:inline-flex;align-items:center;gap:.4rem;font-size:.63rem;color:#A3C4AE;}
.rh-key {display:inline-block;width:21px;height:3px;background:#32C867;}
.rh-key.is-projected {background:#BC96F3;border-top:1px dashed #BC96F3;}
@media(max-width:1000px){.rh-metric{min-height:115px;padding:.75rem}.rh-metric-value{font-size:1.2rem;}}
</style>
"""


def _card(label, value, detail, *, actual=False):
    return (
        '<div class="rh-metric">'
        f'<div class="rh-metric-name">{html.escape(label)}</div>'
        f'<div class="rh-metric-value">{html.escape(value)}</div>'
        f'<div class="rh-metric-detail">{html.escape(detail)}</div>'
        f'<div class="rh-metric-foot">{"Reported actual" if actual else "Illustrative baseline"}</div>'
        '</div>'
    )


def _forecast_chart(history, metric="nim_pct"):
    """The Synthetic-style two-colour handoff, plotted over real quarters."""
    fields = {
        "nim_pct": ("NIM (%)", ".3f"),
        "nii_m": ("Quarterly NII (€m)", ",.1f"),
        "loans_m": ("Customer loans (€m)", ",.0f"),
        "deposits_m": ("Customer deposits (€m)", ",.0f"),
    }
    title, fmt = fields[metric]
    frame = history.dropna(subset=[metric]).copy()
    quarters = history["quarter"].tolist()
    actual = frame[frame["series"] == "Actual"]
    baseline = frame[frame["series"] == "Baseline"]
    if actual.empty:
        return alt.Chart(pd.DataFrame({"quarter": [], metric: []})).mark_line()
    if not baseline.empty:
        bridge = actual.tail(1).copy()
        bridge["series"] = "Baseline"
        baseline = pd.concat([bridge, baseline], ignore_index=True)
    low, high = float(frame[metric].min()), float(frame[metric].max())
    buffer = max((high - low) * 0.12, 0.05 if metric == "nim_pct" else max(abs(high) * .015, 1))
    scale = alt.Scale(domain=[low - buffer, high + buffer])
    x = alt.X("quarter:N", sort=quarters, title=None, axis=alt.Axis(
        labelColor="#95B99D", labelAngle=0, domainColor="#426850",
        tickColor="#426850", labelFontSize=10,
    ))
    y = alt.Y(f"{metric}:Q", title=title, scale=scale, axis=alt.Axis(
        labelColor="#A4C4AF", titleColor="#A4C4AF", gridColor="#203629",
        labelFontSize=10,
    ))
    actual_tooltip = [
        alt.Tooltip("quarter:N", title="Reported quarter"),
        alt.Tooltip(f"{metric}:Q", title=f"Reported {title}", format=fmt),
        alt.Tooltip("source:N", title="Source"),
    ]
    forecast_tooltip = [
        alt.Tooltip("quarter:N", title="Forecast quarter"),
        alt.Tooltip(f"{metric}:Q", title=f"Illustrative {title}", format=fmt),
        alt.Tooltip("source:N", title="Method"),
    ]
    a = (alt.Chart(actual).mark_line(color="#32C867", strokeWidth=3)
         .encode(x=x, y=y, tooltip=actual_tooltip))
    ap = (alt.Chart(actual).mark_circle(color="#32C867", size=64, stroke="#0A100C", strokeWidth=1)
          .encode(x=x, y=y, tooltip=actual_tooltip))
    b = (alt.Chart(baseline).mark_line(color="#BC96F3", strokeWidth=3, strokeDash=[7,5])
         .encode(x=x, y=y, tooltip=forecast_tooltip))
    bp = (alt.Chart(baseline.iloc[1:]).mark_point(filled=True,color="#120F18",stroke="#C4AEFA",
                                                 strokeWidth=2,size=70)
          .encode(x=x, y=y, tooltip=forecast_tooltip))
    return (a+ap+b+bp).properties(height=350).configure_view(strokeOpacity=0).configure(
        background="#08100C"
    )


def _default_state(group):
    if "rh_assumptions" not in st.session_state:
        st.session_state["rh_assumptions"] = default_quarterly_assumptions(group)
    return dict(st.session_state["rh_assumptions"])


def _assumption_form(group):
    current = _default_state(group)
    with st.expander("Model assumptions · edit quarterly baseline", expanded=False):
        st.caption(
            "Starting values are medians of the last three reported QoQ changes. "
            "The 50% NIM momentum decay is an explicit modelling choice. "
            "These are NOT bank guidance, approved budgets or verified market expectations."
        )
        with st.form("rh_quarterly_assumptions"):
            c1,c2 = st.columns(2)
            with c1:
                nim_change = st.number_input(
                    "First projected quarter NIM movement (bps)",
                    min_value=-40.0,max_value=40.0,value=float(current["nim_change_bps"]),
                    step=0.5,format="%.2f",
                )
                nii_growth = st.number_input(
                    "Quarterly NII growth (%)",
                    min_value=-15.0,max_value=15.0,value=float(current["nii_growth_pct"]),
                    step=0.5,format="%.2f",
                )
            with c2:
                loan_growth = st.number_input(
                    "Quarterly customer loans growth (%)",
                    min_value=-10.0,max_value=10.0,value=float(current["loan_growth_pct"]),
                    step=0.5,format="%.2f",
                )
                deposit_growth = st.number_input(
                    "Quarterly deposits growth (%)",
                    min_value=-10.0,max_value=10.0,value=float(current["deposit_growth_pct"]),
                    step=0.5,format="%.2f",
                )
            decay = st.slider(
                "NIM momentum retention after each forward quarter (%)",
                min_value=0,max_value=100,value=int(round(current["nim_decay"] * 100)),step=5,
            )
            saved = st.form_submit_button("Apply assumptions", use_container_width=True)
        if saved:
            st.session_state["rh_assumptions"] = {
                "nim_change_bps": float(nim_change),
                "nii_growth_pct": float(nii_growth),
                "loan_growth_pct": float(loan_growth),
                "deposit_growth_pct": float(deposit_growth),
                "nim_decay": float(decay)/100,
            }
        if st.button("Reset to reported-history medians", key="rh_reset", use_container_width=True):
            st.session_state["rh_assumptions"] = default_quarterly_assumptions(group)
    return dict(st.session_state["rh_assumptions"])


def _lens(result, metrics):
    a = metrics["assumptions"]
    fy = metrics["fiscal_year"]
    fy_total = metrics["fy_nii_m"]
    fy_content = (
        f"€{fy_total/1000:.2f}bn includes "
        f"€{metrics['fy_nii_actual_m']/1000:.2f}bn actually reported "
        f"and €{metrics['fy_nii_projected_m']/1000:.2f}bn modelled."
        if pd.notna(fy_total) else
        "A complete FY NII total cannot be calculated from the available reported quarters."
    )
    projected = result[result["series"]=="Baseline"]
    first_label = projected.iloc[0]["quarter"] if not projected.empty else "Next quarter"
    last_label = projected.iloc[-1]["quarter"] if not projected.empty else ""
    return f"""
    <div class="forward-lens-panel">
        <div class="forward-lens-kicker">Forward lens · modelled</div>
        <div class="forward-lens-title">What is the baseline telling us?</div>
        <div class="forward-lens-row">
            <span class="forward-lens-label">Repricing proxy</span>
            <span class="forward-lens-value">Starting from reported NIM
                <strong>{metrics['reported_nim_pct']:.3f}%</strong>,
                the next-quarter movement is assumed to be
                <strong>{a['nim_change_bps']:+.2f} bps</strong>.
                Each subsequent move retains <strong>{a['nim_decay']*100:.0f}%</strong>
                of the previous move. This is not an observed loan/deposit repricing rate.</span>
        </div>
        <div class="forward-lens-row">
            <span class="forward-lens-label">Funding</span>
            <span class="forward-lens-value">Customer loans are projected at
                <strong>{a['loan_growth_pct']:+.2f}% QoQ</strong> and deposits at
                <strong>{a['deposit_growth_pct']:+.2f}% QoQ</strong>.
                These are balance-sheet stock assumptions, not average earning assets.</span>
        </div>
        <div class="forward-lens-row">
            <span class="forward-lens-label">Income</span>
            <span class="forward-lens-value">Projected quarterly NII compounds at
                <strong>{a['nii_growth_pct']:+.2f}% QoQ</strong>, separately from NIM because
                the factsheet does not provide a complete earning-assets/yield bridge.</span>
        </div>
        <div class="forward-lens-row">
            <span class="forward-lens-label">Outcome</span>
            <span class="forward-lens-value">FY <strong>{fy}</strong> NII: {fy_content}
                The illustration runs from <strong>{html.escape(first_label)}</strong>
                to <strong>{html.escape(last_label)}</strong>.</span>
        </div>
        <div class="forward-lens-row">
            <span class="forward-lens-label">Confidence</span>
            <span class="forward-lens-value">No calibrated statistical confidence or
                90% interval is available from the provided source. Only a deterministic
                sensitivity to the editable assumptions is shown.</span>
        </div>
        <div class="forward-lens-row">
            <span class="forward-lens-label">Plan gap</span>
            <span class="forward-lens-value">ABN's official forecast, management targets
                and approved budget are not contained in the source package.</span>
        </div>
        <div class="forward-lens-meaning">
            <strong>How to use it</strong>
            Start with a traceable quarterly reference case. Challenge the assumptions
            rather than treating an extrapolation as an official forecast.
            The What-If Engine will eventually use the same inputs and accounting basis.
        </div>
    </div>"""


def render_reported_horizon(s):
    """Same Horizon information architecture, with source-aware quarter handling."""
    render_html(HORIZON_CSS)
    group = s.reported_group.sort_values("date")
    if s.business_line:
        st.info(
            f"Reporting scope: {s.business_line}. NIM and NII are not disclosed "
            "by this segment in the uploaded factsheet. The Horizon financial "
            "forecast below is explicitly for ABN AMRO GROUP."
        )
    st.markdown('<div class="section-title">Where are we heading?</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="rh-description">'
        "A deterministic quarterly reference from reported ABN AMRO actuals. "
        "The next four quarters are illustrative extrapolations, not an official bank forecast."
        '</div>', unsafe_allow_html=True,
    )
    render_html('<div class="rh-pill">Group actuals + explicit assumptions · forecast unapproved</div>')
    assumptions = _assumption_form(group)
    forecast, metrics = build_quarterly_horizon(group, assumptions, FORECAST_QUARTERS)
    next_q = forecast[forecast["series"]=="Baseline"].iloc[0]["quarter"]
    ye_nim = metrics["year_end_nim_pct"]
    fy_nii = metrics["fy_nii_m"]
    card_data = [
        (
            f"{metrics['year_end_quarter']} NIM baseline",
            f"{ye_nim:.2f}%" if pd.notna(ye_nim) else "Unavailable",
            f"{metrics['nim_change_to_year_end_bps']:+.2f}bps vs {metrics['latest_quarter']}"
            if pd.notna(ye_nim) else "No supported year-end value",
        ),
        (
            f"FY{metrics['fiscal_year']} NII baseline",
            f"€{fy_nii/1000:.2f}bn" if pd.notna(fy_nii) else "Unavailable",
            f"€{metrics['fy_nii_actual_m']/1000:.2f}bn actual + "
            f"€{metrics['fy_nii_projected_m']/1000:.2f}bn illustrative",
        ),
        (
            f"{next_q} NIM step",
            f"{metrics['first_quarter_nim_step_bps']:+.2f}bps",
            f"vs reported {metrics['latest_quarter']}",
        ),
        (
            "Balance-sheet run-rate",
            f"{assumptions['loan_growth_pct']:+.2f}%",
            f"Customer loans / quarter · deposits {assumptions['deposit_growth_pct']:+.2f}%",
        ),
    ]
    for col, (label, value, detail) in zip(st.columns(4), card_data):
        with col:
            render_html(_card(label, value, detail))

    st.write("")
    chart_col, lens_col = st.columns([1.72,0.90],gap="large")
    with chart_col:
        render_html(
            '<div class="module-code">Forward trajectory / actual → baseline</div>'
            '<div class="section-title">Quarterly outlook</div>'
        )
        metric_choice = st.selectbox(
            "View trajectory", [
                "Net interest margin", "Net interest income",
                "Customer loans", "Customer deposits",
            ], key="rh_chart_metric",
        )
        field = {
            "Net interest margin":"nim_pct",
            "Net interest income":"nii_m",
            "Customer loans":"loans_m",
            "Customer deposits":"deposits_m",
        }[metric_choice]
        render_html(
            '<div class="rh-legend">'
            '<span><i class="rh-key"></i>Reported actuals</span>'
            '<span><i class="rh-key is-projected"></i>Deterministic baseline</span>'
            '</div>'
        )
        st.altair_chart(_forecast_chart(forecast,metric=field),use_container_width=True)
        st.caption(
            "Green = published quarterly actuals; dashed purple = mechanical "
            "projections based on the assumption panel. No official plan or "
            "statistically validated 90% confidence band is implied."
        )
    with lens_col:
        render_html(_lens(forecast, metrics))

    render_html(
        '<div class="module-action-row">'
        f'<a class="module-action-link" href="{module_url("scenario")}" target="_self">'
        'Stress key assumptions in What-If (next stage) →</a>'
        '<span class="rh-model-label">Copilot / real-data grounding pending</span>'
        '</div>'
    )
    st.caption(
        "Source: ABN AMRO Q2 2026 factsheet (Group disclosures only). "
        "Starting assumptions = median of last 3 actual QoQ moves, capped "
        "for modelling (NIM ±40bps; NII ±15%; loans/deposits ±10%). "
        "NIM momentum retention initially set to 50% by explicit choice. "
        "No unreported monthly data, earning-asset yields, rate betas or budgets used."
    )
