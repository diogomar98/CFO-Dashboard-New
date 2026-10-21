"""Regression tests for the optional factsheet reporting mode.

Run from repository root: python -m unittest discover -s tests -p test_dual_mode.py
"""
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src import hud
from src.real_data_mode import build_reported_state, load_reported


class ReportedDataTests(unittest.TestCase):
    def test_data_coverage_and_key_reported_values(self):
        group, segments = load_reported()
        self.assertEqual(len(group), 10)
        self.assertEqual(segments["date"].nunique(), 7)
        self.assertEqual(len(segments), 28)
        self.assertEqual(pd.Timestamp(group.iloc[-1]["date"]), pd.Timestamp("2026-06-30"))
        latest = group.iloc[-1]
        self.assertAlmostEqual(latest["net_profit_m"], 780.531615084, places=5)
        self.assertAlmostEqual(latest["nii_m"], 1699.854335362, places=5)
        self.assertAlmostEqual(latest["cet1_ratio_pct"], 15.859229928, places=5)
        self.assertAlmostEqual(latest["lcr_pct"], 158.6, places=3)
        self.assertEqual(group["loans_m"].notna().sum(), 7)

    def test_segment_totals_reconcile_to_consolidated(self):
        group, segments = load_reported()
        for metric in ("loans_m", "deposits_m", "rwa_m"):
            values = segments.groupby("date")[metric].sum()
            published = group.set_index("date")[metric].reindex(values.index)
            self.assertTrue(((values - published).abs() < 0.01).all(), metric)

    def test_real_group_has_reported_cards_not_synthetic_signals(self):
        state = build_reported_state()
        self.assertTrue(state.is_reported)
        self.assertEqual(len(state.kpi_cards), 4)
        self.assertEqual(state.close_date, "30 Jun 2026")
        self.assertAlmostEqual(state.cert_current_nim, 1.4875018917, places=5)
        for card in state.kpi_cards:
            self.assertEqual(card["delta_label"], "QoQ")
            self.assertEqual(card["rag"]["status"], "NOT_ASSESSED")
        self.assertEqual(state.ratings["treasury_rate50"]["status"], "UNAVAILABLE")

    def test_business_line_is_source_reported(self):
        state = build_reported_state("Wealth Management")
        self.assertEqual(len(state.kpi_cards), 4)
        self.assertEqual(state.kpi_cards[0]["label"], "CUSTOMER LOANS")
        _, segments = load_reported()
        latest_wm = segments[
            (segments["date"] == pd.Timestamp("2026-06-30"))
            & (segments["business_line"] == "Wealth Management")
        ].iloc[0]
        self.assertIn(f"{latest_wm['loans_m']:,.0f}", state.kpi_cards[0]["value"])

    def test_navigation_retains_mode(self):
        with patch("src.hud.get_query_value", side_effect=lambda key, default="": {
            "mode": "real", "bl": "pbb", "module": "home"
        }.get(key, default)):
            self.assertEqual(hud.get_data_mode(), "real")
            self.assertEqual(hud.module_url("brief"), "?module=brief&bl=pbb&mode=real")
            self.assertEqual(hud.bl_url("Wealth Management"), "?enter=1&bl=wm&mode=real")
            self.assertEqual(hud.mode_url("synthetic"), "?enter=1&bl=pbb")
            self.assertEqual(hud.mode_url("real"), "?enter=1&bl=pbb&mode=real")
        with patch("src.hud.get_query_value", return_value=""):
            self.assertEqual(hud.get_data_mode(), "synthetic")

    def test_original_entry_point_keeps_synthetic_path(self):
        main = Path(__file__).resolve().parents[1].joinpath("main.py").read_text()
        self.assertIn("s = build_state(business_line=selected_bl)", main)
        self.assertIn("RENDERERS[module](s)", main)
        self.assertIn("s = build_reported_state(business_line=selected_bl)", main)
        self.assertNotIn("if render_reported_dashboard()", main)


if __name__ == "__main__":
    unittest.main()
