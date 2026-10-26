"""Real Data What-If: public-model driver scenarios and transparent CFO impacts.

Only sourced Group 2021-on NII/NIM and published ECB rates are used. The
original Synthetic balance-sheet scenario module is never imported or run.
"""
import html

import altair as alt
import pandas as pd
import streamlit as st

from src.hud import module_url, render_html
from src.public_horizon_engine import load_public_horizon_inputs
from src.public_scenario_engine import (
    SCENARIO_METHODS,NEUTRAL_INPUTS,build_public_scenario_comparison
)
from src.reported_horizon import HORIZON_CSS


SCENARIO_CSS = """
<style>
.rs-intro {max-width:1000px;font-size:.78rem;line-height:1.55;color:#ACC9B4;margin:.25rem 0 1rem;}
.rs-note {font-size:.66rem;color:#A6B9AB;line-height:1.5;}
.rs-impact {
  position:relative;min-height:154px;
  border:1px solid rgba(51,148,83,.34);padding:1rem 1.05rem;
  background:linear-gradient(140deg,#15261A,#08120C);
  box-sizing:border-box;
}
.rs-impact::before {content:"";width:30%;height:2px;position:absolute;left:0;top:0;
  background:linear-gradient(90deg,#62D985,transparent);}
.rs-impact-title {color:#91BFA2;font-size:.65rem;letter-spacing:.06em;
  font-weight:800;text-transform:uppercase;}
.rs-impact-value {font-family:"Cascadia Mono",Consolas,monospace;
  font-size:clamp(1.55rem,2.15vw,2.3rem);color:#E6FFEA;
  font-weight:800;margin:.6rem 0 .4rem;letter-spacing:-.03em;white-space:nowrap;}
.rs-impact-desc {color:#BDD7C7;font-size:.70rem;}
.rs-impact-status {font-size:.56rem;color:#DBBD7C;text-transform:uppercase;margin-top:.65rem;}
.rs-legend {display:flex;gap:1.1rem;flex-wrap:wrap;font-size:.65rem;color:#ACCEB5;margin:.4rem 0 1rem;}
.rs-line {display:inline-block;width:22px;height:3px;margin-right:.4rem;vertical-align:middle;}
.rs-actual {background:#36C877;}
.rs-baseline {background:#B794F2;}
.rs-stress {background:#EDB866;}
@media(max-width:980px){
  .rs-impact{min-height:139px;padding:.8rem;}
  .rs-impact-value{font-size:1.4rem;}
}
</style>
"""


def _impact_card(title,value,detail):
    return (
        '<div class="rs-impact">'
        f'<div class="rs-impact-title">{html.escape(title)}</div>'
        f'<div class="rs-impact-value">{html.escape(value)}</div>'
        f'<div class="rs-impact-desc">{html.escape(detail)}</div>'
        '<div class="rs-impact-status">Scenario − matched model baseline</div>'
        '</div>'
    )


def _scenario_controls():
    if "rs_public_options" not in st.session_state:
        st.session_state["rs_public_options"]=dict(NEUTRAL_INPUTS)
    state=st.session_state["rs_public_options"]
    choices=list(SCENARIO_METHODS)
    label=next((k for k,v in SCENARIO_METHODS.items()
                if v==state["method"]),choices[1])
    render_html('<div class="module-code">Scenario assumptions</div>')
    with st.form("rs_public_form"):
        model_label=st.selectbox(
            "Forecast engine",choices,index=choices.index(label),
            help="The same method is applied to the reference and shocked paths."
        )
        shock=st.slider(
            "ECB Deposit Facility Rate shock (bps)",
            min_value=-100,max_value=100,
            value=int(state["rate_shock_bps"]),step=25,
            help="A hypothetical one-time ECB policy rate shift after Q2 2026. "
                 "Rate-sensitive forecasts incorporate it after a reporting-quarter lag.",
        )
        with st.expander("Advanced overrides · impose financial outcomes",expanded=False):
            st.caption("Manual, cumulative assumptions · not inferred from published banking drivers.")
            nim=st.number_input(
                "Additional NIM adjustment per quarter (bps)",
                min_value=-15.0,max_value=15.0,
                value=float(state["nim_overlay_bps"]),step=1.0,format="%.1f",
            )
            nii=st.number_input(
                "Additional NII adjustment per quarter (%)",
                min_value=-7.0,max_value=7.0,
                value=float(state["nii_overlay_pct"]),step=.5,format="%.1f",
            )
        applied=st.form_submit_button("Run scenario",use_container_width=True)
    if applied:
        state={
            "method":SCENARIO_METHODS[model_label],
            "rate_shock_bps":float(shock),
            "nim_overlay_bps":float(nim),
            "nii_overlay_pct":float(nii),
        }
        st.session_state["rs_public_options"]=state
    if st.button("Reset to neutral scenario",key="rs_reset_scenario",use_container_width=True):
        st.session_state["rs_public_options"]=dict(NEUTRAL_INPUTS)
        st.rerun()

    if state["method"]=="no_change":
        st.warning(
            "**Flat financial baseline (ECB-insensitive):** rate changes do not "
            "affect NIM or NII in this benchmark. To test ECB sensitivity, "
            "choose **Rate-sensitive model (ARX)**. Advanced overrides may still "
            "change outputs directly."
        )
    return state


def _scenario_chart(reference,stressed,metric="nim_bps"):
    """Three clean source-aware lines, exactly one common Q2 anchor."""
    if metric not in ("nim_bps","nii_m"):
        raise ValueError("Only audited Group NIM/NII supported.")
    label="NIM (basis points)" if metric=="nim_bps" else "Quarterly NII (€m)"
    fmt=".2f" if metric=="nim_bps" else ",.1f"
    actual=reference[reference["series"]=="Actual"].tail(7).copy()
    base=reference[reference["series"]=="Baseline"].copy()
    shock=stressed[stressed["series"]=="Baseline"].copy()
    if actual.empty or len(base)!=4 or len(shock)!=4:
        raise ValueError("Scenario needs common historical source and four forecast quarters.")
    anchor=actual.tail(1)
    base=pd.concat([anchor,base],ignore_index=True)
    shock=pd.concat([anchor,shock],ignore_index=True)
    sorted_periods=pd.concat([actual,base.iloc[1:]])["quarter"].tolist()
    x=alt.X("quarter:N",sort=sorted_periods,title=None,axis=alt.Axis(
        labelAngle=-28,labelColor="#A2C5AF",labelFontSize=10,
        domainColor="#496A54",tickColor="#496A54",
    ))
    y=alt.Y(f"{metric}:Q",title=label,scale=alt.Scale(zero=False),axis=alt.Axis(
        titleColor="#A4C5AE",labelColor="#A4C5AE",gridColor="#20382A"
    ))
    def layer(data,color,style,dashes=None):
        kw={"color":color,"strokeWidth":3}
        if dashes is not None: kw["strokeDash"]=dashes
        return alt.Chart(data).mark_line(**kw).encode(
            x=x,y=y,tooltip=[
                alt.Tooltip("quarter:N",title="Quarter"),
                alt.Tooltip(f"{metric}:Q",title=style+" "+label,format=fmt),
            ]
        )
    layers=[
        layer(actual,"#37C96E","Reported"),
        layer(base,"#B794F2","Reference",dashes=[7,5]),
        layer(shock,"#EDB866","Scenario"),
    ]
    return alt.layer(*layers).properties(height=300).configure_view(
        strokeOpacity=0
    ).configure(background="#08100C")


def _impact_narrative(options,impacts,quarterly):
    """No invented attribution: distinguish statistical signal and direct overlay."""
    msgs=[]
    n=impacts["selected_models"]
    if options["method"]=="auto":
        def name(value):
            return "rate-sensitive ARX" if value=="rate_arx" else "flat benchmark"
        msgs.append(
            "Automatic method selected: NIM = "+name(n["nim"])
            +"; NII = "+name(n["nii"])+"."
        )
    if float(options["rate_shock_bps"])!=0:
        flat=impacts["flat_for"]
        if flat:
            msgs.append(
                "ECB shocks cannot change the "+", ".join(flat)
                +" projection under its flat benchmark. "
                "Select ARX to test that metric's historical ECB association."
            )
        else:
            msgs.append(
                "The ARX uses lagged policy-rate movements. A new ECB "
                "rate shock first feeds the statistical forecast from "
                "Q4 2026, not immediately in Q3."
            )
    if impacts["overlays_applied"]:
        msgs.append(
            "The advanced NIM and/or NII adjustments directly impose "
            "an additional change each quarter. They do not represent "
            "independently measured loan repricing, funding or credit risks."
        )
    if not (float(options["rate_shock_bps"]) or impacts["overlays_applied"]):
        msgs.append(
            "Neutral assumptions selected: scenario and matched baseline "
            "are identical, so both forecast lines overlap."
        )
    if all(float(quarterly[c].abs().max())<1e-10 for c in (
        "delta_nim_bps","delta_nii_m"
    )):
        msgs.append(
            "No forecast financial impact is estimated under these "
            "specific model assumptions. This is not evidence that real "
            "ECB policy changes would have no economic effect."
        )
    return msgs


def render_reported_scenario(s):
    """Public bank Group What-If, fully isolated from Synthetic what-if."""
    render_html(HORIZON_CSS+SCENARIO_CSS)
    st.markdown('<div class="section-title">What-If Engine</div>',
                unsafe_allow_html=True)
    st.caption("Group NII / NIM · compare an ECB rate scenario with the neutral baseline")
    if s.business_line:
        st.info(
            f"Scope selected: {s.business_line}. This sensitivity analysis is "
            "for ABN AMRO GROUP only, not segment results."
        )
    news_source=st.session_state.get("rs_news_source")
    if news_source:
        current=st.session_state.get("rs_public_options",{})
        if current.get("rate_shock_bps")==float(news_source["rate_shock_bps"]):
            st.info(
                "Official ECB rate update prepared from News Intelligence: "
                f"{news_source['rate_shock_bps']:+d} bps effective "
                f"{news_source['rate_effective_date']}. This is an observed "
                "policy-rate move since the Q2 2026 model cutoff, not a "
                "modelled financial effect. Review or change the assumptions "
                "below before using the results."
            )
            st.caption(
                "Official source: "+news_source["official_data_url"]
            )
        else:
            st.session_state.pop("rs_news_source",None)
    try:
        public=load_public_horizon_inputs(s.reported_group)
    except (ValueError,FileNotFoundError,KeyError) as exc:
        st.error("Source check failed: "+str(exc))
        return
    control,result=st.columns([.88,1.56],gap="large")
    with control:
        inputs=_scenario_controls()
    try:
        baseline,scenario,quarters,impacts=build_public_scenario_comparison(
            public,inputs
        )
    except (ValueError,OverflowError,ArithmeticError) as exc:
        with result: st.error("Scenario calculation failed: "+str(exc))
        return
    with result:
        render_html(
            '<div class="module-code">Paired scenario / same model</div>'
            '<div class="section-title">What changes?</div>'
        )
        rows=[
            ("Q4 2026 · NIM impact",
             f"{impacts['q4_nim_bps']:+,.2f} bps",
             f"Baseline {quarters.iloc[1]['base_nim_bps']:.2f} → "
             f"scenario {quarters.iloc[1]['scenario_nim_bps']:.2f} bps"),
            ("Q4 2026 · NII impact",
             f"€{impacts['q4_nii_m']:+,.1f}m",
             f"Baseline €{quarters.iloc[1]['base_nii_m']:,.0f}m → "
             f"scenario €{quarters.iloc[1]['scenario_nii_m']:,.0f}m"),
            ("FY2026 · NII impact",
             f"€{impacts['fy_nii_delta_m']:+,.1f}m",
             f"Base €{impacts['fy_nii_baseline_m']/1000:.3f}bn → "
             f"scenario €{impacts['fy_nii_scenario_m']/1000:.3f}bn"),
        ]
        for col,(name,val,description) in zip(st.columns(3),rows):
            with col:
                render_html(_impact_card(name,val,description))
        st.write("")
        selection=st.radio(
            "Compare forecast impacts",
            ["NIM (bps)","NII (€m)"],horizontal=True,
            key="rs_metric",
        )
        target="nim_bps" if selection=="NIM (bps)" else "nii_m"
        render_html(
            '<div class="rs-legend">'
            '<span><i class="rs-line rs-actual"></i>Reported</span>'
            '<span><i class="rs-line rs-baseline"></i>Neutral reference</span>'
            '<span><i class="rs-line rs-stress"></i>Selected scenario</span>'
            '</div>'
        )
        st.altair_chart(_scenario_chart(baseline,scenario,metric=target),
                        use_container_width=True)

    st.markdown("#### Financial impact · period by period")
    pretty=quarters.copy()
    pretty["NIM baseline (bps)"]=pretty["base_nim_bps"].round(2)
    pretty["NIM scenario (bps)"]=pretty["scenario_nim_bps"].round(2)
    pretty["Δ NIM (bps)"]=pretty["delta_nim_bps"].round(2)
    pretty["NII baseline (€m)"]=pretty["base_nii_m"].round(1)
    pretty["NII scenario (€m)"]=pretty["scenario_nii_m"].round(1)
    pretty["Δ NII (€m)"]=pretty["delta_nii_m"].round(1)
    st.dataframe(
        pretty[["quarter","NIM baseline (bps)","NIM scenario (bps)",
                "Δ NIM (bps)","NII baseline (€m)","NII scenario (€m)",
                "Δ NII (€m)"]],
        hide_index=True,use_container_width=True,
    )
    st.markdown("#### How to interpret this test")
    for message in _impact_narrative(inputs,impacts,quarters):
        st.write("• "+message)
    with st.expander("Scenario methodology & limitations",expanded=False):
        st.caption(
            "FY2026 combines reported Q1/Q2 NII with modelled Q3/Q4. "
            "Rate shocks are hypothetical and do not estimate bank-specific "
            "deposit betas. CET1, credit losses and liquidity are not modelled."
        )
    render_html(
        '<div class="module-action-row">'
        f'<a class="module-action-link" href="{module_url("horizon")}" target="_self">'
        'Return to Horizon baseline →</a>'

        '</div>'
    )
