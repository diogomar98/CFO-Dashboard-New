"""Guardrails for the independently sourced 2021–2026 Real Data Horizon."""
import unittest
from pathlib import Path

import pandas as pd

from src.real_data_mode import load_reported
from src.public_horizon_engine import (
    GROUP_PATH, ECB_PATH, load_public_horizon_inputs,
    build_public_horizon, CRITICAL_VALUES, _rolling_errors, _source_series,
)
from src.reported_horizon import _forecast_chart


class PublicHorizonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        group,_=load_reported()
        cls.group=group
        cls.public=load_public_horizon_inputs(group)

    def test_crosschecked_public_series_has_exact_22_consecutive_quarters(self):
        self.assertEqual(len(self.public),22)
        self.assertEqual(self.public.iloc[0]["date"],pd.Timestamp("2021-03-31"))
        self.assertEqual(self.public.iloc[-1]["date"],pd.Timestamp("2026-06-30"))
        self.assertAlmostEqual(self.public.iloc[-1]["nii_m"],1699.854335,places=6)
        self.assertAlmostEqual(self.public.iloc[-1]["nim_bps"],148.750189,places=6)
        self.assertTrue(self.public["source_url_bank"].str.startswith(
            "https://assets.ctfassets.net/").all())
        self.assertTrue(self.public["source_url_ecb"].str.startswith(
            "https://data-api.ecb.europa.eu/").all())

    def test_ecb_source_is_calendar_average_not_rate_change_events(self):
        self.assertAlmostEqual(self.public.iloc[0]["dfr_qavg_pct"],-0.5)
        self.assertAlmostEqual(self.public.iloc[-1]["dfr_qavg_pct"],2.038461538)
        self.assertAlmostEqual(self.public.iloc[-1]["dfr_qend_pct"],2.25)
        self.assertEqual(self.public.iloc[-1]["days"],91)

    def test_public_series_and_app_factsheet_must_match(self):
        modified=self.group.copy()
        modified.loc[modified.index[-1],"nim_bps"]=0
        with self.assertRaisesRegex(ValueError,"SOURCE CHECK FAILED"):
            load_public_horizon_inputs(modified)
        wrong=self.public.copy()
        wrong.loc[wrong.index[1],"date"]=wrong.iloc[0]["date"]
        with self.assertRaises(ValueError):
            build_public_horizon(wrong)
    
    def test_forecasts_and_model_predictions_are_strictly_separate_from_actuals(self):
        output,info=build_public_horizon(self.public)
        self.assertEqual(len(output),26)
        self.assertEqual(output["series"].value_counts()["Actual"],22)
        self.assertEqual(output["series"].value_counts()["Baseline"],4)
        self.assertEqual(output.iloc[21]["quarter"],"Q2 2026")
        self.assertEqual(output.iloc[22]["quarter"],"Q3 2026")
        self.assertEqual(output.iloc[23]["date"],pd.Timestamp("2026-12-31"))
        self.assertEqual(output.iloc[-1]["quarter"],"Q2 2027")
        self.assertAlmostEqual(output.iloc[21]["nii_m"],1699.854335)
        self.assertAlmostEqual(output.iloc[21]["nim_bps"],148.750189)
        self.assertEqual(info["observed_quarters"],22)
        self.assertIn(info["diagnostics"]["nim_bps"]["model"],
                      {"rate_arx","no_change"})
        self.assertIn(info["diagnostics"]["nii_m"]["model"],
                      {"rate_arx","no_change"})
        self.assertTrue("Model-estimated" in output.iloc[-1]["source"])

    def test_90_95_bands_nest_and_widen_with_horizon(self):
        path,info=build_public_horizon(self.public)
        for _,r in path[path["series"]=="Baseline"].iterrows():
            for metric in ("nim_pct","nii_m"):
                self.assertLess(r[f"{metric}_low_95"],r[f"{metric}_low_90"])
                self.assertLess(r[f"{metric}_low_90"],r[metric])
                self.assertLess(r[metric],r[f"{metric}_high_90"])
                self.assertLess(r[f"{metric}_high_90"],r[f"{metric}_high_95"])
        self.assertAlmostEqual(CRITICAL_VALUES[90],1.64485362695)
        self.assertAlmostEqual(CRITICAL_VALUES[95],1.95996398454)
        for key in ("nim_bps","nii_m"):
            self.assertEqual(len(info["diagnostics"][key]["horizons"]),4)
            self.assertGreaterEqual(
                min(x["backtest_count"] for x in info["diagnostics"][key]["horizons"]),5
            )

    def test_source_data_untouched_and_fy_nii_has_2_actual_2_estimates(self):
        unchanged=self.public.copy(deep=True)
        output,info=build_public_horizon(self.public)
        pd.testing.assert_frame_equal(self.public,unchanged)
        full_actual=self.public[self.public["date"].dt.year==2026]["nii_m"].sum()
        forecast_2026=output[(output["series"]=="Baseline")&
                             (output["date"].dt.year==2026)]["nii_m"].sum()
        self.assertAlmostEqual(info["fy_nii_actual_m"],full_actual)
        self.assertAlmostEqual(info["fy_nii_projected_m"],forecast_2026)
        self.assertAlmostEqual(info["fy_nii_m"],full_actual+forecast_2026)

    def test_scenario_is_explicit_and_rate_sensitive_only_when_enabled(self):
        reference,_=build_public_horizon(self.public,model_preference="rate_arx")
        shocked,_=build_public_horizon(
            self.public,model_preference="rate_arx",rate_shock_bps=100.0
        )
        # ARX lag uses rate change known at origin; Q3 forecast doesn't know
        # next-quarter ECB change. Later quarters may respond to the shock.
        self.assertAlmostEqual(reference.iloc[22]["nim_bps"],shocked.iloc[22]["nim_bps"])
        self.assertAlmostEqual(reference.iloc[22]["nii_m"],shocked.iloc[22]["nii_m"])
        naive,_=build_public_horizon(self.public,model_preference="no_change")
        naive_shock,_=build_public_horizon(
            self.public,model_preference="no_change",rate_shock_bps=100.0
        )
        self.assertAlmostEqual(naive.iloc[-1]["nim_bps"],naive_shock.iloc[-1]["nim_bps"])
        self.assertAlmostEqual(naive.iloc[-1]["nii_m"],naive_shock.iloc[-1]["nii_m"])
        manual,_=build_public_horizon(
            self.public,model_preference="no_change",
            nim_overlay_bps=1.5,nii_overlay_pct=2.0
        )
        self.assertAlmostEqual(manual.iloc[22]["nim_bps"]-naive.iloc[22]["nim_bps"],1.5)
        self.assertAlmostEqual(manual.iloc[22]["nii_m"]/naive.iloc[22]["nii_m"],1.02)

    def test_risky_assumptions_fail_closed(self):
        for arg in (
            {"rate_shock_bps":101.0},
            {"nim_overlay_bps":-20.0},
            {"nii_overlay_pct":float("nan")},
            {"quarters_ahead":9},
            {"model_preference":"unknown"},
        ):
            with self.assertRaises(ValueError):
                build_public_horizon(self.public,**arg)

    def test_altair_chart_has_6_layers_when_both_bands(self):
        trajectory,diag=build_public_horizon(self.public)
        both=_forecast_chart(trajectory,metric="nim_pct",history_points=12,bands="Both")
        self.assertEqual(len(both.to_dict()["layer"]),6)
        off=_forecast_chart(trajectory,metric="nii_m",history_points=22,bands="Off")
        self.assertEqual(len(off.to_dict()["layer"]),4)

    def test_real_data_is_isolated_from_synthetic_code(self):
        actual=Path("src/reported_horizon.py").read_text(encoding="utf-8")
        self.assertIn("from src.public_horizon_engine import",actual)
        self.assertNotIn("src.engines",actual)
        self.assertIn("90%",actual)
        self.assertIn("95%",actual)
        self.assertIn("font-size:clamp(1.66rem,2.38vw,2.40rem)",actual)
        original=Path("src/modules/horizon.py").read_text(encoding="utf-8")
        self.assertIn("def render_horizon(s)",original)
        self.assertIn("from src.reported_horizon import render_reported_horizon",
                      Path("src/real_data_mode.py").read_text(encoding="utf-8"))


if __name__=="__main__":
    unittest.main()
