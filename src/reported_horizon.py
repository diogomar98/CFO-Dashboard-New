"""CFO Horizon — 2021-on PUBLIC-ONLY Group actuals and backtested forecasts.

The existing Synthetic module, synthetic engines, reporting dashboard and
source financial CSV are deliberately untouched. Assumption-based 90/95
prediction intervals are statistical illustrations, not certified coverage.
"""
import html

import altair as alt
import pandas as pd
import streamlit as st

from src.hud import module_url, render_html
from src.public_horizon_engine import (
    load_public_horizon_inputs, build_public_horizon, CRITICAL_VALUES,
)

HORIZON_CSS = """
<style>
.rh-description {font-size:.79rem;color:#A2B9AA;line-height:1.5;max-width:1100px;margin:.25rem 0 .85rem;}
.rh-pill {display:inline-flex;margin:.55rem 0 .5rem;padding:.25rem .5rem;border:1px solid rgba(211,176,97,.42);
 color:#E8CF92;background:rgba(143,117,55,.09);font-size:.64rem;font-weight:700;letter-spacing:.045em;}
/* Match the Synthetic Horizon card hierarchy while retaining the same
   explicitly labelled illustrative-vs-actual status. Scoped to Real mode. */
.rh-metric {
 position:relative;min-height:169px;padding:1.15rem 1.15rem .95rem;
 background:linear-gradient(145deg,rgba(17,24,19,.96),rgba(9,13,10,.93)),
            radial-gradient(circle at 100% 0%,rgba(19,172,51,.13),transparent 45%);
 border:1px solid rgba(19,172,51,.29);box-sizing:border-box;
 box-shadow:inset 0 0 24px rgba(19,150,50,.035);
}
.rh-metric::before {
 content:"";position:absolute;top:0;left:0;width:38%;height:2px;
 background:linear-gradient(90deg,#38CF72,transparent);
 box-shadow:0 0 12px rgba(19,172,51,.38);
}
.rh-metric-name {font-size:.69rem;letter-spacing:.055em;font-weight:800;color:#91BF9D;text-transform:uppercase;line-height:1.4;}
.rh-metric-value {
 margin:.48rem 0 .4rem;font-size:clamp(1.66rem,2.38vw,2.40rem);
 line-height:1.07;letter-spacing:-.055em;
 font-weight:800;color:#E7FFE9;font-family:"Cascadia Mono","Segoe UI",monospace;
 white-space:nowrap;text-shadow:0 0 22px rgba(38,188,85,.20);
}
.rh-metric-detail {font-size:.71rem;color:#BDD7C3;line-height:1.42;font-weight:600;}
.rh-metric-foot {margin-top:.58rem;font-size:.60rem;letter-spacing:.06em;color:#DCC286;font-weight:750;text-transform:uppercase;}
.rh-model-label {font-family:"Cascadia Mono",Consolas,monospace;font-size:.65rem;color:#87B49A;letter-spacing:.06em;}
.rh-note {font-size:.72rem;color:#9CBAA6;line-height:1.55;}
.rh-legend {display:flex;align-items:center;gap:1.2rem;flex-wrap:wrap;margin:.35rem 0 1rem;}
.rh-legend span {display:inline-flex;align-items:center;gap:.4rem;font-size:.63rem;color:#A3C4AE;}
.rh-key {display:inline-block;width:21px;height:3px;background:#32C867;}
.rh-key.is-projected {background:#BC96F3;border-top:1px dashed #BC96F3;}
@media(max-width:1150px){
  .rh-metric {min-height:162px;padding:.9rem .85rem;}
  .rh-metric-value {font-size:clamp(1.5rem,2.15vw,2.02rem);}
}
@media(max-width:700px){
  .rh-metric {min-height:140px;}
  .rh-metric-value {font-size:clamp(1.42rem,4vw,1.85rem);}
}
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



def _forecast_chart(history, metric="nim_pct", history_points=12, bands="Both"):
    """Synthetic-style green actuals, dashed purple forecast, 90/95 shaded bands."""
    if metric not in ("nim_pct", "nii_m"):
        raise ValueError("This public forecast supports only cross-checked Group NIM/NII.")
    field_label = "NIM (%)" if metric == "nim_pct" else "Net interest income (€m)"
    fmt = ".3f" if metric == "nim_pct" else ",.1f"
    actual = history[history["series"]=="Actual"].tail(history_points).copy()
    projected = history[history["series"]=="Baseline"].copy()
    if actual.empty or projected.empty:
        raise ValueError("Historical and forward periods are both required.")
    bridge = actual.tail(1).copy()
    bridge["series"] = "Baseline"
    baseline = pd.concat([bridge, projected], ignore_index=True)
    order = pd.concat([actual, projected])["quarter"].tolist()
    band_values = [actual[metric], projected[metric]]
    for level in (90, 95):
        if bands == "Both" or bands == str(level)+"%":
            band_values.extend([
                projected[f"{metric}_low_{level}"],
                projected[f"{metric}_high_{level}"],
            ])
    stacked = pd.concat(band_values).dropna()
    lo,hi = float(stacked.min()),float(stacked.max())
    pad=max((hi-lo)*0.08,0.03 if metric=="nim_pct" else max(hi*0.01,1))
    scale = alt.Scale(domain=[lo-pad,hi+pad])
    x=alt.X("quarter:N",sort=order,title=None,axis=alt.Axis(
        labelColor="#9BBCA5",labelAngle=-35,labelFontSize=10,domainColor="#43684E",
        tickColor="#43684E",
    ))
    y=alt.Y(f"{metric}:Q",title=field_label,scale=scale,axis=alt.Axis(
        labelColor="#A7C5B0",titleColor="#A7C5B0",gridColor="#203A28",
        labelFontSize=10,
    ))
    band_layers=[]
    for level,opacity in ((95,0.10),(90,0.22)):
        if bands!="Both" and bands!=str(level)+"%":
            continue
        low=f"{metric}_low_{level}"
        high=f"{metric}_high_{level}"
        area=alt.Chart(projected).mark_area(
            color="#AD89EF",opacity=opacity
        ).encode(x=x,y=alt.Y(f"{low}:Q",title=field_label,scale=scale,axis=alt.Axis(
            labelColor="#A7C5B0",titleColor="#A7C5B0",gridColor="#203A28",
        )),y2=f"{high}:Q",
        tooltip=[
            alt.Tooltip("quarter:N",title="Forecast quarter"),
            alt.Tooltip(f"{low}:Q",title=f"{level}% lower",format=fmt),
            alt.Tooltip(f"{high}:Q",title=f"{level}% upper",format=fmt),
        ])
        band_layers.append(area)

    actual_tooltips=[
        alt.Tooltip("quarter:N",title="Reported quarter"),
        alt.Tooltip(f"{metric}:Q",title=f"Reported {field_label}",format=fmt),
        alt.Tooltip("source:N",title="Source"),
    ]
    future_tooltips=[
        alt.Tooltip("quarter:N",title="Forecast quarter"),
        alt.Tooltip(f"{metric}:Q",title=f"Model baseline {field_label}",format=fmt),
        alt.Tooltip("source:N",title="Model status"),
    ]
    line1=alt.Chart(actual).mark_line(color="#32C867",strokeWidth=3).encode(
        x=x,y=y,tooltip=actual_tooltips
    )
    dots1=alt.Chart(actual).mark_circle(color="#32C867",size=62,stroke="#0A100C",
                                            strokeWidth=1.2).encode(x=x,y=y,tooltip=actual_tooltips)
    line2=alt.Chart(baseline).mark_line(color="#BC96F3",strokeWidth=3,strokeDash=[7,5]).encode(
        x=x,y=y,tooltip=future_tooltips
    )
    dots2=alt.Chart(projected).mark_point(
        filled=True,color="#110C17",stroke="#CFB9FF",strokeWidth=2,size=72
    ).encode(x=x,y=y,tooltip=future_tooltips)
    # Use a FLAT layer list: this avoids nested Vega-Lite layers and makes
    # both 90/95 confidence bands independently inspectable.
    chart=alt.layer(*(band_layers+[line1,dots1,line2,dots2]))
    return chart.properties(height=350).configure_view(
        strokeOpacity=0
    ).configure(background="#08100C")


def _lens(path,summary):
    """Preserve the Synthetic forward-lens layout with accountable methodology."""
    diag=summary["diagnostics"]
    nim=diag["nim_bps"];nii=diag["nii_m"]
    method_labels={"no_change":"Flat financial baseline (ECB-insensitive)",
                   "rate_arx":"Rate-sensitive ARX (ridge regularised)"}
    start=path[path["series"]=="Baseline"].iloc[0]["quarter"]
    final=path[path["series"]=="Baseline"].iloc[-1]["quarter"]
    full_year=summary["fy_nii_m"]
    fy_text=(
        f"FY{path.iloc[-1]['date'].year-1} NII baseline "
        f"<strong>€{full_year/1000:,.2f}bn</strong> "
        f"(€{summary['fy_nii_actual_m']/1000:,.2f}bn reported "
        f"+ €{summary['fy_nii_projected_m']/1000:,.2f}bn estimated)."
        if pd.notna(full_year) else
        "Full-year NII cannot be calculated from the available reported periods."
    )
    return f"""
    <div class="forward-lens-panel">
      <div class="forward-lens-kicker">Forward lens · public-data model</div>
      <div class="forward-lens-title">What is the baseline telling us?</div>
      <div class="forward-lens-row">
        <span class="forward-lens-label">Historical evidence</span>
        <span class="forward-lens-value"><strong>22 quarters</strong> of independently
        reconciled Group NII and NIM from public ABN AMRO factsheets (2021 Q1 to 2026 Q2),
        plus ECB deposit-rate history.</span>
      </div>
      <div class="forward-lens-row">
        <span class="forward-lens-label">NIM model</span>
        <span class="forward-lens-value"><strong>{method_labels[nim['model']]}</strong>.
        The lagged previous-quarter NIM and prior ECB DFR movement are candidate drivers.
        One-quarter historical mean absolute error:
        <strong>{nim['selected_1q_mae']:.1f} bps</strong>
        ({nim['backtest_1q_count']} historical origins).</span>
      </div>
      <div class="forward-lens-row">
        <span class="forward-lens-label">Income model</span>
        <span class="forward-lens-value"><strong>{method_labels[nii['model']]}</strong>.
        Fitted on log of published quarterly statutory NII;
        selected one-quarter log error <strong>{nii['selected_1q_mae']:.3f}</strong>.
        NII and NIM are not mechanically tied without matching average
        interest-earning assets.</span>
      </div>
      <div class="forward-lens-row">
        <span class="forward-lens-label">Rates context</span>
        <span class="forward-lens-value">Last published ECB DFR:
        <strong>{summary['last_ecb_qend_pct']:.2f}%</strong>.
        The neutral forecast holds it flat from the Q2 2026 close.
        This is a modelling convention, <strong>not</strong> an ECB forecast
        or market-implied forward path.</span>
      </div>
      <div class="forward-lens-row">
        <span class="forward-lens-label">Year-end lens</span>
        <span class="forward-lens-value">{fy_text}
        Projections cover <strong>{html.escape(start)}</strong> to
        <strong>{html.escape(final)}</strong>.</span>
      </div>
      <div class="forward-lens-row">
        <span class="forward-lens-label">Prediction bands</span>
        <span class="forward-lens-value"><strong>90% and 95%</strong> model-based
        Gaussian ranges derived from out-of-sample rolling forecast RMSE, separately
        at horizons 1–4 quarters. With only 22 quarters, these are
        <strong>not independently calibrated coverage guarantees</strong>.
        Macroeconomic regime changes and acquisition effects are not fully captured.</span>
      </div>
      <div class="forward-lens-meaning">
        <strong>Interpretation</strong>
        A transparent, public-data reference case, not ABN's official earnings guidance.
        Full-year commercial NII guidance, acquisition adjustments and internal
        repricing parameters cannot be reconciled to this statutory NII model.
        No calibrated statistical confidence guarantee is available from
        the limited source package; official plan details are not contained in the source package.
      </div>
    </div>"""


def _validation_details(history,summary,frame):
    with st.expander("Forecast validation, sourced figures and four-eyes audit",expanded=False):
        st.markdown("**Reporting provenance**")
        st.caption(
            "Group NII and NIM: 22 ABN public quarterly factsheets. "
            "49 of 49 independent source comparisons passed for these two series. "
            "ECB rates: official rate-change CSV transformed to quarterly calendar-day averages. "
            "Other Group measures (loans, deposits, capital) are not extrapolated."
        )
        st.dataframe(
            frame[["date","nii_m","nim_bps","dfr_qavg_pct","dfr_qend_pct",
                   "source_url_bank","nii_cell","nim_cell","source_url_ecb"]].iloc[::-1],
            hide_index=True,use_container_width=True,
        )
        st.markdown("**Rolling-origin prediction diagnostics**")
        table=[]
        for name,field in (("NIM (bps)","nim_bps"),("NII (log level)","nii_m")):
            diagnostics=summary["diagnostics"][field]
            for h in diagnostics["horizons"]:
                table.append({
                    "Metric":name,"Horizon (quarters)":h["horizon"],
                    "Method":diagnostics["model"],
                    "Backtest origins":h["backtest_count"],
                    "MAE":round(h["mae"],4),
                    "RMSE":round(h["rmse"],4),
                    "90% in-sample-tested hit":round(h["central90_hit_pct"],1),
                    "95% in-sample-tested hit":round(h["central95_hit_pct"],1),
                })
        st.dataframe(pd.DataFrame(table),hide_index=True,use_container_width=True)
        st.caption(
            "Hit rates are diagnostic only: model selection and interval scaling "
            "use the same limited historical test origins. These are not independent "
            "proof of predictive coverage. Log NII errors are dimensionless."
        )
        st.markdown(
            "Sources and independent review: "
            "[ABN NII/NIM source cross-check](https://github.com/diogomar98/CFO-Dashboard-New/blob/"
            "feature/cfo-dual-data-mode-foundation/research/2021_NII_NIM_4EYES_RESULTS.md) · "
            "[ECB official API](https://data-api.ecb.europa.eu/service/data/"
            "FM/B.U2.EUR.4F.KR.DFR.LEV?startPeriod=2019-01-01&endPeriod=2026-06-30&format=csvdata)"
        )


def render_reported_horizon(s):
    """Real Data only; never call Synthetic's historical/forecast generators."""
    render_html(HORIZON_CSS)
    if s.business_line:
        st.info(
            f"Selected business line: {s.business_line}. The published "
            "2021-on NII/NIM forecast is GROUP-wide, not this segment."
        )
    st.markdown('<div class="section-title">Where are we heading?</div>',
                unsafe_allow_html=True)
    render_html(
        '<div class="rh-description">Publicly sourced ABN AMRO Group NII/NIM trends '
        'since 2021, combined with ECB policy-rate history and a small backtested '
        'forecast. Forecasts and prediction bands are estimates, not reported actuals '
        'or official management guidance.</div>'
    )
    render_html('<div class="rh-pill">22 verified Group quarters · neutral baseline · modelled 90% / 95% ranges</div>')
    try:
        public=load_public_horizon_inputs(s.reported_group)
    except (FileNotFoundError,ValueError,KeyError) as exc:
        st.error("Source check failed: " + str(exc))
        st.caption("Do not substitute the Synthetic financial datasets.")
        return
    # Horizon always displays the automatically selected, unshocked public
    # baseline. ECB shocks and direct financial overlays belong in What-If.
    try:
        trajectory,model=build_public_horizon(public,model_preference="auto")
    except (ValueError,OverflowError,ArithmeticError) as exc:
        st.error("Unable to calculate a source-grounded forecast: " + str(exc))
        return
    cards=[
        (f"{model['year_end_quarter']} NIM baseline",
         f"{model['year_end_nim_pct']:.2f}%",
         f"{model['year_end_nim_change_bps']:+.1f} bps vs {model['last_quarter']}"),
        (f"FY{public.iloc[-1]['date'].year} NII baseline",
         f"€{model['fy_nii_m']/1000:.2f}bn",
         f"€{model['fy_nii_actual_m']/1000:.2f}bn actual + "
         f"€{model['fy_nii_projected_m']/1000:.2f}bn projected"),
        ("Next-quarter NIM step",
         f"{model['first_nim_change_bps']:+.1f} bps",
         f"Modelled vs reported {model['last_quarter']}"),
        ("ECB DFR · Q2 actual",
         f"{model['last_ecb_qend_pct']:.2f}%",
         "Neutral forward-rate assumption: unchanged"),
    ]
    for col,(label,value,detail) in zip(st.columns(4),cards):
        with col:
            render_html(_card(label,value,detail))
    st.caption(
        "This view shows the neutral, automatically selected forecast. "
        "For rate shocks or manual NIM/NII overlays, use the Real Data What-If Engine."
    )
    st.write("")
    chart_col,lens_col=st.columns([1.72,.90],gap="large")
    with chart_col:
        render_html(
            '<div class="module-code">Forward trajectory / actual → baseline</div>'
            '<div class="section-title">Quarterly outlook</div>'
        )
        c1,c2,c3=st.columns([1.35,1.25,1.10],gap="small")
        with c1:
            selection=st.selectbox(
                "Metric",["Net interest margin","Net interest income"],
                key="rh_public_metric",
            )
        with c2:
            view=st.selectbox("Prediction bands",["Both","90%","95%","Off"],
                              key="rh_public_bands")
        with c3:
            scope=st.selectbox("Reported history",["Latest 12 quarters","All 22 quarters"],
                               key="rh_public_history")
        metric=("nim_pct" if selection=="Net interest margin" else "nii_m")
        render_html(
            '<div class="rh-legend">'
            '<span><i class="rh-key"></i>Published actuals</span>'
            '<span><i class="rh-key is-projected"></i>Baseline estimate</span>'
            '<span style="color:#BFA6F0">Shaded = model-based prediction ranges</span>'
            '</div>'
        )
        st.altair_chart(
            _forecast_chart(trajectory,metric=metric,
                            history_points=12 if scope=="Latest 12 quarters" else 22,
                            bands=view),
            use_container_width=True,
        )
        st.caption(
            "Green = audited public Group NII/NIM actuals. Dashed purple = "
            "forecast. 90% / 95% bands reflect assumed Gaussian errors scaled "
            "from limited rolling tests, not bank-approved statistical confidence. "
            "Horizon holds the ECB policy rate flat; rate scenarios belong in What-If."
        )
    with lens_col:
        render_html(_lens(trajectory,model))
    _validation_details(trajectory,model,public)
    render_html(
        '<div class="module-action-row">'
        f'<a class="module-action-link" href="{module_url("scenario")}" target="_self">'
        'Test ECB rates & management overlays in What-If →</a>'
        '<span class="rh-model-label">Public-model forecast · Real Data mode only</span>'
        '</div>'
    )
    st.caption(
        "Group forecast research cutoff: Q2 2026. "
        "Financial actuals: official ABN factsheets Q1 2021–Q2 2026. "
        "ECB DFR: official rate-change series, averaged by calendar day. "
        "Separate source checks passed; 90%/95% ranges have NOT been "
        "demonstrated to deliver those frequencies out of sample."
    )
