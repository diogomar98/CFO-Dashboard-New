"""Real Data Copilot phase 1: auditable evidence, no external AI requests.

The Synthetic Copilot and its chat threads are unmodified. Until an
organization-approved authenticated AI gateway is configured, this view only
lets reviewers inspect exactly which public/loaded Group facts a future
assistant would be given.
"""
import json

import streamlit as st

from src.hud import render_html
from src.reported_copilot_evidence import (
    GROUP_TOPICS, SEGMENT_TOPICS, build_reported_evidence,
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


def render_reported_copilot(s):
    render_html(
        '<div class="section-title">CFO Copilot · source-grounded investigations</div>'
        '<div class="section-subtitle">'
        'Phase 1 establishes auditable reported-data context. '
        'No external model call, Genie query or AI-generated conclusion is enabled yet.'
        '</div>'
    )
    st.info(
        "AI connection pending approval. This is an evidence inspection view, "
        "not a live financial chatbot. Financial inputs are not sent to any AI service."
    )
    options = SEGMENT_TOPICS if s.business_line else GROUP_TOPICS
    topic = st.selectbox(
        "Choose the first investigation context",
        list(options),
        key="real_copilot_evidence_topic",
    )
    try:
        packet = build_reported_evidence(s, topic)
    except ValueError as exc:
        st.error(f"Cannot prepare evidence: {exc}")
        return
    st.caption(
        f"{packet['scope']} · {packet['as_of']} · "
        "published quarterly actuals only"
    )
    top = packet["metrics"][:3]
    for col, metric in zip(st.columns(len(top)), top):
        with col:
            st.metric(metric["label"], _print_value(metric), _print_change(metric))
    with st.expander("Inspect every source value and comparison", expanded=False):
        st.dataframe(
            [
                {
                    "Metric": m["label"],
                    "Period": m["latest_quarter"],
                    "Reported value": _print_value(m),
                    "QoQ movement": _print_change(m),
                    "Source": m["provenance"],
                }
                for m in packet["metrics"]
            ],
            use_container_width=True, hide_index=True,
        )
    with st.expander("Inspect the exact context contract for future AI calls"):
        st.code(json.dumps(packet, ensure_ascii=False, indent=2), language="json")
    st.markdown("#### What the future assistant will be allowed to do")
    st.write(
        "Explain these figures, calculate supported changes, and reference "
        "approved period-specific public documents. Where the source doesn't "
        "support a causal explanation, it must say what's missing."
    )
    st.caption(
        "Next integration stage: securely authenticate to an approved "
        "corporate AI gateway, validate responses against this evidence "
        "packet, and display citations. The existing Synthetic Copilot "
        "is completely separate."
    )
