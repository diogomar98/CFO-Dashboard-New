"""Embedded Real Data Copilot balloon, chat turns and verified visual evidence.

A native Streamlit popover stays inside the active report dialog or home.
It never sends chart instructions to the LLM: all diagrams are computed from
the same two published Group capital/RWA reporting quarters.
"""
import inspect

import altair as alt
import pandas as pd
import streamlit as st

from src.hud import render_html
from src.reported_copilot_evidence import build_reported_evidence
from src.reported_copilot_partner import (
    DEFAULT_QUESTION, answer_reported_cet1, build_cet1_bridge,
)


BALLOON_CSS = """
<style>
/* Deliberately scoped: no visual or behavioural change in Synthetic mode. */
/* ABN runs a Streamlit version without keyed containers. The
   balloon is the only native popover in the Real Data view, so style its
   native wrapper directly instead of depending on keyed containers. */
div[data-testid="stPopover"] {
    position:fixed !important;
    bottom:22px !important;
    right:24px !important;
    width:max-content !important;
    max-width:calc(100vw - 30px);
    z-index:1000000 !important;
}
div[data-testid="stPopover"] > button,
div[data-testid="stPopover"] button {
    background:linear-gradient(110deg,#0C2716,#173A25) !important;
    border:1px solid #45C878 !important;
    box-shadow:0 8px 34px rgba(0,0,0,.52),0 0 14px rgba(45,190,96,.17);
    border-radius:100px !important;
    color:#E7FBEA !important;
    font-size:.86rem !important;
    font-weight:750;
    padding:.48rem 1.1rem;
    min-height:42px;
}
div[data-testid="stPopoverBody"]:has(.real-cfo-panel-header) {
    width:min(500px, calc(100vw - 24px)) !important;
    max-height:min(78vh,850px) !important;
    overflow-y:auto !important;
    background:#0C1710 !important;
    color:#D8ECE0 !important;
    border:1px solid rgba(80,184,111,.55);
    border-radius:10px !important;
    box-shadow:0 16px 50px rgba(0,0,0,.65);
}
.real-cfo-panel-header {padding:.1rem 0 .5rem;}
.real-cfo-panel-title {font-size:1.0rem;font-weight:800;color:#D7FFE0;letter-spacing:.025em;}
.real-cfo-panel-sub {font-size:.67rem;color:#A6CAB1;line-height:1.45;}
.real-cfo-visual-head {font-size:.71rem;font-weight:800;color:#B9DDC1;letter-spacing:.03em;}
@media(max-width:650px){
  div[data-testid="stPopover"] {right:12px !important;bottom:12px !important;}
  div[data-testid="stPopoverBody"]:has(.real-cfo-panel-header) {
    width:calc(100vw - 24px) !important; max-height:75vh !important;
  }
}
</style>
"""
HISTORY_KEY = "real_cfo_cet1_messages"
CONTEXT_KEY = "real_cfo_cet1_evidence_context"
MAX_STORED_MESSAGES = 24


def prepare_cet1_investigation(question=None):
    """Queue a source-specific question from a Real Morning Brief KPI card.

    Streamlit >=1.55 supports a keyed popover that can open programmatically.
    Older versions retain the prepared text for the next manual balloon open.
    """
    st.session_state["real_cfo_question_compact"] = (
        question or DEFAULT_QUESTION
    )
    st.session_state["real_cfo_popover_open"] = True


def _popover_options():
    settings = {"use_container_width": False}
    options = inspect.signature(st.popover).parameters
    if "key" in options and "on_change" in options:
        settings.update(key="real_cfo_popover_open", on_change="rerun")
    return settings


def _capital_bridge_chart(bridge):
    """One compact source-derived contribution chart, designed for narrow chat.

    Three bars: capital numerator contribution, RWA denominator contribution,
    and reconciled net CET1 ratio movement. Short horizontal-axis labels
    prevent category text collision in small Streamlit popovers.
    """
    source = pd.DataFrame([
        {"Effect": "Capital", "pp": bridge["capital_component_pp"],
         "description": "CET1 capital numerator, previous-quarter RWA held fixed"},
        {"Effect": "RWA", "pp": bridge["rwa_component_pp"],
         "description": "RWA denominator, latest-quarter CET1 capital held fixed"},
        {"Effect": "Total", "pp": bridge["reported_delta_pp"],
         "description": "Reported quarter-on-quarter CET1 ratio movement"},
    ])
    order = ["Capital", "RWA", "Total"]
    x = alt.X(
        "Effect:N", sort=order, title=None,
        axis=alt.Axis(labelColor="#B7D7C1", labelAngle=0,
                      labelFontSize=11, domain=False, ticks=False),
    )
    y = alt.Y(
        "pp:Q", title="CET1 change (pp)",
        scale=alt.Scale(zero=True, nice=True),
        axis=alt.Axis(labelColor="#A5C2AF", titleColor="#A5C2AF",
                      gridColor="#1B3724", labelFontSize=10),
    )
    color = alt.Color(
        "Effect:N",
        scale=alt.Scale(domain=order, range=["#31C975", "#D4AA69", "#AE8AE9"]),
        legend=None,
    )
    base = alt.Chart(source).encode(
        x=x, y=y, color=color,
        tooltip=[
            alt.Tooltip("Effect:N", title="Effect"),
            alt.Tooltip("pp:Q", format="+.4f", title="Impact in pp"),
            alt.Tooltip("description:N", title="Calculation"),
        ],
    )
    bars = base.mark_bar(size=45, cornerRadiusEnd=3)
    labels = base.mark_text(
        dy=-9, color="#DCEEE1", fontSize=11, fontWeight="bold"
    ).encode(text=alt.Text("pp:Q", format="+.3f"))
    return (bars + labels).properties(height=175).configure_view(
        strokeOpacity=0
    ).configure(background="#0C1710")


def render_cet1_visuals(bridge, compact=True):
    """Always local, exact and source-backed, even if the AI call fails."""
    st.markdown("**CET1 movement · verified financial evidence**")
    a,b,c=st.columns(3)
    a.metric("Q1 ratio",f"{bridge['previous_ratio_pct']:.2f}%")
    b.metric("Q2 ratio",f"{bridge['latest_ratio_pct']:.2f}%")
    c.metric("Movement",f"{bridge['reported_delta_pp']:+.3f}pp")
    # Expand the chart automatically once a real answer is in the thread.
    with st.expander("Visual breakdown · CET1 / capital / RWA",
                     expanded=(not compact or bool(st.session_state.get(HISTORY_KEY)))):
        st.caption(
            "Numerator-first arithmetic, not an explanation of underlying "
            "business causes. Values are from ABN AMRO Q2 2026 factsheet."
        )
        st.markdown("**CET1 ratio movement — capital / RWA / total (pp)**")
        st.altair_chart(_capital_bridge_chart(bridge),use_container_width=True)
        st.caption(
            f"Capital €{bridge['previous_capital_eur_m']:,.1f}m → "
            f"€{bridge['latest_capital_eur_m']:,.1f}m; "
            f"RWA €{bridge['previous_rwa_eur_m']:,.1f}m → "
            f"€{bridge['latest_rwa_eur_m']:,.1f}m. "
            "Source: reported Group capital/RWA, Q1–Q2 2026."
        )


def _get_thread(evidence):
    """One thread across all Real Data pages, reset for different source scope."""
    signature=(evidence["scope"],evidence["as_of"],evidence["source"])
    if st.session_state.get(CONTEXT_KEY)!=signature:
        st.session_state[CONTEXT_KEY]=signature
        st.session_state[HISTORY_KEY]=[]
    return st.session_state[HISTORY_KEY]


def _send(question,evidence,history):
    """Carry bounded verified-evidence chat context into each gateway call."""
    question=question.strip()
    if not question or len(question)>800:
        st.warning("Ask one CET1 question of at most 800 characters.")
        return
    previous=list(history)
    with st.spinner("Investigating the reported figures…"):
        try:
            result=answer_reported_cet1(question,evidence,history=previous)
        except Exception as exc:
            # Avoid leaking authorization headers, URLs, token values or body.
            st.error(
                "The existing ABN AI Gateway could not answer this question. "
                "No synthetic data was substituted."
            )
            st.caption(f"Error class: {type(exc).__name__}")
            return
    history.extend([
        {"role":"user","content":question},
        {"role":"assistant","content":result["answer"],"source":result["source"]},
    ])
    if len(history)>MAX_STORED_MESSAGES:
        del history[:-MAX_STORED_MESSAGES]
    # A rerun restores the entire thread, keeps the native popover open,
    # and expands the deterministic evidence charts beside the latest answer.
    st.rerun()


def render_cet1_chat(evidence, *, compact=True):
    """Full multi-turn interaction reused in balloon and existing Copilot page."""
    bridge=build_cet1_bridge(evidence)
    history=_get_thread(evidence)
    render_cet1_visuals(bridge,compact=compact)
    st.caption(
        "Your follow-up questions keep the previous conversation as context. "
        "Only the cited factsheet and arithmetic are authoritative."
    )
    controls=st.columns([1.9,1],gap="small")
    with controls[0]:
        initial=st.button(
            "Investigate Q2 CET1",key="real_cfo_start_"+("compact" if compact else "full"),
            use_container_width=True,disabled=bool(history),
        )
    with controls[1]:
        clear=st.button(
            "New conversation",key="real_cfo_clear_"+("compact" if compact else "full"),
            use_container_width=True,
        )
    if clear:
        history.clear()

    if history:
        # Height was added before keyed containers, but older ABN runtimes may
        # lack it too. Keep follow-up chat functional without either argument.
        container_args = (
            {"height":260 if compact else 420}
            if "height" in inspect.signature(st.container).parameters else {}
        )
        with st.container(**container_args):
            for message in history[-16:]:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                    if message["role"]=="assistant":
                        st.caption("Model interpretation · source review required")
    else:
        st.info("Start the CET1 investigation or enter your own first question.")
    with st.form("real_cfo_chat_form_"+("compact" if compact else "full"),
                 clear_on_submit=True):
        question=st.text_area(
            "Ask a follow-up",placeholder=(
                "For example: What does the RWA contribution mean? "
                "What evidence is needed to establish the cause?"
            ),max_chars=800,height=72,
            key="real_cfo_question_"+("compact" if compact else "full"),
        )
        asked=st.form_submit_button("Send question",use_container_width=True)
    if initial:
        _send(DEFAULT_QUESTION,evidence,history)
    elif asked and question:
        _send(question,evidence,history)


def render_floating_copilot(s):
    """Show one floating launch balloon in the ACTIVE Real Data report only."""
    if not getattr(s,"is_reported",False):
        return
    render_html(BALLOON_CSS)
    # Use the native Streamlit popover directly. The ABN-deployed version of
    # the local Streamlit version does not support keyed containers.
    # Real-only CSS fixes this native popover in the viewport corner.
    with st.popover("✦ CFO Copilot", **_popover_options()):
        render_html(
            '<div class="real-cfo-panel-header">'
            '<div class="real-cfo-panel-title">CFO Copilot</div>'
            '<div class="real-cfo-panel-sub">'
            'Live Group CET1 investigation · verified figures and follow-ups'
            '</div></div>'
        )
        if s.business_line:
            st.info(
                "Group CET1 investigation only. Select Group reporting "
                "to use the live Copilot. Segment financial questions "
                "are not connected yet."
            )
            return
        try:
            evidence=build_reported_evidence(s,"Capital")
            render_cet1_chat(evidence,compact=True)
        except ValueError:
            st.error("Cannot verify the current CET1 figures; Copilot is unavailable.")
            return
