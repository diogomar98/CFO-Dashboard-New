"""Jarvis: separate Real Data floating chat; central Ask CFO Copilot unchanged.

Uses native older-Streamlit-compatible widgets and scoped fixed-position CSS,
with a distinct scrolling message body and an ordinary composer footer.
All CET1 evidence charts are derived locally from verified quarterly actuals.
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
/* Jarvis is a SEPARATE Real Data assistant. The radial CFO Copilot is intact.
   Target only the innermost Streamlit block containing the Jarvis marker.
   This does not require keyed Streamlit containers, unavailable at ABN. */
div[data-testid="stVerticalBlock"]:has(.jarvis-root-marker):not(
  :has(div[data-testid="stVerticalBlock"] .jarvis-root-marker)
) {
    position:fixed !important;
    bottom:20px !important;
    right:24px !important;
    z-index:1000000 !important;
    width:min(470px,calc(100vw - 24px)) !important;
    max-width:min(470px,calc(100vw - 24px)) !important;
    background:linear-gradient(160deg,#102118,#07120C) !important;
    border:1px solid rgba(72,187,111,.63) !important;
    border-radius:14px !important;
    padding:14px !important;
    box-shadow:0 20px 55px rgba(0,0,0,.74),0 0 18px rgba(41,167,88,.12);
    box-sizing:border-box !important;
}
div[data-testid="stVerticalBlock"]:has(.jarvis-root-marker):not(
  :has(div[data-testid="stVerticalBlock"] .jarvis-root-marker)
):has(.jarvis-open-marker) {
    height:min(700px,calc(100dvh - 42px)) !important;
    max-height:calc(100dvh - 42px) !important;
    overflow:hidden !important;
    display:flex !important;
    flex-direction:column !important;
    gap:7px !important;
}
div[data-testid="stVerticalBlock"]:has(.jarvis-root-marker):not(
  :has(div[data-testid="stVerticalBlock"] .jarvis-root-marker)
):has(.jarvis-closed-marker) {
    width:max-content !important;
    min-width:116px;
    height:auto !important;
    border-radius:38px !important;
    padding:4px !important;
    background:transparent !important;
    border:0 !important;
    box-shadow:none !important;
}
div[data-testid="stVerticalBlock"]:has(.jarvis-closed-marker):not(
  :has(div[data-testid="stVerticalBlock"] .jarvis-closed-marker)
) button {
    border-radius:40px !important;
    background:linear-gradient(115deg,#14502D,#0B2518) !important;
    color:#E5FFEA !important;
    border:1px solid #4DDD86 !important;
    font-size:.84rem !important;
    font-weight:800 !important;
    box-shadow:0 9px 34px rgba(0,0,0,.62),0 0 15px rgba(26,172,79,.23);
    min-height:49px !important;
    padding:0 17px !important;
}
/* Streamlit builds differ in whether a container introduces a border
   wrapper. Constrain either wrapper so it cannot push the composer offscreen. */
div[data-testid="stVerticalBlockBorderWrapper"]:has(.jarvis-history-marker):not(
  :has(div[data-testid="stVerticalBlockBorderWrapper"] .jarvis-history-marker)
) {
    max-height:calc(min(700px,100dvh - 42px) - 300px) !important;
    min-height:0 !important;
    overflow-y:auto !important;
    flex:1 1 auto !important;
}
.jarvis-root-marker,.jarvis-open-marker,.jarvis-closed-marker,
.jarvis-history-marker {display:none;}
.jarvis-heading {font-weight:850;font-size:1.05rem;color:#E3FFEA;}
.jarvis-subtitle {font-size:.67rem;color:#A9CCB2;margin-top:.1rem;}
div[data-testid="stVerticalBlock"]:has(.jarvis-history-marker):not(
  :has(div[data-testid="stVerticalBlock"] .jarvis-history-marker)
) {
    overflow-y:auto !important;
    overscroll-behavior:contain;
    min-height:150px !important;
    max-height:calc(min(700px,100dvh - 42px) - 300px) !important;
    padding:8px !important;
    background:rgba(2,10,6,.65) !important;
    border:1px solid rgba(76,145,92,.29) !important;
    border-radius:8px !important;
}
div[data-testid="stVerticalBlock"]:has(.jarvis-history-marker):not(
  :has(div[data-testid="stVerticalBlock"] .jarvis-history-marker)
) [data-testid="stChatMessage"] {
    padding:.75rem !important;
    margin-bottom:.5rem !important;
    border:1px solid rgba(74,118,82,.2);
    border-radius:8px;
}
div[data-testid="stVerticalBlock"]:has(.jarvis-root-marker):not(
  :has(div[data-testid="stVerticalBlock"] .jarvis-root-marker)
) textarea {
    min-height:66px !important;
    background:#101C19 !important;
}
div[data-testid="stVerticalBlock"]:has(.jarvis-root-marker):not(
  :has(div[data-testid="stVerticalBlock"] .jarvis-root-marker)
) [data-testid="stForm"] {
    background:rgba(11,32,20,.96);
    padding:.45rem .55rem !important;
    border-top:1px solid rgba(86,159,109,.35);
    border-radius:7px;
}
/* Streamlit dialogs can create an opaque backdrop; Jarvis lives inside
   the active Real Data dialog and is therefore interactive above it. */
@media (max-width:650px) {
  div[data-testid="stVerticalBlock"]:has(.jarvis-root-marker):not(
    :has(div[data-testid="stVerticalBlock"] .jarvis-root-marker)
  ) {
    bottom:10px !important;right:10px !important;
    width:calc(100vw - 20px) !important;
    max-width:calc(100vw - 20px) !important;
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
    st.session_state["jarvis_open"] = True


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


def _render_jarvis_conversation(evidence):
    """Dedicated floating-panel layout; standalone central Copilot untouched."""
    bridge=build_cet1_bridge(evidence)
    history=_get_thread(evidence)

    # Keep the composer's contents across a contextual handoff from Morning
    # Brief. Never copy these prompts to Synthetic session state.
    queued=st.session_state.pop("real_cfo_question_compact",None)
    if queued:
        st.session_state["jarvis_composer_text"]=queued

    # Scrollable, separate conversation area. The composer is a SIBLING of
    # this container, never absolutely overlaid on the model's answer.
    with st.container():
        render_html('<span class="jarvis-history-marker" aria-hidden="true"></span>')
        if not history:
            st.info("Ask Jarvis about Group CET1, capital or risk-weighted assets.")
            if st.button("Investigate Q2 2026 CET1",
                         key="jarvis_first_investigation",
                         use_container_width=True):
                _send(DEFAULT_QUESTION,evidence,history)
        for index,message in enumerate(history[-16:]):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if message["role"]=="assistant":
                    st.caption("AI interpretation · ABN factsheet · review underlying causes")
                    if index==len(history[-16:])-1:
                        # Evidence is deterministic, sourced and placed AFTER
                        # the model reply (inside the scrollable body).
                        with st.expander("Show CET1 visual evidence",expanded=False):
                            render_cet1_visuals(bridge,compact=True)

    # This footer follows the scroll area in normal Streamlit layout and
    # cannot cover earlier assistant replies.
    with st.form("jarvis_composer_form",clear_on_submit=True):
        question=st.text_area(
            "Ask Jarvis a follow-up",
            placeholder="E.g. What does the RWA contribution mean?",
            key="jarvis_composer_text",max_chars=800,height=70,
        )
        asked=st.form_submit_button("Send to Jarvis →",use_container_width=True)
    if asked and question.strip():
        _send(question,evidence,history)


def render_floating_copilot(s):
    """Persistent bottom-right Jarvis in every Real Data view.

    The central Ask CFO Copilot radial action and its existing page are never
    modified. Uses ONLY old-version-compatible st.container() without key.
    """
    if not getattr(s,"is_reported",False):
        return
    render_html(BALLOON_CSS)
    with st.container():
        render_html('<span class="jarvis-root-marker" aria-hidden="true"></span>')
        opened=bool(st.session_state.get("jarvis_open",False))
        if not opened:
            render_html('<span class="jarvis-closed-marker" aria-hidden="true"></span>')
            if st.button("✦ Jarvis",key="jarvis_launcher"):
                st.session_state["jarvis_open"]=True
                st.rerun()
            return

        render_html('<span class="jarvis-open-marker" aria-hidden="true"></span>')
        head,actions=st.columns([5,1],gap="small")
        with head:
            render_html(
                '<div class="jarvis-heading">✦ Jarvis</div>'
                '<div class="jarvis-subtitle">ABN CFO Assistant · Real Data</div>'
            )
        with actions:
            if st.button("✕",key="jarvis_close",help="Close Jarvis"):
                st.session_state["jarvis_open"]=False
                st.rerun()

        if st.button("New conversation",key="jarvis_reset",use_container_width=True):
            st.session_state[HISTORY_KEY]=[]
            st.session_state["jarvis_composer_text"]=""
            st.rerun()

        if s.business_line:
            st.info(
                "Group CET1 investigation only. Switch to Group reporting "
                "to use Jarvis; segment explanations are not yet supported."
            )
            return
        try:
            evidence=build_reported_evidence(s,"Capital")
            _render_jarvis_conversation(evidence)
        except ValueError:
            st.error("Reported capital values cannot be reconciled; Jarvis is unavailable.")
