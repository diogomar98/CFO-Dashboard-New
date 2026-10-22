"""Real Data CFO Copilot — open-ended sourced financial chat on existing gateway.

Synthetic Copilot, its AI Gateway client implementation and Databricks Genie
remain completely unchanged. Every request carries a fresh, bounded packet
of published Group values and a locally reconciled CET1 arithmetic bridge.
"""
import json

import streamlit as st

from src.hud import render_html
from src.reported_copilot_evidence import (
    GROUP_TOPICS, SEGMENT_TOPICS, build_reported_evidence,
)
from src.reported_copilot_partner import (
    DEFAULT_QUESTION, build_cet1_bridge, answer_reported_cet1,
)


def _print_value(item):
    value = item["latest"]
    if value is None:
        return "Unavailable"
    if item["unit"] == "EUR millions":
        return f"€{value:,.0f}m"
    if item["unit"] == "percent":
        return f"{value:.2f}%"
    return f"{value:.2f} bps"


def _print_change(item):
    value = item["delta"]
    if value is None:
        return "Prior period unavailable"
    unit = item["unit"]
    if unit == "percent":
        return f"{value:+.2f}pp QoQ"
    if unit == "EUR millions":
        return f"{value:+,.1f}m QoQ"
    return f"{value:+.2f} bps QoQ"


def _render_capital_arithmetic(evidence):
    """Deterministic figures shown separately from any language-model text."""
    bridge = build_cet1_bridge(evidence)
    st.markdown("#### Verified Group CET1 arithmetic")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Ratio movement", f"{bridge['reported_delta_pp']:+.3f} pp")
    with col2:
        st.metric("Capital numerator contribution", f"{bridge['capital_component_pp']:+.3f} pp")
    with col3:
        st.metric("RWA denominator contribution", f"{bridge['rwa_component_pp']:+.3f} pp")
    st.caption(
        "Numerator-first arithmetic bridge: CET1 capital / RWA × 100. "
        "The two contributions sum to the reported ratio change. "
        "They do NOT establish why capital or RWA moved."
    )
    with st.expander("Review exact bridge and source values"):
        st.json(bridge)
    return bridge


def _live_cet1_thread(evidence):
    """The standalone route uses the exact same multi-turn thread as the balloon."""
    from src.reported_copilot_balloon import render_cet1_chat
    render_cet1_chat(evidence, compact=False)


def render_reported_copilot(s):
    render_html(
        '<div class="section-title">CFO Copilot · reported financial investigations</div>'
        '<div class="section-subtitle">'
        'Use the original corporate AI Gateway with verified factsheet context. '
        'Ask freely across sourced Group and segment financial figures. '
        'For unsupported topics, Copilot explains what evidence is missing.'
        '</div>'
    )
    options=SEGMENT_TOPICS if s.business_line else GROUP_TOPICS
    topic_names=["All reported metrics"]+[x for x in options if x!="All reported metrics"]
    topic=st.selectbox(
        "Investigation area",topic_names,key="real_copilot_evidence_topic"
    )
    try:
        evidence=build_reported_evidence(s,topic)
    except ValueError as exc:
        st.error(f"Reported source check failed: {exc}")
        return
    st.caption(
        f"{evidence['scope']} · {evidence['as_of']} · "
        "published quarterly financial figures"
    )
    for col,metric in zip(st.columns(3),evidence["metrics"][:3]):
        with col:
            st.metric(metric["label"],_print_value(metric),_print_change(metric))

    live = bool(evidence["llm_enabled"])
    if live:
        try:
            _live_cet1_thread(evidence)
        except ValueError as exc:
            st.error(f"Cannot reconcile CET1: {exc}")
            return
    else:
        st.info(
            "The selected scope does not have approved AI evidence; "
            "the published values remain available for review."
        )

    with st.expander("Inspect the complete reported evidence and source references"):
        st.dataframe([
            {
                "Metric":m["label"],
                "Reported quarter":m["latest_quarter"],
                "Reported value":_print_value(m),
                "Quarterly movement":_print_change(m),
                "Source":m["provenance"],
            }
            for m in evidence["metrics"]
        ],use_container_width=True,hide_index=True)
        st.caption(
            "These figures are from the official reporting extract. "
            "No Synthetic values, unrestricted SQL or Genie data are included."
        )
    with st.expander("Inspect exact Real Data AI evidence payload"):
        st.code(json.dumps(evidence,ensure_ascii=False,indent=2),language="json")
    st.caption(
        "The gateway request uses src.openai_partner.generate_prompt_response. "
        "The same already-configured ABN token and routing apply; this module "
        "does not modify the connection, Synthetic Copilot, or Genie integration."
    )
