"""Prove Phase-1 Copilot evidence is exclusively reported quarterly data."""
from pathlib import Path
from types import SimpleNamespace
import unittest

from src.real_data_mode import build_reported_state
from src.reported_copilot_evidence import (
    build_reported_evidence, GROUP_TOPICS, SEGMENT_TOPICS
)


class ReportedCopilotEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.group = build_reported_state()
        cls.segment = build_reported_state("Wealth Management")

    def test_group_capital_matches_actual_source_rows(self):
        packet = build_reported_evidence(self.group, "Capital")
        self.assertEqual(packet["data_mode"], "real")
        self.assertEqual(packet["as_of"], "Q2 2026")
        self.assertFalse(packet["llm_enabled"])
        self.assertEqual(packet["scope"], "ABN AMRO Group")
        self.assertEqual(len(packet["metrics"]), 3)
        for metric in packet["metrics"]:
            key = metric["field"]
            latest = self.group.reported_group.iloc[-1]
            previous = self.group.reported_group.iloc[-2]
            self.assertAlmostEqual(metric["latest"], float(latest[key]))
            self.assertAlmostEqual(metric["previous"], float(previous[key]))
            self.assertAlmostEqual(metric["delta"], float(latest[key]-previous[key]))
            self.assertEqual(metric["latest_quarter"], "Q2 2026")
            self.assertEqual(metric["previous_quarter"], "Q1 2026")
            self.assertIn("data/abn_quarterly.csv", metric["provenance"])

    def test_profitability_separates_fact_from_explanation(self):
        packet = build_reported_evidence(self.group, "Profitability")
        fields = {m["field"]:m for m in packet["metrics"]}
        self.assertIn("nii_m", fields)
        self.assertIn("nim_bps", fields)
        self.assertIn("net_profit_m", fields)
        self.assertIn("A quarter-to-quarter movement alone does not establish why", packet["notes"][1])
        self.assertNotIn("forecast", packet["kind"])
        self.assertNotIn("management threshold supplied", str(fields))

    def test_segment_is_scoped_to_disclosed_loan_deposit_rwa_fields(self):
        packet=build_reported_evidence(self.segment,"Balance sheet")
        self.assertEqual(packet["scope"],"Wealth Management")
        self.assertEqual(
            [m["field"] for m in packet["metrics"]],
            ["loans_m","deposits_m","rwa_m"],
        )
        self.assertIn("data/abn_segments_quarterly.csv",packet["source"])
        self.assertTrue(any("No segment NII" in item for item in packet["notes"]))
        with self.assertRaises(ValueError):
            build_reported_evidence(self.segment,"Capital")

    def test_invalid_or_synthetic_state_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"reported-data"):
            build_reported_evidence(SimpleNamespace(is_reported=False),"Capital")
        with self.assertRaises(ValueError):
            build_reported_evidence(self.group,"Not a source-backed topic")

    def test_copilot_phase_1_performs_no_ai_or_genie_calls(self):
        view=Path("src/reported_copilot.py").read_text(encoding="utf-8")
        for token in ("openai_partner","copilot_partner","genie_partner",
                      "generate_prompt_response","answer_data_question",
                      "requests.post","st.chat_input"):
            self.assertNotIn(token, view)
        self.assertIn("Financial inputs are not sent to any AI service",view)
        route=Path("src/real_data_mode.py").read_text(encoding="utf-8")
        self.assertIn("from src.reported_copilot import render_reported_copilot",route)
        original=Path("src/modules/copilot.py").read_text(encoding="utf-8")
        self.assertIn("def render_copilot(s)",original)

    def test_horizon_and_morning_both_have_three_headline_cards(self):
        horizon=Path("src/reported_horizon.py").read_text(encoding="utf-8")
        self.assertIn("zip(st.columns(3),cards)",horizon)
        self.assertNotIn('("Next-quarter NIM step"',horizon)
        self.assertIn('("ECB DFR · Q2 actual"',horizon)
        morning=Path("src/reported_brief.py").read_text(encoding="utf-8")
        self.assertIn("cols = st.columns(3",morning)


if __name__=="__main__":
    unittest.main()
