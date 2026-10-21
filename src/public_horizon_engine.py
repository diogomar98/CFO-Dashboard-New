"""PUBLIC-ONLY Real Data Horizon, distinct from the unchanged Synthetic model.

History: 22 separately cross-checked Group NII and NIM factsheet quarters,
plus calendar-day-average ECB deposit facility rates based on official ECB
rate-change observations. The macro signal is *not* ABN's internal loan yield.

Two minimal competing forecasts are tested: last reported value and a ridge-
shrunk ARX (lagged bank metric + lagged ECB policy-rate movement). Historical
rolling-origin errors size model-ASSUMED 90% and 95% prediction bands; no claim
of empirical coverage at either level is made with this sample.
"""
from pathlib import Path
import math

import numpy as np
import pandas as pd


GROUP_PATH = Path("data/abn_group_nii_nim_2021_public.csv")
ECB_PATH = Path("data/ecb_dfr_quarterly_2021_public.csv")
SOURCE_LAST = "2026-06-30"
FORECAST_QUARTERS = 4
MIN_TRAIN = 12
CRITICAL_VALUES = {90: 1.64485362695, 95: 1.95996398454}
MODELS = {"auto", "rate_arx", "no_change"}
BOUNDS = {"rate_shock_bps": (-100.0, 100.0),
          "nim_overlay_bps": (-15.0, 15.0),
          "nii_overlay_pct": (-7.0, 7.0)}


def load_public_horizon_inputs(reported_group=None, group_path=GROUP_PATH, ecb_path=ECB_PATH):
    """Fail closed on missing, misaligned, duplicated, incompatible public inputs."""
    group = pd.read_csv(group_path, parse_dates=["date"])
    rates = pd.read_csv(ecb_path, parse_dates=["date"])
    for df, keys in (
        (group, {"date", "nii_m", "nim_bps", "source_url", "nii_cell", "nim_cell"}),
        (rates, {"date", "dfr_qavg_pct", "dfr_qend_pct", "source_url", "days"}),
    ):
        if not keys.issubset(df.columns):
            raise ValueError("Public Horizon source columns missing: " + str(keys - set(df.columns)))
        if df["date"].isna().any() or df["date"].duplicated().any():
            raise ValueError("Invalid or duplicate reporting dates in source files.")
        if len(df) != 22:
            raise ValueError("Expected exactly 22 public quarters from 2021 Q1 through 2026 Q2.")

    frame = group.merge(
        rates[["date", "dfr_qavg_pct", "dfr_qend_pct", "days", "source_url"]],
        on="date", validate="one_to_one", suffixes=("_bank", "_ecb")
    ).sort_values("date").reset_index(drop=True)
    periods = frame["date"].dt.to_period("Q")
    expected = pd.period_range("2021Q1", "2026Q2", freq="Q")
    if list(periods) != list(expected):
        raise ValueError("Public Horizon reporting quarters are not consecutive or complete.")
    if frame.iloc[-1]["date"].strftime("%Y-%m-%d") != SOURCE_LAST:
        raise ValueError("Wrong public data cutoff.")
    for col in ("nii_m", "nim_bps", "dfr_qavg_pct", "dfr_qend_pct"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
        if not np.isfinite(frame[col]).all():
            raise ValueError(f"Missing or nonfinite source value in {col}.")
    if (frame["nii_m"] <= 0).any() or (frame["nim_bps"] <= 0).any():
        raise ValueError("Historical Group NII/NIM out of validated range.")
    if not frame["source_url_bank"].astype(str).str.startswith("https://assets.ctfassets.net/").all():
        raise ValueError("Unexpected bank source domain.")
    if not frame["source_url_ecb"].astype(str).str.startswith("https://data-api.ecb.europa.eu/").all():
        raise ValueError("Unexpected ECB source domain.")
    if not frame["days"].between(90, 92).all():
        raise ValueError("Unexpected quarter length in derived ECB rates.")
    if reported_group is not None:
        actual = reported_group.sort_values("date").iloc[-1]
        if pd.Timestamp(actual["date"]) != pd.Timestamp(SOURCE_LAST):
            raise ValueError("Live factsheet actuals are not at the same reporting close.")
        for public_key, local_key in (("nii_m", "nii_m"), ("nim_bps", "nim_bps")):
            if abs(float(actual[local_key]) - float(frame.iloc[-1][public_key])) > .005:
                raise ValueError(
                    f"PUBLIC SOURCE CHECK FAILED: {public_key} Q2 2026 disagrees "
                    "with the existing ABN factsheet dataset."
                )
    return frame


def _source_series(frame, metric):
    values = frame[metric].to_numpy(dtype=float)
    return np.log(values) if metric == "nii_m" else values


def _fit_arx(y, dfr):
    """Small ridge model with an unpenalized intercept and two predictors."""
    if len(y) < MIN_TRAIN:
        raise ValueError("Insufficient observations to fit the quarterly public ARX.")
    target = y[2:]
    lag_metric = y[1:-1]
    lag_rate_move = np.diff(dfr)[:-1]  # dfr_(t-1) - dfr_(t-2)
    raw_x = np.column_stack([lag_metric, lag_rate_move])
    xmean = raw_x.mean(axis=0)
    xstd = np.maximum(raw_x.std(axis=0), [1e-6, .05])
    ymean = float(target.mean())
    ystd = max(float(target.std()), 1e-6)
    x = np.column_stack([np.ones(len(target)), (raw_x - xmean) / xstd])
    target_standard = (target - ymean) / ystd
    ridge = np.diag([0.0, 2.5, 2.5])
    beta = np.linalg.solve(x.T @ x + ridge, x.T @ target_standard)
    return (xmean, xstd, ymean, ystd, beta)


def _arx_step(lag_y, lag_dfr_move, params):
    xmean, xstd, ymean, ystd, beta = params
    standardized = (np.array([lag_y, lag_dfr_move]) - xmean) / xstd
    return float(ymean + ystd * (beta[0] + np.dot(beta[1:], standardized)))


def _forecast_from_origin(y, dfr, dfr_quarter_end, origin, horizon, model,
                          rate_shock_bps=0.0, level_overlay=0.0):
    """Predict from data KNOWN at origin, never reading future actual rates."""
    if model not in {"rate_arx", "no_change"}:
        raise ValueError("Unknown model")
    params = _fit_arx(y[:origin+1], dfr[:origin+1]) if model == "rate_arx" else None
    prior = float(y[origin])
    previous_rate = float(dfr[origin - 1])
    current_rate = float(dfr[origin])
    # An as-of-origin flat forward rate starts at the *known quarter-end*
    # DFR, not the trailing quarterly average (these diverge at rate turns).
    projected_rate = float(dfr_quarter_end[origin]) + float(rate_shock_bps) / 100.0
    forecasts=[]
    for h in range(1,horizon+1):
        rate_move_known_at_prior = current_rate - previous_rate
        predicted = (_arx_step(prior, rate_move_known_at_prior, params)
                     if model == "rate_arx" else prior)
        predicted += float(level_overlay)
        forecasts.append(predicted)
        prior = predicted
        previous_rate, current_rate = current_rate, projected_rate
    return np.array(forecasts,dtype=float)


def _rolling_errors(y, dfr, dfr_quarter_end, model, h):
    """Expanding-window genuinely out-of-sample errors for one fixed method."""
    residuals=[]
    for origin in range(MIN_TRAIN-1,len(y)-h):
        prediction = _forecast_from_origin(y,dfr,dfr_quarter_end,origin,h,model)[h-1]
        residuals.append(float(y[origin+h]-prediction))
    return np.array(residuals,dtype=float)


def _choose_model(y, dfr, dfr_quarter_end, requested):
    if requested != "auto":
        if requested not in MODELS:
            raise ValueError("Unknown requested model")
        return requested
    baseline = _rolling_errors(y,dfr,dfr_quarter_end,"no_change",1)
    driver = _rolling_errors(y,dfr,dfr_quarter_end,"rate_arx",1)
    base_mae = float(np.mean(np.abs(baseline)))
    drv_mae = float(np.mean(np.abs(driver)))
    # Complexity must demonstrably outperform the no-change benchmark.
    return "rate_arx" if drv_mae < base_mae * 0.95 else "no_change"


def _band(estimate, sigma, level, log_scale):
    critical = CRITICAL_VALUES[level]
    low = estimate - critical*sigma
    high = estimate + critical*sigma
    return ((float(np.exp(low)), float(np.exp(high))) if log_scale
            else (float(low),float(high)))


def build_public_horizon(frame, *, model_preference="auto", rate_shock_bps=0.0,
                         nim_overlay_bps=0.0, nii_overlay_pct=0.0,
                         quarters_ahead=FORECAST_QUARTERS):
    """Return public actual and modelled 4Q levels with validation diagnostics.

    Adjustments are explicit USER SCENARIOS; the neutral run has all zero.
    NII overlay is applied multiplicatively per forward quarter in log space.
    NIM overlay adds a level-change in bps per projected quarter.
    """
    if quarters_ahead != 4:
        raise ValueError("Only the separately backtested four-quarter horizon is supported.")
    if model_preference not in MODELS:
        raise ValueError("Unknown modelling preference.")
    args = {
        "rate_shock_bps": rate_shock_bps,
        "nim_overlay_bps": nim_overlay_bps,
        "nii_overlay_pct": nii_overlay_pct,
    }
    for k,v in args.items():
        lo,hi=BOUNDS[k]
        if not np.isfinite(float(v)) or not lo<=float(v)<=hi:
            raise ValueError(f"Out-of-bounds scenario parameter {k}.")
    if not np.isfinite(frame[["nii_m","nim_bps","dfr_qavg_pct"]].to_numpy(dtype=float)).all():
        raise ValueError("Missing history values prevent forecast.")
    n=len(frame)
    if n != 22:
        raise ValueError("Public forecast requires exactly 22 independently reconciled quarters.")
    periods=pd.to_datetime(frame["date"]).dt.to_period("Q")
    if (frame["date"].duplicated().any()
        or list(periods) != list(pd.period_range("2021Q1","2026Q2",freq="Q"))):
        raise ValueError("Forecast input has duplicated, missing or out-of-order public quarters.")
    dfr=frame["dfr_qavg_pct"].to_numpy(dtype=float)
    dfr_quarter_end=frame["dfr_qend_pct"].to_numpy(dtype=float)
    info={}
    projections={}
    for metric in ("nim_bps","nii_m"):
        historical = _source_series(frame,metric)
        log_scale=metric=="nii_m"
        selected = _choose_model(historical,dfr,dfr_quarter_end,model_preference)
        adjustment=(float(nim_overlay_bps) if not log_scale
                    else math.log1p(float(nii_overlay_pct)/100.0))
        forward=_forecast_from_origin(
            historical,dfr,dfr_quarter_end,n-1,quarters_ahead,selected,
            rate_shock_bps=rate_shock_bps,
            level_overlay=adjustment,
        )
        values=np.exp(forward) if log_scale else forward
        if not np.isfinite(values).all() or (values<=0).any():
            raise ValueError(f"Unusable projected {metric}; review assumptions.")
        bands=[]
        horizon_errors=[]
        for h in range(1,quarters_ahead+1):
            residuals = _rolling_errors(historical,dfr,dfr_quarter_end,selected,h)
            if len(residuals)<5:
                raise ValueError("Too few backtest forecast errors to display a model range.")
            rmse=float(np.sqrt(np.mean(residuals**2)))
            if not np.isfinite(rmse):
                raise ValueError("Unusable historical model errors.")
            horizons={
                "horizon":h,"backtest_count":len(residuals),
                "mae":float(np.mean(np.abs(residuals))),
                "rmse":rmse,
                "central90_hit_pct":float(np.mean(np.abs(residuals)<=CRITICAL_VALUES[90]*rmse)*100),
                "central95_hit_pct":float(np.mean(np.abs(residuals)<=CRITICAL_VALUES[95]*rmse)*100),
            }
            horizon_errors.append(horizons)
            bands.append({confidence:_band(forward[h-1],rmse,confidence,log_scale)
                          for confidence in (90,95)})
        projections[metric] = {"values":values,"bands":bands}
        base_errors=_rolling_errors(historical,dfr,dfr_quarter_end,"no_change",1)
        arx_errors=_rolling_errors(historical,dfr,dfr_quarter_end,"rate_arx",1)
        info[metric]={
            "model":selected,
            "source_rows":n,
            "backtest_1q_count":len(base_errors),
            "baseline_1q_mae":float(np.mean(np.abs(base_errors))),
            "arx_1q_mae":float(np.mean(np.abs(arx_errors))),
            "selected_1q_mae":float(np.mean(np.abs(_rolling_errors(historical,dfr,dfr_quarter_end,selected,1)))),
            "horizons":horizon_errors,
            "error_unit":"log ratio" if log_scale else "basis points",
        }
    historical_rows=[]
    for _,r in frame.iterrows():
        d=pd.Timestamp(r["date"])
        historical_rows.append({
            "date":d,"quarter":f"Q{d.quarter} {d.year}",
            "series":"Actual","source":"Official ABN quarterly factsheet",
            "nii_m":float(r["nii_m"]),"nim_bps":float(r["nim_bps"]),
            "nim_pct":float(r["nim_bps"])/100,
            "dfr_qavg_pct":float(r["dfr_qavg_pct"]),
            "dfr_qend_pct":float(r["dfr_qend_pct"]),
        })
    latest=pd.Timestamp(frame.iloc[-1]["date"]).to_period("Q")
    past_end_rate=float(frame.iloc[-1]["dfr_qend_pct"])
    future_dfr=past_end_rate+float(rate_shock_bps)/100.0
    forecast_rows=[]
    for h in range(1,quarters_ahead+1):
        q=latest+h
        values={
            "date":q.end_time.normalize(),"quarter":f"Q{q.quarter} {q.year}",
            "series":"Baseline","source":"Model-estimated (not reported or ABN guidance)",
            "nim_bps":float(projections["nim_bps"]["values"][h-1]),
            "nii_m":float(projections["nii_m"]["values"][h-1]),
            "dfr_qavg_pct":future_dfr,"dfr_qend_pct":future_dfr,
        }
        values["nim_pct"]=values["nim_bps"]/100
        for metric in ("nim_bps","nii_m"):
            for level in (90,95):
                lo,hi=projections[metric]["bands"][h-1][level]
                if metric=="nim_bps":
                    lo,hi=lo/100,hi/100
                    label="nim_pct"
                else:
                    label="nii_m"
                values[f"{label}_low_{level}"]=lo
                values[f"{label}_high_{level}"]=hi
        forecast_rows.append(values)
    result=pd.concat([pd.DataFrame(historical_rows),pd.DataFrame(forecast_rows)],
                     ignore_index=True)
    target_year=latest.year
    year_end=next((r for r in forecast_rows if r["date"].year==target_year
                   and pd.Timestamp(r["date"]).quarter==4),None)
    actual_ytd=frame.loc[frame["date"].dt.year==target_year,"nii_m"]
    projected_ytd=[r["nii_m"] for r in forecast_rows if r["date"].year==target_year]
    fy_total=(float(actual_ytd.sum()+sum(projected_ytd))
              if len(actual_ytd)+len(projected_ytd)==4 else float("nan"))
    return result,{
        "observed_quarters":n,
        "last_quarter":f"Q{latest.quarter} {latest.year}",
        "year_end_quarter":f"Q4 {target_year}",
        "year_end_nim_pct":year_end["nim_pct"] if year_end else float("nan"),
        "year_end_nim_change_bps":(
            year_end["nim_bps"]-float(frame.iloc[-1]["nim_bps"]) if year_end else float("nan")
        ),
        "fy_nii_m":fy_total,
        "fy_nii_actual_m":float(actual_ytd.sum()),
        "fy_nii_projected_m":float(sum(projected_ytd)),
        "first_nim_change_bps":float(forecast_rows[0]["nim_bps"]-frame.iloc[-1]["nim_bps"]),
        "first_nii_change_pct":float(
            (forecast_rows[0]["nii_m"]/float(frame.iloc[-1]["nii_m"])-1)*100
        ),
        "last_ecb_qend_pct":past_end_rate,
        "future_dfr_pct":future_dfr,
        "rate_shock_bps":float(rate_shock_bps),
        "model_preference":model_preference,
        "diagnostics":info,
    }
