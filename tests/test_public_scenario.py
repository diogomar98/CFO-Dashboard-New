"""Real Data What-If and Horizon separation checks: Synthetic untouched."""
import unittest
from pathlib import Path

import pandas as pd

from src.real_data_mode import load_reported
from src.public_horizon_engine import build_public_horizon, load_public_horizon_inputs
from src.public_scenario_engine import (
    NEUTRAL_INPUTS,SCENARIO_METHODS,build_public_scenario_comparison,
)
from src.reported_scenario import _scenario_chart, _impact_narrative


class PublicScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        group,_=load_reported()
        cls.public=load_public_horizon_inputs(group)

    def test_horizon_is_always_unshocked_with_no_manual_financial_inputs(self):
        source=Path("src/reported_horizon.py").read_text(encoding="utf-8")
        self.assertNotIn("def _assumption_form(",source)
        self.assertNotIn("rh_public_scenario",source)
        self.assertNotIn("Run scenario",source)
        self.assertIn('build_public_horizon(public,model_preference="auto")',source)
        self.assertIn("Test ECB rates & management overlays in What-If",source)
        self.assertIn("90%",source)
        self.assertIn("95%",source)

    def test_zero_scenario_matches_same_model_reference(self):
        for mode in ("auto","rate_arx","no_change"):
            options=dict(NEUTRAL_INPUTS,method=mode)
            base,stress,quarterly,summary=build_public_scenario_comparison(self.public,options)
            pd.testing.assert_frame_equal(base,stress)
            self.assertTrue((quarterly[["delta_nim_bps","delta_nii_m"]].abs()<1e-9).all().all())
            self.assertAlmostEqual(summary["fy_nii_delta_m"],0)
            self.assertAlmostEqual(summary["dfr_reference_pct"],summary["dfr_stress_pct"])
            self.assertEqual(summary["model_choice"],mode)

    def test_flat_financial_benchmark_never_responds_to_dfr_shocks(self):
        for shock in (-100,-50,25,100):
            options=dict(NEUTRAL_INPUTS,method="no_change",rate_shock_bps=shock)
            base,stress,table,summary=build_public_scenario_comparison(self.public,options)
            self.assertTrue((table[["delta_nim_bps","delta_nii_m"]].abs()<1e-9).all().all())
            self.assertCountEqual(summary["flat_for"],["NIM","NII"])
            self.assertAlmostEqual(summary["dfr_stress_pct"],
                                   summary["dfr_reference_pct"]+shock/100)
            self.assertAlmostEqual(summary["fy_nii_delta_m"],0)

    def test_rate_sensitive_shock_affects_only_future_after_lag(self):
        options=dict(NEUTRAL_INPUTS,rate_shock_bps=50)
        base,stress,table,summary=build_public_scenario_comparison(self.public,options)
        self.assertEqual(table.iloc[0]["quarter"],"Q3 2026")
        self.assertEqual(table.iloc[1]["quarter"],"Q4 2026")
        self.assertAlmostEqual(table.iloc[0]["delta_nii_m"],0,places=8)
        self.assertAlmostEqual(table.iloc[0]["delta_nim_bps"],0,places=8)
        self.assertAlmostEqual(summary["dfr_stress_pct"],summary["dfr_reference_pct"]+.5)
        self.assertEqual(summary["selected_models"]["nim"],"rate_arx")
        self.assertEqual(summary["selected_models"]["nii"],"rate_arx")
        self.assertTrue(
            (table.loc[table.index[1]:,["delta_nii_m","delta_nim_bps"]].abs().max()>1e-6).any()
        )

    def test_direct_overlays_are_advanced_and_compound_quarterly(self):
        options=dict(NEUTRAL_INPUTS,method="no_change",nim_overlay_bps=-5,
                     nii_overlay_pct=2)
        base,stress,table,summary=build_public_scenario_comparison(self.public,options)
        self.assertTrue(summary["overlays_applied"])
        self.assertAlmostEqual(table.iloc[0]["delta_nim_bps"],-5,places=7)
        self.assertAlmostEqual(table.iloc[1]["delta_nim_bps"],-10,places=7)
        self.assertAlmostEqual(table.iloc[0]["scenario_nii_m"]/table.iloc[0]["base_nii_m"],1.02)
        self.assertAlmostEqual(table.iloc[1]["scenario_nii_m"]/table.iloc[1]["base_nii_m"],1.02**2)
        self.assertGreater(summary["fy_nii_delta_m"],0)

    def test_fy2026_uses_reported_q1_q2_and_projected_q3_q4(self):
        shock=dict(NEUTRAL_INPUTS,rate_shock_bps=50)
        base,stress,table,summary=build_public_scenario_comparison(self.public,shock)
        self.assertAlmostEqual(summary["fy_nii_actual_m"],
                               self.public.iloc[-2:]["nii_m"].sum(),places=5)
        self.assertAlmostEqual(summary["fy_nii_scenario_projected_m"],
                               table.iloc[:2]["scenario_nii_m"].sum(),places=5)
        self.assertAlmostEqual(summary["fy_nii_baseline_m"],
                               summary["fy_nii_actual_m"]+table.iloc[:2]["base_nii_m"].sum())
        self.assertAlmostEqual(summary["fy_nii_delta_m"],
                               table.iloc[:2]["delta_nii_m"].sum())

    def test_chart_has_three_source_distinct_series(self):
        base,stress,_,_=build_public_scenario_comparison(
            self.public,dict(NEUTRAL_INPUTS,rate_shock_bps=25))
        chart=_scenario_chart(base,stress,"nim_bps")
        self.assertEqual(len(chart.to_dict()["layer"]),3)
        chart_nii=_scenario_chart(base,stress,"nii_m")
        self.assertEqual(len(chart_nii.to_dict()["layer"]),3)

    def test_warns_appropriately_for_ecb_insensitive_method(self):
        options=dict(NEUTRAL_INPUTS,method="no_change",rate_shock_bps=25)
        _,_,table,summary=build_public_scenario_comparison(self.public,options)
        copy=" ".join(_impact_narrative(options,summary,table))
        self.assertIn("flat benchmark",copy.lower())
        self.assertIn("cannot change",copy)
        self.assertIn("No forecast financial impact",copy)
        self.assertIn("not evidence",copy)
        scenario_src=Path("src/reported_scenario.py").read_text(encoding="utf-8")
        self.assertIn("Flat financial baseline (ECB-insensitive)",scenario_src)
        self.assertIn("Advanced overrides",scenario_src)
        self.assertIn("Select ARX",scenario_src)

    def test_invalid_parameters_fail_closed(self):
        options=dict(NEUTRAL_INPUTS)
        cases=[
            dict(options,method="invented"),
            dict(options,rate_shock_bps=105),
            dict(options,nii_overlay_pct=15),
            dict(options,nim_overlay_bps=float("nan")),
        ]
        for case in cases:
            with self.assertRaises(ValueError):
                build_public_scenario_comparison(self.public,case)

    def test_real_data_route_uses_isolated_public_scenario_only(self):
        route=Path("src/real_data_mode.py").read_text(encoding="utf-8")
        self.assertIn("from src.reported_scenario import render_reported_scenario",route)
        scenario=Path("src/reported_scenario.py").read_text(encoding="utf-8")
        self.assertNotIn("src.engines",scenario)
        self.assertNotIn("src.modules.scenario",scenario)
        original=Path("src/modules/scenario.py").read_text(encoding="utf-8")
        self.assertIn("def render_scenario(s)",original)
        self.assertIn("BETA_UNCERTAINTY_PP",original)
        main=Path("main.py").read_text(encoding="utf-8")
        self.assertIn("from src.modules import MODULE_METADATA, RENDERERS",main)


if __name__=="__main__":
    unittest.main()
