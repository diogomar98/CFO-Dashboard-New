"""Public-only Real Data What-If comparisons against a matched neutral baseline.

Never feeds prototype loan/deposit betas or synthetic forecasts to the bank
financials. Paired runs use the SAME chosen model on the SAME Group dataset.
"""
import math

import pandas as pd

from src.public_horizon_engine import build_public_horizon


SCENARIO_METHODS = {
    "Auto · same as Horizon": "auto",
    "Rate-sensitive model (ARX)": "rate_arx",
    "Flat financial baseline (ECB-insensitive)": "no_change",
}
NEUTRAL_INPUTS = {
    "method": "rate_arx",
    "rate_shock_bps": 0.0,
    "nim_overlay_bps": 0.0,
    "nii_overlay_pct": 0.0,
}
METRICS = ("nim_bps", "nii_m")


def build_public_scenario_comparison(public, options):
    """Source-grounded base vs scenario; financial actuals stay unchanged."""
    if not isinstance(options, dict):
        raise ValueError("Scenario options must be a dictionary.")
    method = options.get("method", "rate_arx")
    if method not in {"auto", "rate_arx", "no_change"}:
        raise ValueError("Unsupported What-If model.")
    for key in ("rate_shock_bps", "nim_overlay_bps", "nii_overlay_pct"):
        if key not in options or not math.isfinite(float(options[key])):
            raise ValueError(f"Missing or invalid {key} scenario input.")
    # Reference and stress MUST have identical estimated model selection.
    baseline, baseline_info = build_public_horizon(public, model_preference=method)
    scenario, scenario_info = build_public_horizon(
        public,model_preference=method,
        rate_shock_bps=float(options["rate_shock_bps"]),
        nim_overlay_bps=float(options["nim_overlay_bps"]),
        nii_overlay_pct=float(options["nii_overlay_pct"]),
    )
    before=baseline[baseline["series"]=="Actual"].reset_index(drop=True)
    after=scenario[scenario["series"]=="Actual"].reset_index(drop=True)
    for metric in METRICS:
        if not before[metric].equals(after[metric]):
            raise ValueError("Scenario altered a published historical observation.")
    base=baseline[baseline["series"]=="Baseline"].reset_index(drop=True)
    stress=scenario[scenario["series"]=="Baseline"].reset_index(drop=True)
    if base["quarter"].tolist()!=stress["quarter"].tolist() or len(base)!=4:
        raise ValueError("Scenario quarter mismatch.")
    rows=[]
    for i in range(4):
        rows.append({
            "date":base.iloc[i]["date"],
            "quarter":base.iloc[i]["quarter"],
            "base_nim_bps":float(base.iloc[i]["nim_bps"]),
            "scenario_nim_bps":float(stress.iloc[i]["nim_bps"]),
            "delta_nim_bps":float(stress.iloc[i]["nim_bps"]-base.iloc[i]["nim_bps"]),
            "base_nii_m":float(base.iloc[i]["nii_m"]),
            "scenario_nii_m":float(stress.iloc[i]["nii_m"]),
            "delta_nii_m":float(stress.iloc[i]["nii_m"]-base.iloc[i]["nii_m"]),
        })
    df=pd.DataFrame(rows)
    end_2026=df[df["date"].dt.year==2026]
    fy_base=float(baseline_info["fy_nii_m"])
    fy_stress=float(scenario_info["fy_nii_m"])
    if not math.isfinite(fy_base) or not math.isfinite(fy_stress):
        raise ValueError("Incomplete FY2026 Group NII calculation.")
    selected = {
        "nim":baseline_info["diagnostics"]["nim_bps"]["model"],
        "nii":baseline_info["diagnostics"]["nii_m"]["model"],
    }
    impact = {
        "model_choice": method,
        "selected_models": selected,
        "flat_for": [
            label for label,key in (("NIM","nim"),("NII","nii"))
            if selected[key]=="no_change"
        ],
        "q4_nim_bps":float(end_2026.iloc[-1]["delta_nim_bps"]),
        "q4_nii_m":float(end_2026.iloc[-1]["delta_nii_m"]),
        "fy_nii_delta_m":fy_stress-fy_base,
        "fy_nii_baseline_m":fy_base,
        "fy_nii_scenario_m":fy_stress,
        "fy_nii_actual_m":float(baseline_info["fy_nii_actual_m"]),
        "fy_nii_baseline_projected_m":float(baseline_info["fy_nii_projected_m"]),
        "fy_nii_scenario_projected_m":float(scenario_info["fy_nii_projected_m"]),
        "dfr_reference_pct":float(baseline_info["last_ecb_qend_pct"]),
        "dfr_stress_pct":float(scenario_info["future_dfr_pct"]),
        "dfr_shock_bps":float(options["rate_shock_bps"]),
        "overlays_applied": (
            abs(float(options["nim_overlay_bps"])) > 1e-10
            or abs(float(options["nii_overlay_pct"])) > 1e-10
        ),
    }
    return baseline,scenario,df,impact
