"""Transparent quarterly CFO Horizon modelling on sourced ABN AMRO actuals.

This module intentionally does not import the synthetic monthly engines.
Every observed point comes from abn_quarterly.csv. All future values are
mechanical, assumption-based illustrations, not ABN's approved forecast.
NII and NIM assumptions are independent (no unreported earning-asset yield or
deposit-beta reconciliation is invented). No statistical confidence is claimed.
"""

import math

import pandas as pd


FORECAST_QUARTERS = 4
CAPS = {
    "nim_change_bps": (-40.0, 40.0),
    "nii_growth_pct": (-15.0, 15.0),
    "loan_growth_pct": (-10.0, 10.0),
    "deposit_growth_pct": (-10.0, 10.0),
    "nim_decay": (0.0, 1.0),
}


def _bounded(value, key):
    value = float(value)
    low, high = CAPS[key]
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{key} must be finite and within {low} to {high}.")
    return value


def _observed_median(frame, key, kind="percentage", periods=3):
    """Median of the latest three actual QoQ movements; missing periods ignored."""
    frame = frame[["date", key]].dropna().sort_values("date").copy()
    if len(frame) < 2:
        return 0.0
    frame["period"] = frame["date"].dt.to_period("Q")
    frame = frame.drop_duplicates(subset="period", keep="last")
    previous = frame[key].shift(1)
    adjacent = ((frame["period"] - frame["period"].shift(1)).map(
        lambda diff: diff.n == 1 if pd.notna(diff) else False
    ))
    if kind == "difference":
        moves = (frame[key] - previous).where(adjacent).dropna().tail(periods)
    else:
        moves = (100.0 * (frame[key] / previous - 1.0)).where(adjacent).dropna().tail(periods)
    if moves.empty:
        return 0.0
    return float(moves.median())


def default_quarterly_assumptions(group):
    """Derive starting assumptions solely from reported consecutive quarters.

    Caps are documented modelling guardrails, NOT ABN business forecasts.
    The raw medians and clipping are exposed in the on-screen methodology.
    """
    choices = {
        "nim_change_bps": _observed_median(group, "nim_bps", "difference"),
        "nii_growth_pct": _observed_median(group, "nii_m"),
        "loan_growth_pct": _observed_median(group, "loans_m"),
        "deposit_growth_pct": _observed_median(group, "deposits_m"),
    }
    clipped = {
        key: round(min(max(value, CAPS[key][0]), CAPS[key][1]), 3)
        for key, value in choices.items()
    }
    clipped["nim_decay"] = 0.5  # Explicit modelling choice, not sourced.
    return clipped


def build_quarterly_horizon(group, assumptions, quarters_ahead=FORECAST_QUARTERS):
    """Return ordered sourced actual + illustrative forecast and diagnostics.

    The Q4 year-end NIM and full-year NII are computed from the actual YTD
    figures and enough forecast quarters to complete that calendar year.
    The available factual history is preserved at its originally reported
    frequency and is never interpolated into months or days.
    """
    if not 1 <= int(quarters_ahead) <= 8:
        raise ValueError("quarters_ahead must be between 1 and 8.")
    if not isinstance(quarters_ahead, int):
        raise ValueError("quarters_ahead must be an integer.")
    required = {"date", "nim_bps", "nii_m", "loans_m", "deposits_m"}
    if not required.issubset(group.columns):
        raise ValueError("Group data missing Horizon source columns.")
    for key in CAPS:
        if key not in assumptions:
            raise ValueError(f"Missing modelling input: {key}.")
    checked = {key: _bounded(assumptions[key], key) for key in CAPS}
    actual = group.copy().sort_values("date").reset_index(drop=True)
    if actual.empty or actual["date"].isna().any():
        raise ValueError("Reported quarterly dataset is empty or date is invalid.")
    last = actual.iloc[-1]
    for key in ("nim_bps", "nii_m", "loans_m", "deposits_m"):
        if pd.isna(last[key]):
            raise ValueError(f"Latest quarter has no reported {key}; cannot project.")

    latest_period = pd.Timestamp(last["date"]).to_period("Q")
    rows = []
    for _, row in actual.iterrows():
        date = pd.Timestamp(row["date"])
        rows.append({
            "date": date, "quarter": f"Q{date.quarter} {date.year}",
            "series": "Actual", "source": "ABN AMRO Q2 2026 factsheet",
            "nim_bps": float(row["nim_bps"]) if pd.notna(row["nim_bps"]) else float("nan"),
            "nim_pct": float(row["nim_bps"]) / 100 if pd.notna(row["nim_bps"]) else float("nan"),
            **{key: float(row[key]) if pd.notna(row[key]) else float("nan")
               for key in ("nii_m", "loans_m", "deposits_m")},
        })
    last_nim = float(last["nim_bps"])
    last_nii = float(last["nii_m"])
    last_loans = float(last["loans_m"])
    last_deposits = float(last["deposits_m"])
    for step in range(1, quarters_ahead + 1):
        q = latest_period + step
        last_nim += checked["nim_change_bps"] * checked["nim_decay"] ** (step - 1)
        last_nii *= 1 + checked["nii_growth_pct"] / 100.0
        last_loans *= 1 + checked["loan_growth_pct"] / 100.0
        last_deposits *= 1 + checked["deposit_growth_pct"] / 100.0
        rows.append({
            "date": q.end_time.normalize(), "quarter": f"Q{q.quarter} {q.year}",
            "series": "Baseline", "source": "Illustrative, assumption-driven calculation",
            "nim_bps": last_nim, "nim_pct": last_nim / 100.0,
            "nii_m": last_nii, "loans_m": last_loans, "deposits_m": last_deposits,
        })

    result = pd.DataFrame(rows)
    forward = result[result["series"] == "Baseline"]
    fiscal_year = latest_period.year
    remaining = max(4 - latest_period.quarter, 0)
    year_end_q = pd.Period(f"{fiscal_year}Q4", freq="Q")
    year_end_forecast = forward.loc[forward["date"].dt.to_period("Q") == year_end_q]
    # Q4 actual already reported: year-end NIM is an actual, not a forecast.
    if remaining == 0:
        year_end_nim = float(last["nim_bps"]) / 100.0
        year_end_kind = "Actual"
    elif not year_end_forecast.empty:
        year_end_nim = float(year_end_forecast.iloc[-1]["nim_pct"])
        year_end_kind = "Illustrative baseline"
    else:
        year_end_nim = float("nan")
        year_end_kind = "Unavailable"

    booked = actual[
        (actual["date"].dt.year == fiscal_year) &
        (actual["date"].dt.to_period("Q") <= latest_period)
    ]["nii_m"]
    forecasts_in_year = forward[forward["date"].dt.year == fiscal_year]["nii_m"]
    # Never claim full-year totals without exactly all 4 quarters supported.
    fy_nii = (float(booked.sum() + forecasts_in_year.sum())
              if len(booked) + len(forecasts_in_year) == 4 else float("nan"))
    first_step = checked["nim_change_bps"]
    reported_nim = float(last["nim_bps"]) / 100.0
    return result, {
        "source_close": pd.Timestamp(last["date"]),
        "latest_quarter": f"Q{latest_period.quarter} {latest_period.year}",
        "fiscal_year": fiscal_year, "year_end_quarter": f"Q4 {fiscal_year}",
        "year_end_nim_pct": year_end_nim, "year_end_kind": year_end_kind,
        "nim_change_to_year_end_bps": (
            (year_end_nim - reported_nim) * 100
            if pd.notna(year_end_nim) else float("nan")
        ),
        "first_quarter_nim_step_bps": first_step,
        "fy_nii_m": fy_nii,
        "fy_nii_actual_m": float(booked.sum()),
        "fy_nii_projected_m": float(forecasts_in_year.sum()),
        "forward_quarters": int(len(forward)),
        "assumptions": checked,
        "reported_nim_pct": reported_nim,
        "reported_nii_m": float(last["nii_m"]),
        "reported_loans_m": float(last["loans_m"]),
        "reported_deposits_m": float(last["deposits_m"]),
    }
