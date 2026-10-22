"""Public-factsheet grounded, unrestricted-topic Real Copilot checks."""
from pathlib import Path
import unittest
from unittest.mock import patch

from src.real_data_mode import build_reported_state
from src.reported_copilot_evidence import build_reported_evidence
from src.reported_copilot_partner import (
    answer_reported_question, build_real_financial_prompt, build_cet1_bridge
)


class GeneralReportedQuestions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.group=build_reported_state()
        cls.packet=build_reported_evidence(cls.group,"All reported metrics")

    def test_full_group_packet_uses_only_sourced_24_metrics(self):
        packet=self.packet
        self.assertTrue(packet["llm_enabled"])
        self.assertEqual(len(packet["metrics"]),24)
        self.assertEqual(len(packet["quarterly_history"]),10)
        self.assertEqual(len(packet["group_nii_nim_history_2021"]),22)
        self.assertEqual(len(packet["segment_history"]),28)
        self.assertEqual(packet["as_of"],"Q2 2026")
        self.assertEqual(packet["group_nii_nim_history_2021"][0]["quarter"],"Q1 2021")
        self.assertAlmostEqual(
            packet["group_nii_nim_history_2021"][0]["nii_m"],1362.917019,places=6
        )
        self.assertIn("49/49",packet["history_2021_source"])
        self.assertIn("data/abn_quarterly.csv",packet["source"])
        for r in packet["group_nii_nim_history_2021"]:
            self.assertTrue(r["source_url"].startswith("https://assets.ctfassets.net/"))
        # Balance-sheet observations are absent before Q4 2024. Do not fill them.
        self.assertIsNone(packet["quarterly_history"][0]["values"]["rwa_m"])

    def test_open_ended_questions_about_profitability_and_liquidity(self):
        for question,field in (
            ("What happened to net profit in 2024?","net_profit_m"),
            ("What was the trend in NIM between 2022 and 2023?","nim_bps"),
            ("What are the reported LCR and NSFR ratios?","lcr_pct"),
            ("What were the latest customer deposits?","deposits_m"),
            ("Compare Corporate Banking and Wealth Management loans.","business_line"),
        ):
            prompt=build_real_financial_prompt(question,self.packet)
            self.assertIn(question,prompt)
            self.assertIn(field,prompt)
            self.assertIn("only state bank-specific facts",prompt.lower())
            self.assertIn("UNTRUSTED PRIOR CONVERSATION",prompt)

    def test_existing_gateway_one_call_on_non_cet1_question(self):
        previous=[{"role":"user","content":"What happened to NII in 2022?"},
                  {"role":"assistant","content":"Previous model response, untrusted."}]
        with patch("src.reported_copilot_partner.generate_prompt_response",
                   return_value="Based on reported NII, more evidence is needed.") as gateway:
            response=answer_reported_question(
                "What about 2023?",self.packet,history=previous)
        gateway.assert_called_once()
        prompt=gateway.call_args.args[0]
        self.assertIn("What about 2023?",prompt)
        self.assertIn("Previous model response, untrusted.",prompt)
        self.assertIn('"group_nii_nim_history_2021"',prompt)
        self.assertFalse(response["used_genie"])
        self.assertEqual(response["mode"],"real")

    def test_cet1_arithmetic_guard_preserved_in_full_packet(self):
        bridge=build_cet1_bridge(self.packet)
        self.assertAlmostEqual(
            bridge["capital_component_pp"]+bridge["rwa_component_pp"],
            bridge["reported_delta_pp"],places=6
        )

    def test_scope_restrictions_and_missing_data_rule(self):
        segment=build_reported_state("Wealth Management")
        evidence=build_reported_evidence(segment,"All reported metrics")
        self.assertNotIn("group_nii_nim_history_2021",evidence)
        self.assertNotIn("segment_history",evidence)
        self.assertEqual(len(evidence["metrics"]),3)
        prompt=build_real_financial_prompt("What was Wealth Management NIM?",evidence)
        self.assertIn("Explicit null values mean NOT DISCLOSED",prompt)
        self.assertNotIn('"nim_bps":',prompt)
        with self.assertRaises(ValueError):
            build_cet1_bridge(evidence)

    def test_unsupported_questions_are_allowed_but_source_constrained(self):
        prompt=build_real_financial_prompt(
            "What will CET1 be if credit losses double?",self.packet
        )
        self.assertIn("forward-looking financial forecasts",prompt)
        self.assertIn("never",prompt.lower())
        for question in ("", "x"*1201):
            with self.assertRaises(ValueError):
                build_real_financial_prompt(question,self.packet)

    def test_layout_scrolling_siblings_and_central_radial_intact(self):
        floating=Path("src/reported_copilot_balloon.py").read_text("utf-8")
        self.assertIn("cfo-thread-history-marker",floating)
        self.assertIn("jarvis-history-marker",floating)
        self.assertIn('with st.form("jarvis_composer_form"',floating)
        self.assertIn('with st.form("real_cfo_chat_form_"+str(compact)',floating)
        self.assertIn('width:min(560px',floating)
        self.assertIn('height:min(800px',floating)
        self.assertIn('answer_reported_question(question,evidence,history=previous)',floating)
        self.assertNotIn('st.container(key=',floating)
        central=Path("src/reported_copilot.py").read_text("utf-8")
        self.assertIn('topic_names=["All reported metrics"]',central)
        app=Path("main.py").read_text("utf-8")
        self.assertIn('Ask CFO<br>Copilot',app)
        self.assertIn('href="{module_url(\'copilot\')}"',app)


if __name__=="__main__":
    unittest.main()
