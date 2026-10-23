"""Jarvis: separate Real Data floating chat; central Ask CFO Copilot unchanged.

Uses native older-Streamlit-compatible widgets and scoped fixed-position CSS,
with a distinct scrolling message body and an ordinary composer footer.
All CET1 evidence charts are derived locally from verified quarterly actuals.
"""
import inspect
import time
from uuid import uuid4

import altair as alt
import pandas as pd
import streamlit as st

from src.hud import render_html
from src.reported_copilot_evidence import build_reported_evidence
from src.reported_copilot_partner import (
    DEFAULT_QUESTION, answer_reported_question, build_cet1_bridge,
)
from src.reported_genie_partner import (
    answer_real_genie_question, real_genie_configured,
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
    bottom:12px !important;
    /* Dialog windows use a transformed, centred containing block on ABN.
       Account for that offset so Jarvis reaches the VIEWPORT right edge. */
    right:clamp(-480px,calc((100% - 100vw)/2 + 16px),16px) !important;
    z-index:2147483000 !important;
    width:min(560px,calc(100vw - 24px)) !important;
    max-width:min(560px,calc(100vw - 24px)) !important;
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
    height:min(730px,calc(100dvh - 24px)) !important;
    max-height:calc(100dvh - 24px) !important;
    overflow-y:auto !important;
    overflow-x:hidden !important;
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
    max-height:calc(min(730px,100dvh - 24px) - 240px) !important;
    min-height:0 !important;
    overflow-y:auto !important;
    flex:1 1 auto !important;
}
.jarvis-root-marker,.jarvis-open-marker,.jarvis-closed-marker,
.jarvis-history-marker,.cfo-thread-history-marker {display:none;}
.jarvis-heading {font-weight:850;font-size:1.05rem;color:#E3FFEA;}
.jarvis-subtitle {font-size:.67rem;color:#A9CCB2;margin-top:.1rem;}
div[data-testid="stVerticalBlock"]:has(.jarvis-history-marker):not(
  :has(div[data-testid="stVerticalBlock"] .jarvis-history-marker)
) {
    overflow-y:auto !important;
    overscroll-behavior:contain;
    min-height:160px !important;
    height:min(460px,calc(100dvh - 270px)) !important;
    max-height:min(460px,calc(100dvh - 270px)) !important;
    flex:1 1 auto !important;
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
/* Older ABN Streamlit: independent scroll area in central Ask CFO Copilot. */
div[data-testid="stVerticalBlock"]:has(.cfo-thread-history-marker):not(
  :has(div[data-testid="stVerticalBlock"] .cfo-thread-history-marker)
) {
    max-height:min(450px,48vh) !important;
    overflow-y:auto !important;
    overflow-x:hidden !important;
    min-height:170px !important;
    padding:10px !important;
    border:1px solid rgba(76,145,92,.29);
    border-radius:8px;
}
div[data-testid="stVerticalBlock"]:has(.jarvis-root-marker):not(
  :has(div[data-testid="stVerticalBlock"] .jarvis-root-marker)
) [data-testid="stForm"] {
    background:rgba(11,32,20,.98);
    padding:.45rem .55rem !important;
    border-top:1px solid rgba(86,159,109,.35);
    border-radius:7px;
    position:relative;
    z-index:3;
    flex-shrink:0 !important;
}
/* Modern chat avatars, without image assets or native Streamlit theme changes. */
div[data-testid="stChatMessageAvatarAssistant"],
div[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessage"] [data-testid="stChatMessageAvatar"] {
    border-radius:13px !important;
    background:linear-gradient(145deg,#153d29,#0d211a) !important;
    border:1px solid rgba(88,198,123,.52) !important;
    box-shadow:0 2px 14px rgba(28,166,84,.16);
}
.jarvis-toolbar-label {font-size:.66rem;color:#A4C6AF;letter-spacing:.05em;}
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
THREADS_KEY = "real_cfo_chat_threads_36h"
ACTIVE_KEY = "real_cfo_active_thread"
THREAD_TTL_SECONDS = 36 * 60 * 60
MAX_CONVERSATIONS = 12
MAX_STORED_MESSAGES = 24


def _genie_evidence(evidence, method):
    """Keep distinct, 36-hour threads for SQL Genie vs source-packet AI."""
    if method!="genie":
        return evidence
    return dict(evidence,topic="Real Genie · "+evidence["topic"])


def _answer_method(*,compact):
    """Explicit opt-in: the synthetic Genie agent is never a fallback."""
    label="Answer using"
    mode=st.selectbox(
        label,
        ["Reported factsheet · AI", "Real Data Genie · SQL"],
        key="jarvis_method" if compact else "real_cfo_method",
        help=(
            "Factsheet AI uses the uploaded financial figures; "
            "Real Genie uses only the separately configured Unity Catalog "
            "agent with inspectable SQL and query rows."
        ),
    )
    if mode.startswith("Real Data Genie") and not real_genie_configured():
        st.caption(
            "Real Genie is not configured yet. Create the Real Data Genie "
            "Agent, attach the approved Unity Catalog reporting tables and "
            "set REAL_GENIE_SPACE_ID for this Databricks App. "
            "No Synthetic agent is used."
        )
    return "genie" if mode.startswith("Real Data Genie") else "factsheet"


def _valid_threads(threads, now):
    """Pure TTL pruning; last activity refreshes a conversation's expiry."""
    keep = []
    for thread in threads if isinstance(threads, list) else []:
        if not isinstance(thread, dict):
            continue
        if not isinstance(thread.get("id"),str) or not isinstance(thread.get("messages"),list):
            continue
        touched = thread.get("updated_at")
        if not isinstance(touched,(int,float)) or not 0 <= now-touched < THREAD_TTL_SECONDS:
            continue
        keep.append(thread)
    return sorted(keep,key=lambda x:x["updated_at"],reverse=True)[:MAX_CONVERSATIONS]


def _create_thread(evidence, *, now=None):
    """Create a source-scoped, temporary thread; cannot cross ABN users."""
    now=time.time() if now is None else now
    signature=_scope_signature(evidence)
    thread={
        "id":uuid4().hex,
        "title":"New financial question",
        "created_at":now,
        "updated_at":now,
        "signature":signature,
        "messages":[],
    }
    current=_valid_threads(st.session_state.get(THREADS_KEY,[]),now)
    st.session_state[THREADS_KEY]=[thread]+current[:MAX_CONVERSATIONS-1]
    st.session_state[ACTIVE_KEY]=thread["id"]
    st.session_state[CONTEXT_KEY]=signature
    st.session_state[HISTORY_KEY]=thread["messages"]
    return thread


def _scope_signature(evidence):
    return (evidence["scope"],evidence["as_of"],evidence["source"],evidence["topic"])


def _available_threads(evidence, *, now=None):
    now=time.time() if now is None else now
    stored=_valid_threads(st.session_state.get(THREADS_KEY,[]),now)
    st.session_state[THREADS_KEY]=stored
    return [thread for thread in stored if tuple(thread.get("signature",()))==_scope_signature(evidence)]


def _switch_thread(evidence, thread_id):
    options=_available_threads(evidence)
    selected=next((t for t in options if t["id"]==thread_id),None)
    if selected is None:
        return False
    st.session_state[ACTIVE_KEY]=selected["id"]
    st.session_state[HISTORY_KEY]=selected["messages"]
    st.session_state[CONTEXT_KEY]=_scope_signature(evidence)
    return True


def _conversation_picker(evidence, *, compact=False):
    """Shared Jarvis/Copilot selector; conversations survive view navigation."""
    threads=_available_threads(evidence)
    if not threads:
        return
    active=st.session_state.get(ACTIVE_KEY)
    ids=[thread["id"] for thread in threads]
    labels={t["id"]:t["title"] for t in threads}
    method_tag="genie" if "Real Genie" in evidence.get("topic","") else "factsheet"
    key=("jarvis_history_select_" if compact else "real_cfo_history_select_")+method_tag
    # Widget keys are synced before rendering to avoid stale previous choices.
    if st.session_state.get(key) not in ids:
        st.session_state[key]=active if active in ids else ids[0]
    chosen=st.selectbox(
        "Conversation history · expires 36h after last message",
        ids,index=ids.index(st.session_state[key]),
        format_func=lambda tid: labels.get(tid,"Conversation"),
        key=key,
    )
    if chosen!=active and _switch_thread(evidence,chosen):
        st.rerun()


def _new_conversation(evidence):
    _create_thread(evidence)
    st.session_state.pop("jarvis_composer_text",None)
    st.rerun()


def prepare_cet1_investigation(question=None):
    """Prepare the first Jarvis question and open the separate floating panel."""
    st.session_state["real_cfo_question_compact"] = (
        question or DEFAULT_QUESTION
    )
    st.session_state["jarvis_open"] = True


def _capital_bridge_chart(bridge):
    """One compact source-derived contribution chart, designed for narrow chat.

    Three bars: capital numerator contribution, RWA denominator contribution,
    and reconciled net CET1 ratio movement. Short horizontal-axis labels
    prevent category text collision in small visual evidence panels.
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
    """Use the selected conversation; TTL retained only in this Streamlit session."""
    options=_available_threads(evidence)
    active=st.session_state.get(ACTIVE_KEY)
    current=next((t for t in options if t["id"]==active),None)
    if current is None:
        current=options[0] if options else _create_thread(evidence)
        st.session_state[ACTIVE_KEY]=current["id"]
    st.session_state[CONTEXT_KEY]=_scope_signature(evidence)
    st.session_state[HISTORY_KEY]=current["messages"]
    return current["messages"]


def _send(question,evidence,history,*,method="factsheet"):
    """Choose independent source-backed factsheet or governed Genie SQL."""
    question=question.strip()
    if not question or len(question)>1200:
        st.warning("Ask one question of at most 1,200 characters.")
        return
    previous=list(history)
    thread=next((t for t in st.session_state.get(THREADS_KEY,[])
                 if t["id"]==st.session_state.get(ACTIVE_KEY)),None)
    with st.spinner(
        "Querying approved Real Genie data…" if method=="genie"
        else "Investigating the reported figures…"
    ):
        try:
            if method=="genie":
                if not real_genie_configured():
                    st.warning("Set REAL_GENIE_SPACE_ID for the new Real Data Genie Agent.")
                    return
                result=answer_real_genie_question(
                    question,scope=evidence["scope"],
                    conversation_id=thread.get("genie_conversation_id") if thread else None,
                )
            else:
                result=answer_reported_question(
                    question,evidence,history=previous,
                )
        except Exception as exc:
            # Never expose Genie SQL, credentials, user proxy headers or
            # internal financial records through a raw exception.
            st.error(
                "The Real Genie Agent could not be queried. Check its ID, "
                "CAN RUN permission, warehouse and table grants."
                if method=="genie" else
                "The existing ABN AI Gateway could not answer the question. "
                "No synthetic data was substituted."
            )
            st.caption(f"Error class: {type(exc).__name__}")
            return
    assistant={
        "role":"assistant","content":result["answer"],
        "source":result["source"],
        "used_genie":method=="genie",
    }
    if method=="genie":
        assistant["sql"]=result.get("sql")
        assistant["data"]=result.get("data")
        assistant["has_rows"]=result.get("has_rows",False)
        assistant["query_rows_status"]=result.get("query_rows_status","unavailable")
        if thread:
            thread["genie_conversation_id"]=result.get("conversation_id")
    history.extend([
        {"role":"user","content":question},assistant,
    ])
    if len(history)>MAX_STORED_MESSAGES:
        del history[:-MAX_STORED_MESSAGES]
    now=time.time()
    if thread:
        thread["updated_at"]=now
        if thread["title"]=="New financial question":
            thread["title"]=question[:46]+("…" if len(question)>46 else "")
    st.rerun()


def _genie_provenance(item):
    """Keep generated SQL, exact returned data and limitations inspectable."""
    if not item.get("used_genie"):
        return
    st.caption("Real Data Genie · governed Unity Catalog views · read-only")
    with st.expander("Inspect Genie SQL and retrieved source rows",expanded=False):
        if item.get("sql"):
            st.code(item["sql"],language="sql")
        else:
            st.caption("Genie did not return a SQL attachment.")
        data=item.get("data")
        if isinstance(data,pd.DataFrame) and not data.empty:
            st.dataframe(data,use_container_width=True,hide_index=True)
        else:
            status=item.get("query_rows_status","unavailable")
            reasons={
                "no_sql_attachment":"Genie did not generate a SQL query for this answer.",
                "zero_query_rows":"The generated SQL returned zero rows.",
                "missing_statement_response":"Genie did not return a statement response with data rows.",
                "missing_attachment_identifiers":"Genie did not provide the message/attachment IDs needed to fetch rows.",
                "unknown_result_format":"Genie returned an SQL response without rows in a recognised field.",
                "inline_rows_empty":"The API returned an empty inline data array; no rows could be confirmed.",
                "missing_result_payload":"The API returned statement metadata but no result payload.",
                "typed_result_parse_failed":"The API returned typed SQL cells that could not be parsed safely.",
                "external_links_only":"SQL results are available through an external link, not inline.",
                "result_column_count_mismatch":"Genie returned a row that does not match the reported SQL column schema.",
                "sql_statement_api_unavailable":"The SQL Statement Execution API is unavailable in this app's Databricks SDK.",
                "sql_statement_pending":"The Genie SQL statement is still running; try a new conversation after it completes.",
                "sql_statement_closed":"The SQL statement result has already closed or expired.",
                "sql_statement_failed":"The SQL statement reported a failed execution.",
                "sql_statement_canceled":"The SQL statement was cancelled.",
            }
            explanation=reasons.get(status)
            if explanation is None and status.startswith((
                "query_fetch_failed_", "sdk_result_failed_",
                "raw_result_failed_", "external_result_failed_",
                "sql_statement_fetch_failed_"
            )):
                explanation=(
                    "The Genie API SQL-result retrieval failed. "
                    "Diagnostic: "+status
                )
            if explanation is None and status.startswith("external_result_failed_"):
                explanation=(
                    "Genie generated the SQL, but this App could not download "
                    "the signed result chunk. Check workspace network/egress "
                    "policies and available Python dependencies. Error class: "
                    +status.removeprefix("external_result_failed_")
                )
            st.caption(
                (explanation or "No SQL query-result rows were available.")
                +" Numerical conclusions are not verified in this app."
            )



def render_cet1_chat(evidence, *, compact=True):
    """Dedicated Ask CFO Copilot route; now supports any sourced finance question."""
    method=_answer_method(compact=False)
    chat_evidence=_genie_evidence(evidence,method)
    history=_get_thread(chat_evidence)
    st.caption("Ask about capital, profitability, liquidity, segments or reported trends. "
               "Unavailable business causes and figures are identified, not invented.")
    left,right=st.columns([2,1])
    with left:
        start=st.button("Investigate Q2 CET1",key="real_cfo_start_"+str(compact),
                        use_container_width=True,disabled=bool(history))
    with right:
        clear=st.button("New conversation",key="real_cfo_clear_"+str(compact),
                        use_container_width=True)
    if clear:
        _new_conversation(chat_evidence)
    _conversation_picker(chat_evidence,compact=False)
    # The dedicated central view previously placed the composer over replies.
    # A marked, max-height scroll container keeps all replies fully accessible
    # even in the ABN runtime without st.container(height=).
    with st.container():
        render_html('<span class="cfo-thread-history-marker" aria-hidden="true"></span>')
        if not history:
            st.info("Your conversation will appear here. Type your **first question in the box below**.")
        visible=history[-16:]
        for index,item in enumerate(visible):
            with st.chat_message(item["role"], avatar="🤖" if item["role"]=="assistant" else "🧑‍💼"):
                st.markdown(item["content"])
                if item["role"]=="assistant":
                    if item.get("used_genie"):
                        _genie_provenance(item)
                    else:
                        st.caption("Model interpretation · factsheet figures are authoritative")
                        if index==len(visible)-1:
                            _show_answer_visual(evidence,history)
    st.divider()
    with st.form("real_cfo_chat_form_"+str(compact),clear_on_submit=True):
        question=st.text_area(
            "Your question to CFO Copilot",
            placeholder="Type your FIRST question or a follow-up here…",
            max_chars=1200,height=78,
            key="real_cfo_question_"+str(compact),
        )
        asked=st.form_submit_button("Send question",use_container_width=True)
    if start:
        _send(DEFAULT_QUESTION,evidence,history,method=method)
    elif asked and question.strip():
        _send(question,evidence,history,method=method)


def _show_answer_visual(evidence,history):
    """Only factsheet-derived chart data; never parse the language-model text."""
    last_question=next((
        m["content"].lower() for m in reversed(history) if m["role"]=="user"
    ),"")
    candidates=(
        ("cet1_ratio_pct",("cet1","capital ratio")),
        ("nim_bps",("nim","interest margin")),
        ("nii_m",("nii","interest income")),
        ("net_profit_m",("net profit","profit")),
        ("lcr_pct",("lcr","liquidity coverage")),
        ("deposits_m",("deposits","deposit growth")),
        ("loans_m",("loans","lending")),
        ("rwa_m",("rwa","risk-weighted")),
    )
    name=next((field for field,phrases in candidates
               if any(p in last_question for p in phrases)),None)
    if not name:
        return
    with st.expander("Show financial evidence",expanded=False):
        if name in ("cet1_ratio_pct","rwa_m") and evidence["scope"]=="ABN AMRO Group":
            # Do not nest st.expander inside st.expander; older ABN Streamlit
            # raises an exception when expandable visual blocks are nested.
            bridge=build_cet1_bridge(evidence)
            st.caption(
                f"Q1 CET1 {bridge['previous_ratio_pct']:.2f}% → "
                f"Q2 CET1 {bridge['latest_ratio_pct']:.2f}%; "
                f"change {bridge['reported_delta_pp']:+.3f} pp."
            )
            st.altair_chart(_capital_bridge_chart(bridge),use_container_width=True)
            st.caption(
                "Reported Group CET1 capital and RWA arithmetic. "
                "Not an explanation of the underlying business causes."
            )
            return
        history_rows=evidence.get("quarterly_history",[])
        if name in ("nii_m","nim_bps") and evidence.get("group_nii_nim_history_2021"):
            points=[{"quarter":r["quarter"],"value":r.get(name)}
                    for r in evidence["group_nii_nim_history_2021"]]
        else:
            points=[{"quarter":r["quarter"],"value":r["values"].get(name)}
                    for r in history_rows]
        data=pd.DataFrame([r for r in points if r["value"] is not None])
        if data.empty:
            st.caption("No reported observations are available for this chart.")
            return
        plot=alt.Chart(data).mark_line(color="#39C971",point=True).encode(
            x=alt.X("quarter:N",sort=data["quarter"].tolist(),title="Reported quarter",
                    axis=alt.Axis(labelAngle=-35,labelColor="#A8D8BB")),
            y=alt.Y("value:Q",title=name,scale=alt.Scale(zero=False)),
            tooltip=["quarter:N",alt.Tooltip("value:Q",format=",.2f")],
        )
        st.altair_chart(plot.properties(height=185),use_container_width=True)
        st.caption("Published observations only · source: ABN AMRO quarterly factsheets.")


def _render_jarvis_conversation(evidence,*,method="factsheet"):
    """Larger Jarvis chat; SQL Genie is opt-in, not a Synthetic fallback."""
    history=_get_thread(_genie_evidence(evidence,method))
    queued=st.session_state.pop("real_cfo_question_compact",None)
    if queued:
        st.session_state["jarvis_composer_text"]=queued

    with st.container():
        render_html('<span class="jarvis-history-marker" aria-hidden="true"></span>')
        if not history:
            st.info("Type your first question in **Ask Jarvis** below; answers will appear here.")
            if st.button("Investigate Q2 CET1",key="jarvis_first_investigation",
                         use_container_width=True):
                _send(DEFAULT_QUESTION,evidence,history,method=method)
        visible=history[-16:]
        for index,item in enumerate(visible):
            with st.chat_message(item["role"], avatar="🤖" if item["role"]=="assistant" else "🧑‍💼"):
                st.markdown(item["content"])
                if item["role"]=="assistant":
                    if item.get("used_genie"):
                        _genie_provenance(item)
                    else:
                        st.caption("AI interpretation · reported evidence only")
                        if index==len(visible)-1:
                            _show_answer_visual(evidence,history)

    # Separate normal-flow form after bounded chat. It does not cover messages.
    with st.form("jarvis_composer_form",clear_on_submit=True):
        question=st.text_area(
            "Ask Jarvis · type your question",
            placeholder="Ask your first question, e.g. Why did NIM change in 2023?",
            key="jarvis_composer_text",max_chars=1200,height=78,
        )
        asked=st.form_submit_button("Send to Jarvis →",use_container_width=True)
    if asked and question.strip():
        _send(question,evidence,history,method=method)


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
        head,add,actions=st.columns([5,1,1],gap="small")
        with head:
            render_html(
                '<div class="jarvis-heading">🤖 Jarvis</div>'
                '<div class="jarvis-subtitle">ABN CFO Assistant · Real Data</div>'
            )
        with add:
            new=st.button("＋",key="jarvis_reset",help="New conversation")
        with actions:
            if st.button("✕",key="jarvis_close",help="Close Jarvis"):
                st.session_state["jarvis_open"]=False
                st.rerun()

        try:
            evidence=build_reported_evidence(s,"All reported metrics")
            method=_answer_method(compact=True)
            chat_evidence=_genie_evidence(evidence,method)
            _get_thread(chat_evidence)
            if new:
                _new_conversation(chat_evidence)
            with st.expander("🕘 Conversation history · 36h",expanded=False):
                _conversation_picker(chat_evidence,compact=True)
                st.caption(
                    "History is kept for up to 36 hours while this Streamlit "
                    "session is active. Closing the browser or app restart "
                    "may clear it; no shared database is used."
                )
            _render_jarvis_conversation(evidence,method=method)
        except (ValueError,FileNotFoundError):
            st.error("Reported financial evidence is unavailable; Jarvis cannot answer.")
