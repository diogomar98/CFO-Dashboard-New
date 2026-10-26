"""Source-backed executive watchpoints for the Real Data Horizon.

These are DESCRIPTIVE quarterly movements, not causal forecasts. This package
does not include segment NII/NIM or repricing/funding cost parameters.
"""
from __future__ import annotations

import pandas as pd

ALLOWED_SEGMENTS = (
    "Personal & Business Banking", "Corporate Banking",
    "Wealth Management", "Group Functions",
)


def segment_driver_watchpoints(segments: pd.DataFrame, group: pd.DataFrame):
    """Rank material published segment movements, without inventing NIM drivers."""
    required = {"date", "business_line", "loans_m", "deposits_m", "rwa_m"}
    if (not isinstance(segments,pd.DataFrame) or
        not isinstance(group,pd.DataFrame) or
        not required.issubset(segments.columns) or
        not {"date","loans_m","deposits_m","rwa_m"}.issubset(group.columns)):
        return []
    s=segments.copy()
    g=group.copy()
    s["date"]=pd.to_datetime(s["date"])
    g["date"]=pd.to_datetime(g["date"])
    last=g.sort_values("date").iloc[-1]
    end=last["date"]
    periods=sorted(s["date"].unique())
    if end not in set(periods) or len(periods)<2:
        return []
    previous=max(period for period in periods if period<end)
    latest=s.loc[s["date"]==end].set_index("business_line")
    prior=s.loc[s["date"]==previous].set_index("business_line")
    if (set(latest.index)!=set(ALLOWED_SEGMENTS) or
        set(prior.index)!=set(ALLOWED_SEGMENTS) or
        latest.index.has_duplicates or prior.index.has_duplicates):
        return []
    for metric in ("loans_m","deposits_m","rwa_m"):
        if (latest[metric].isna().any() or prior[metric].isna().any() or
            pd.isna(last[metric]) or
            abs(float(latest[metric].sum())-float(last[metric]))>0.1):
            return []
    delta=latest[["loans_m","deposits_m","rwa_m"]]-prior[
        ["loans_m","deposits_m","rwa_m"]]
    loan_leader=delta["loans_m"].idxmax()
    loan_change=float(delta.loc[loan_leader,"loans_m"])
    deposit_laggard=delta["deposits_m"].idxmin()
    deposit_change=float(delta.loc[deposit_laggard,"deposits_m"])
    rwa_leader=latest["rwa_m"].idxmax()
    rwa=float(latest.loc[rwa_leader,"rwa_m"])
    rwa_share=100*rwa/float(last["rwa_m"])
    group_deposit_delta=float(delta["deposits_m"].sum())
    headline=lambda x: x.split(" Banking")[0] if x.endswith(" Banking") else x

    return [
        {
            "topic":"LENDING MOMENTUM",
            "title":loan_leader,
            "number":f"{loan_change/1000:+.2f}bn",
            "unit":"€ · loans QoQ",
            "colour":"green" if loan_change>=0 else "amber",
            "body":(
                "Largest segment increase in customer loans this quarter. "
                "Investigate new volumes and repricing separately; the supplied "
                "figures cannot establish how much NII this growth generates."
                if loan_change>=0 else
                "Highest quarter-on-quarter loan movement among business lines. "
                "Confirm volumes and pricing before assuming an income effect."
            ),
        },
        {
            "topic":"FUNDING WATCH",
            "title":deposit_laggard,
            "number":f"{deposit_change/1000:+.2f}bn",
            "unit":"€ · deposits QoQ",
            "colour":"amber" if deposit_change<0 else "green",
            "body":(
                f"Largest decline in segment deposits; Group deposits "
                f"moved €{group_deposit_delta/1000:+.2f}bn QoQ. "
                "Review customer mix, funding costs and stability. "
                "Deposit balances alone do not identify the cause."
                if deposit_change<0 else
                "Smallest increase in segment deposits. Review funding mix "
                "and repricing; balances do not reveal deposit beta."
            ),
        },
        {
            "topic":"CAPITAL SENSITIVITY",
            "title":rwa_leader,
            "number":f"{rwa_share:.1f}%",
            "unit":"of Group RWA",
            "colour":"blue",
            "body":(
                f"€{rwa/1000:,.2f}bn of quarter-end Group risk-weighted assets "
                "sit in this segment. Prioritise exposure and capital-efficiency "
                "monitoring, not an assumed causal link to Group NIM."
            ),
        },
    ]
