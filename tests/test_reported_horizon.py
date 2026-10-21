"""Grounded quarterly Horizon engine/regression tests; no ABN Databricks required."""
import math
import unittest
from pathlib import Path

import pandas as pd

from src.real_data_mode import load_reported
from src.reported_horizon_engine import (
    CAPS, FORECAST_QUARTERS, default_quarterly_assumptions,
    build_quarterly_horizon, _observed_median,
)
from src.reported_horizon import _forecast_chart, _lens


class ReportedHorizonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.group, cls.segments = load_reported()

    def test_horizon_defaults_use_observed_quarterly_medians(self):
        default = default_quarterly_assumptions(self.group)
        self.assertEqual(default["nim_decay"], .5)
        for key in CAPS:
            self.assertGreaterEqual(default[key], CAPS[key][0])
            self.assertLessEqual(default[key], CAPS[key][1])
        expected_nim = self.group["nim_bps"].diff().dropna().tail(3).median()
        self.assertAlmostEqual(
            default["nim_change_bps"],
            round(float(expected_nim), 3), places=3
        )
        self.assertAlmostEqual(
            _observed_median(self.group, "loans_m"),
            self.group["loans_m"].dropna().pct_change().dropna().tail(3).median() * 100,
        )

    def test_history_and_forecast_have_true_quarter_ends_and_provenance(self):
        path, summary = build_quarterly_horizon(
            self.group, default_quarterly_assumptions(self.group)
        )
        self.assertEqual(len(path), len(self.group) + FORECAST_QUARTERS)
        self.assertEqual((path["series"]=="Actual").sum(), 10)
        self.assertEqual((path["series"]=="Baseline").sum(), 4)
        self.assertEqual(path.iloc[9]["quarter"], "Q2 2026")
        self.assertEqual(path.iloc[10]["quarter"], "Q3 2026")
        self.assertEqual(path.iloc[11]["date"], pd.Timestamp("2026-12-31"))
        self.assertEqual(path.iloc[-1]["quarter"], "Q2 2027")
        self.assertEqual(summary["year_end_quarter"], "Q4 2026")
        self.assertEqual(summary["year_end_kind"], "Illustrative baseline")
        self.assertEqual(path.iloc[9]["source"], "ABN AMRO Q2 2026 factsheet")
        self.assertEqual(path.iloc[10]["source"], "Illustrative, assumption-driven calculation")
        self.assertAlmostEqual(path.iloc[9]["nim_bps"], 148.750189170)

    def test_full_year_nii_is_booked_first_half_plus_two_assumed_quarters(self):
        params = {
            "nim_change_bps": 0.0, "nim_decay": 0.5,
            "nii_growth_pct": 0.0, "loan_growth_pct": 0.0, "deposit_growth_pct": 0.0,
        }
        path, summary = build_quarterly_horizon(self.group, params)
        q1, q2 = self.group.iloc[-2], self.group.iloc[-1]
        expected = q1["nii_m"] + q2["nii_m"] * 3.0
        self.assertAlmostEqual(summary["fy_nii_m"], expected)
        self.assertAlmostEqual(
            summary["fy_nii_actual_m"], float(q1["nii_m"] + q2["nii_m"])
        )
        self.assertAlmostEqual(summary["fy_nii_projected_m"], 2 * float(q2["nii_m"]))
        self.assertAlmostEqual(summary["year_end_nim_pct"], float(q2["nim_bps"]) / 100)
        self.assertAlmostEqual(path.iloc[-1]["loans_m"], float(q2["loans_m"]))
        self.assertAlmostEqual(path.iloc[-1]["deposits_m"], float(q2["deposits_m"]))

    def test_nim_decay_is_quarterly_and_not_conflated_with_nii(self):
        assumptions = {
            "nim_change_bps": 8.0, "nim_decay": 0.5,
            "nii_growth_pct": 0.0, "loan_growth_pct": 0.0, "deposit_growth_pct": 0.0,
        }
        path, info = build_quarterly_horizon(self.group, assumptions)
        actual_nim = float(self.group.iloc[-1]["nim_bps"])
        forecast = path[path["series"]=="Baseline"]
        self.assertAlmostEqual(float(forecast.iloc[0]["nim_bps"]),actual_nim+8)
        self.assertAlmostEqual(float(forecast.iloc[1]["nim_bps"]),actual_nim+12)
        self.assertAlmostEqual(float(forecast.iloc[3]["nim_bps"]),actual_nim+15)
        self.assertAlmostEqual(info["first_quarter_nim_step_bps"],8)
        self.assertTrue((forecast["nii_m"] == float(self.group.iloc[-1]["nii_m"])).all())
        change = dict(assumptions, nim_change_bps=-8.0)
        second, _ = build_quarterly_horizon(self.group, change)
        self.assertNotAlmostEqual(
            float(second.iloc[-1]["nim_pct"]),float(path.iloc[-1]["nim_pct"])
        )
        self.assertAlmostEqual(
            float(second.iloc[-1]["nii_m"]),float(path.iloc[-1]["nii_m"])
        )

    def test_nonzero_nii_volume_growth_keeps_factual_start(self):
        a = {
            "nim_change_bps": 0, "nim_decay": .5, "nii_growth_pct": 1.5,
            "loan_growth_pct": 2.0, "deposit_growth_pct": -1.0,
        }
        result, _ = build_quarterly_horizon(self.group,a)
        final = self.group.iloc[-1]
        self.assertAlmostEqual(
            result.iloc[10]["nii_m"],final["nii_m"]*1.015
        )
        self.assertAlmostEqual(
            result.iloc[10]["loans_m"],final["loans_m"]*1.02
        )
        self.assertAlmostEqual(
            result.iloc[10]["deposits_m"],final["deposits_m"]*.99
        )
        self.assertAlmostEqual(
            result.iloc[9]["loans_m"],final["loans_m"]
        )

    def test_invalid_assumptions_and_missing_sources_fail_closed(self):
        a=default_quarterly_assumptions(self.group)
        for x in [-41.0,41.0,float("nan")]:
            with self.assertRaises(ValueError):
                build_quarterly_horizon(self.group,dict(a,nim_change_bps=x))
        with self.assertRaises(ValueError):
            build_quarterly_horizon(self.group,dict(a, nim_decay=2))
        with self.assertRaises(ValueError):
            build_quarterly_horizon(self.group.drop(columns=["nii_m"]),a)
        with self.assertRaises(ValueError):
            build_quarterly_horizon(self.group.iloc[:-1].copy().assign(loans_m=float("nan")),a)

    def test_existing_chart_style_and_explanatory_disclaimer(self):
        a=default_quarterly_assumptions(self.group)
        path, summary = build_quarterly_horizon(self.group,a)
        chart = _forecast_chart(path,metric="nim_pct")
        spec=chart.to_dict()
        self.assertEqual(len(spec["layer"]),4)
        text = _lens(path,summary)
        self.assertIn("No calibrated statistical confidence",text)
        self.assertIn("not contained in the source package",text)
        self.assertIn("reported NIM", text)
        source = Path("src/reported_horizon.py").read_text(encoding="utf-8")
        self.assertIn("Where are we heading?",source)
        self.assertIn("Forward trajectory / actual",source)
        self.assertIn("Balance-sheet run-rate",source)
        self.assertIn("from src.reported_horizon import render_reported_horizon",
                      Path("src/real_data_mode.py").read_text(encoding="utf-8"))
        synthetic=Path("src/modules/horizon.py").read_text(encoding="utf-8")
        self.assertIn("def render_horizon(s)",synthetic)


if __name__ == "__main__":
    unittest.main()
