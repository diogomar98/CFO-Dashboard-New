"""Real Data CFO Copilot — first live CET1 investigation on the existing gateway.

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
    """Use separate Real-mode state and existing openai_partner gateway."""
    st.markdown("#### Ask the CFO Copilot · CET1")
    st.caption(
        "Real-data AI Gateway call using the existing openai_partner.py connection. "
        "Answers are model-generated; source values and the arithmetic bridge "
        "above are verified locally. Genie is not used for this investigation."
    )
    key="real_cfo_cet1_messages"
    st.session_state.setdefault(key,[])
    history=st.session_state[key]
    controls=st.columns([2.3,1.0],gap="small")
    with controls[0]:
        investigate=st.button(
            "Investigate Q2 2026 CET1 movement",
            key="real_cet1_investigate",
            use_container_width=True,
            type="primary",
        )
    with controls[1]:
        if st.button("Clear conversation",key="real_cet1_clear",use_container_width=True):
            st.session_state[key]=[]
            history=st.session_state[key]
    for item in history[-12:]:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])
            if item.get("role")=="assistant":
                st.caption(
                    "AI-generated interpretation · factsheet-sourced figures · "
                    "not an approved causal assessment"
                )
    question=DEFAULT_QUESTION if investigate else st.chat_input(
        "Ask a standalone question about Group CET1 or RWA…",
        key="real_cet1_chat",
        max_chars=800,
    )
    if not question or not question.strip():
        return
    question=question.strip()
    if len(question)>800:
        st.warning("Keep the CET1 question within 800 characters.")
        return
    history.append({"role":"user","content":question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Investigating sourced Group CET1 figures using the ABN AI Gateway…"):
            try:
                result=answer_reported_cet1(question,evidence)
            except (ValueError,RuntimeError,Exception) as exc:
                # Never print raw HTTP errors or token-bearing request details.
                st.error(
                    "The AI Gateway did not return an answer. Check that the "
                    "existing openai_partner.py connection is configured in the "
                    "ABN environment; no synthetic fallback was used."
                )
                st.caption(f"Failure category: {type(exc).__name__}")
                return
        st.markdown(result["answer"])
        st.caption(
            "Model-generated interpretation; validate all claims with official "
            "disclosures. Source: ABN AMRO Q2 2026 factsheet, Group CET1 and RWA."
        )
        history.append({
            "role":"assistant","content":result["answer"],
            "source":result["source"],
        })


def render_reported_copilot(s):
    render_html(
        '<div class="section-title">CFO Copilot · reported financial investigations</div>'
        '<div class="section-subtitle">'
        'Use the original corporate AI Gateway with verified factsheet context. '
        'CET1 is the first live Real Data investigation; other topics remain '
        'read-only pending source-specific validation.'
        '</div>'
    )
    options=SEGMENT_TOPICS if s.business_line else GROUP_TOPICS
    topic=st.selectbox(
        "Investigation area",list(options),key="real_copilot_evidence_topic"
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
            _render_capital_arithmetic(evidence)
        except ValueError as exc:
            st.error(f"Cannot reconcile CET1: {exc}")
            return
        _live_cet1_thread(evidence)
    else:
        st.info(
            "AI interpretation is enabled only for reported Group CET1 in this "
            "first integration step. You can review source values for this "
            "topic, but no unsupported explanation is generated."
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
            "This is the data the first AI investigation uses. It does not "
            "include the Synthetic cockpit, forecasts, or any Genie SQL results."
        )
    with st.expander("Inspect exact Real Data AI evidence payload"):
        st.code(json.dumps(evidence,ensure_ascii=False,indent=2),language="json")
    st.caption(
        "The gateway request uses src.openai_partner.generate_prompt_response. "
        "The same already-configured ABN token and routing apply; this module "
        "does not modify the connection, Synthetic Copilot, or Genie integration."
    )
