"""Live Real Data CET1 prompt routing and source guardrails; no network calls."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.real_data_mode import build_reported_state
from src.reported_copilot_evidence import (
    build_reported_evidence, GROUP_TOPICS, SEGMENT_TOPICS
)
from src.reported_copilot_partner import (
    DEFAULT_QUESTION, build_cet1_bridge,
    build_real_capital_prompt, answer_reported_cet1,
)


class ReportedCopilotEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.group = build_reported_state()
        cls.segment = build_reported_state("Wealth Management")
        cls.capital = build_reported_evidence(cls.group, "Capital")

    def test_group_capital_matches_actual_source_rows(self):
        packet=self.capital
        self.assertEqual(packet["data_mode"],"real")
        self.assertEqual(packet["as_of"],"Q2 2026")
        self.assertTrue(packet["llm_enabled"])
        self.assertEqual(packet["scope"],"ABN AMRO Group")
        self.assertEqual(len(packet["metrics"]),3)
        for m in packet["metrics"]:
            key=m["field"]
            latest=self.group.reported_group.iloc[-1]
            previous=self.group.reported_group.iloc[-2]
            self.assertAlmostEqual(m["latest"],float(latest[key]))
            self.assertAlmostEqual(m["previous"],float(previous[key]))
            self.assertAlmostEqual(m["delta"],float(latest[key]-previous[key]))
            self.assertEqual(m["latest_quarter"],"Q2 2026")
            self.assertEqual(m["previous_quarter"],"Q1 2026")
            self.assertIn("data/abn_quarterly.csv",m["provenance"])

    def test_cet1_ratio_bridge_reconciles_both_periods_exactly(self):
        b=build_cet1_bridge(self.capital)
        self.assertAlmostEqual(b["latest_ratio_pct"],15.859229928,places=6)
        self.assertAlmostEqual(b["previous_ratio_pct"],15.542293272,places=6)
        self.assertAlmostEqual(b["capital_delta_eur_m"],410.657,places=5)
        self.assertAlmostEqual(b["rwa_delta_eur_m"],-139.820541,places=5)
        self.assertAlmostEqual(
            b["reported_delta_pp"],
            b["capital_component_pp"]+b["rwa_component_pp"],places=5,
        )
        self.assertGreater(b["capital_component_pp"],0)
        self.assertGreater(b["rwa_component_pp"],0)
        self.assertIn("NOT causal",b["calculation_type"])

    def test_prompt_has_real_not_synthetic_numbers_and_requires_grounding(self):
        prompt=build_real_capital_prompt(DEFAULT_QUESTION,self.capital)
        self.assertIn("ABN AMRO Q2 2026 factsheet",prompt)
        self.assertIn("**Why — observed arithmetic**",prompt)
        self.assertIn("**Impact — reported movement**",prompt)
        self.assertIn("**Next — missing evidence**",prompt)
        self.assertIn("410.657",prompt)
        self.assertIn("capital_component_pp",prompt)
        self.assertIn("NOT the",prompt)
        self.assertIn("underlying BUSINESS CAUSES",prompt)
        self.assertNotIn("monthly_changes",prompt)

    def test_gateway_used_once_via_existing_generate_prompt_response(self):
        with patch("src.reported_copilot_partner.generate_prompt_response",
                   return_value="**Why — observed arithmetic** Source-backed response") as mocked:
            result=answer_reported_cet1(DEFAULT_QUESTION,self.capital)
        mocked.assert_called_once()
        sent=mocked.call_args.args[0]
        self.assertIn("CFO QUESTION:",sent)
        self.assertIn("CET1",sent)
        self.assertFalse(result["used_genie"])
        self.assertEqual(result["mode"],"real")
        self.assertIn("AI-generated",result["model_status"])
        self.assertIn("capital_component_pp",str(result["bridge"]))

    def test_no_synthetic_fallback_for_failed_or_empty_gateway(self):
        with patch("src.reported_copilot_partner.generate_prompt_response",
                   side_effect=RuntimeError("offline")):
            with self.assertRaisesRegex(RuntimeError,"offline"):
                answer_reported_cet1(DEFAULT_QUESTION,self.capital)
        with patch("src.reported_copilot_partner.generate_prompt_response",return_value=""):
            with self.assertRaisesRegex(RuntimeError,"empty"):
                answer_reported_cet1(DEFAULT_QUESTION,self.capital)

    def test_profitability_remains_preview_only(self):
        packet=build_reported_evidence(self.group,"Profitability")
        self.assertTrue(packet["llm_enabled"])
        fields={m["field"]:m for m in packet["metrics"]}
        self.assertIn("nii_m",fields)
        self.assertIn("nim_bps",fields)
        self.assertIn("net_profit_m",fields)
        self.assertIn("A quarter-to-quarter movement alone does not establish why",
                      packet["notes"][1])
        with self.assertRaises(ValueError):
            build_cet1_bridge(packet)

    def test_segment_never_sends_group_capital_to_gateway(self):
        packet=build_reported_evidence(self.segment,"Balance sheet")
        self.assertTrue(packet["llm_enabled"])
        self.assertEqual(packet["scope"],"Wealth Management")
        self.assertEqual(
            [m["field"] for m in packet["metrics"]],
            ["loans_m","deposits_m","rwa_m"],
        )
        self.assertIn("data/abn_segments_quarterly.csv",packet["source"])
        with self.assertRaises(ValueError):
            build_reported_evidence(self.segment,"Capital")
        with self.assertRaises(ValueError):
            build_cet1_bridge(packet)

    def test_missing_metric_invalid_state_and_tampered_ratio_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"reported-data"):
            build_reported_evidence(SimpleNamespace(is_reported=False),"Capital")
        with self.assertRaises(ValueError):
            build_reported_evidence(self.group,"Unsupported")
        for q in ("", "x"*801):
            with self.assertRaises(ValueError):
                build_real_capital_prompt(q,self.capital)
        tampered={**self.capital,"metrics":[dict(m) for m in self.capital["metrics"]]}
        tampered["metrics"][0]["latest"]=50
        with self.assertRaisesRegex(ValueError,"inconsistent"):
            build_cet1_bridge(tampered)

    def test_real_copilot_uses_shared_balloon_chat_and_no_genie(self):
        view=Path("src/reported_copilot.py").read_text(encoding="utf-8")
        balloon=Path("src/reported_copilot_balloon.py").read_text(encoding="utf-8")
        self.assertIn("render_cet1_chat(evidence, compact=False)",view)
        self.assertIn("answer_reported_question",balloon)
        self.assertIn("real_cfo_cet1_messages",balloon)
        self.assertNotIn('st.container(key=',balloon)
        self.assertIn('jarvis-root-marker',balloon)
        self.assertIn('st.button("✦ Jarvis"',balloon)
        self.assertIn('st.button("✕"',balloon)
        self.assertNotIn('st.popover(',balloon)
        self.assertNotIn("from src.modules.copilot",balloon)
        self.assertNotIn("answer_data_question",balloon)
        partner=Path("src/reported_copilot_partner.py").read_text(encoding="utf-8")
        self.assertIn("from src.openai_partner import generate_prompt_response",partner)
        self.assertNotIn("genie_partner",partner)
        self.assertNotIn("requests.post",partner)
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
