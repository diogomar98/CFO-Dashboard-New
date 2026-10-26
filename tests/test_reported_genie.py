"""Real Genie Agent isolation, source security and UC setup regression tests.

All Genie test responses are in-memory stubs. No ABN network, SQL warehouse,
Synethic agent or production reporting objects are contacted.
"""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

import pandas as pd

from src.reported_genie_partner import (
    MAX_RETURNED_ROWS, _validate_question, _extract_verified_sql,
    _genie_external_rows,
    real_genie_space_id, real_genie_configured,
    ask_real_genie, answer_real_genie_question,
)


class RealGenieIsolationTests(unittest.TestCase):
    def test_requires_distinct_real_space_env_and_never_uses_synthetic_mock(self):
        with patch.dict(os.environ,{"GENIE_SPACE_ID":"synthetic-space"},clear=True):
            self.assertFalse(real_genie_configured())
            self.assertEqual(real_genie_space_id(),"")
            with self.assertRaisesRegex(RuntimeError,"REAL_GENIE_SPACE_ID"):
                ask_real_genie("What is Group NII?")
        with patch.dict(os.environ,{
            "GENIE_SPACE_ID":"synthetic-space",
            "REAL_GENIE_SPACE_ID":"real-space",
        },clear=True):
            self.assertTrue(real_genie_configured())
            self.assertEqual(real_genie_space_id(),"real-space")
        with patch.dict(os.environ,{
            "GENIE_SPACE_ID":"synthetic-space",
            "REAL_GENIE_SPACE_ID":"synthetic-space",
        },clear=True):
            self.assertFalse(real_genie_configured())
            self.assertEqual(real_genie_space_id(),"")

    def test_question_is_bounded_and_nonempty(self):
        for q in ("","  ","a"*1201,None):
            with self.assertRaises(ValueError):
                _validate_question(q)
        self.assertEqual(_validate_question("  What is Group ROE?  "),"What is Group ROE?")

    def test_sql_guard_rejects_write_queries_and_accepts_select(self):
        # Patch only the Synthetic helper used for extracting an attachment.
        attachment=lambda sql:SimpleNamespace(
            query=SimpleNamespace(query=sql),
        )
        fake=SimpleNamespace(
            _extract_query_attachment=lambda msg:msg,
        )
        with patch.dict(sys.modules,{"src.genie_partner":fake}):
            sql,_=_extract_verified_sql(attachment(
                "SELECT date, net_profit_m FROM cfo_group_quarterly"
            ))
            self.assertIn("net_profit_m",sql)
            sql,_=_extract_verified_sql(attachment(
                "WITH last_q AS (SELECT MAX(date) AS date FROM t) "
                "SELECT date FROM last_q"
            ))
            self.assertTrue(sql.startswith("WITH"))
            for unsafe in (
                "DROP TABLE cfo_group_quarterly",
                "DELETE FROM cfo_group_quarterly",
                "UPDATE cfo_group_quarterly SET nii_m=0",
                "SELECT * FROM t; ALTER TABLE t DROP COLUMN a",
            ):
                with self.assertRaises(ValueError):
                    _extract_verified_sql(attachment(unsafe))

    def test_sdk_space_id_and_conversation_are_real_only(self):
        calls=[]
        class Genie:
            def start_conversation_and_wait(self,**kw):
                calls.append(("start",kw))
                return SimpleNamespace(
                    status="COMPLETED",attachments=[],
                    content="Four quarterly observations",
                    conversation_id="real-conversation-1",
                )
            def create_message_and_wait(self,**kw):
                calls.append(("continue",kw))
                return SimpleNamespace(
                    status="COMPLETED",attachments=[],
                    content="Follow-up observations",
                    conversation_id="real-conversation-1",
                )
        fake_sdk=SimpleNamespace(
            _extract_answer_text=lambda msg:msg.content,
            _extract_query_attachment=lambda msg:None,
            _fetch_query_result=lambda *a,**kw:None,
            _get_client=lambda:None,
            _msg_attr=lambda obj,*names:next(
                (getattr(obj,n) for n in names if getattr(obj,n,None)),None
            ),
            _rows_to_dataframe=lambda obj:pd.DataFrame(),
        )
        client=SimpleNamespace(genie=Genie())
        with patch.dict(sys.modules,{"src.genie_partner":fake_sdk}):
            initial=ask_real_genie(
                "How did Group net profit change?",space_id="approved-real-id",
                client=client,
            )
            followup=ask_real_genie(
                "What about the prior quarter?",space_id="approved-real-id",
                client=client,conversation_id=initial["conversation_id"],
            )
            scoped=ask_real_genie(
                "What are the latest loans?",space_id="approved-real-id",
                scope="Wealth Management",client=client,
            )
        self.assertEqual([c[0] for c in calls],["start","continue","start"])
        self.assertTrue(all(c[1]["space_id"]=="approved-real-id" for c in calls))
        self.assertEqual(calls[1][1]["conversation_id"],"real-conversation-1")
        self.assertIn("Wealth Management",calls[2][1]["content"])
        self.assertIn("filter",calls[2][1]["content"])
        self.assertTrue(all(c.get("used_genie") for c in (initial,followup,scoped)))
        self.assertTrue(all(c["data_mode"]=="real" for c in (initial,followup,scoped)))
        self.assertNotIn("Synthetic",initial["answer_text"])

    def test_real_genie_fetches_rows_even_with_deprecated_query_result_metadata(self):
        calls=[]
        response_rows=pd.DataFrame([
            {"date":"2026-06-30","net_profit_m":781.0}
        ])
        attachment=SimpleNamespace(
            attachment_id="attachment-1",
            query=SimpleNamespace(
                query="SELECT date, net_profit_m FROM cfo_group_quarterly",
                statement_id="statement-not-attachment-id",
            ),
        )
        # The message.query_result is deprecated row-count metadata, not rows.
        message=SimpleNamespace(
            status="COMPLETED", content="Net profit reported.",
            attachments=[attachment], query_result=SimpleNamespace(row_count=1),
            conversation_id="conv-1", message_id="message-1",
        )
        class Genie:
            def start_conversation_and_wait(self, **kwargs):
                calls.append(("start",kwargs))
                return message
        def fetch(*args):
            calls.append(("fetch",args))
            return SimpleNamespace(statement_response=SimpleNamespace(
                result=SimpleNamespace(data_array=[["2026-06-30","781"]]),
            ))
        fake_sdk=SimpleNamespace(
            _extract_answer_text=lambda obj:obj.content,
            _extract_query_attachment=lambda obj:obj.attachments[0],
            _fetch_query_result=fetch,
            _get_client=lambda:None,
            _msg_attr=lambda obj,*names:next(
                (getattr(obj,n) for n in names if getattr(obj,n,None)),None
            ),
            _rows_to_dataframe=lambda obj:response_rows,
        )
        with patch.dict(sys.modules,{"src.genie_partner":fake_sdk}):
            result=ask_real_genie(
                "Q2 2026 Group net profit?",space_id="real-space",
                client=SimpleNamespace(genie=Genie()),
            )
        self.assertEqual(result["query_rows_status"],"rows_retrieved")
        self.assertTrue(result["has_rows"])
        self.assertEqual(len(result["data"]),1)
        self.assertEqual(calls[1][0],"fetch")
        self.assertEqual(calls[1][1][1:],(
            "real-space","conv-1","message-1","attachment-1",
        ))

    def test_real_genie_explains_fetch_failure_without_fake_evidence(self):
        attachment=SimpleNamespace(
            attachment_id="attachment-1",
            query=SimpleNamespace(query="SELECT net_profit_m FROM t"),
        )
        message=SimpleNamespace(
            status="COMPLETED",content="Genie said EUR 100m.",
            attachments=[attachment],conversation_id="conv-1",
            message_id="message-1",
        )
        class Genie:
            def start_conversation_and_wait(self,**kwargs):
                return message
        fake_sdk=SimpleNamespace(
            _extract_answer_text=lambda obj:obj.content,
            _extract_query_attachment=lambda obj:obj.attachments[0],
            _fetch_query_result=lambda *a,**kw:(_ for _ in ()).throw(PermissionError()),
            _get_client=lambda:None,
            _msg_attr=lambda obj,*names:next(
                (getattr(obj,n) for n in names if getattr(obj,n,None)),None
            ),
            _rows_to_dataframe=lambda obj:pd.DataFrame([{"x":1}]),
        )
        with patch.dict(sys.modules,{"src.genie_partner":fake_sdk}):
            result=ask_real_genie(
                "Net profit?",space_id="real-space",
                client=SimpleNamespace(genie=Genie()),
            )
        self.assertEqual(result["query_rows_status"],"sdk_result_failed_PermissionError")
        self.assertFalse(result["has_rows"])
        self.assertTrue(result["data"].empty)

    def test_external_genie_json_array_rows_are_retrieved_without_auth_header(self):
        payload=b'[["2026-06-30","781"]]'
        class Download:
            is_redirect=False
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def raise_for_status(self): return None
            def iter_content(self,chunk_size):
                yield payload
        calls=[]
        def download(url, **kwargs):
            calls.append((url,kwargs))
            return Download()
        response=SimpleNamespace(statement_response=SimpleNamespace(
            manifest=SimpleNamespace(
                format="JSON_ARRAY",schema=SimpleNamespace(columns=[
                    SimpleNamespace(name="date"),SimpleNamespace(name="net_profit_m"),
                ]),
            ),
            result=SimpleNamespace(external_links=[SimpleNamespace(
                external_link="https://abnresults.blob.core.windows.net/results/chunk?sig=private",
                chunk_index=0,
            )]),
        ))
        with patch("requests.get",side_effect=download):
            frame,status=_genie_external_rows(response)
        self.assertEqual(status,"external_rows_retrieved")
        self.assertEqual(frame["net_profit_m"].tolist(),["781"])
        self.assertEqual(len(calls),1)
        self.assertFalse("Authorization" in calls[0][1])
        self.assertFalse(calls[0][1]["allow_redirects"])

    def test_external_genie_rejects_unapproved_host_without_download(self):
        response=SimpleNamespace(statement_response=SimpleNamespace(
            manifest=SimpleNamespace(format="JSON_ARRAY"),
            result=SimpleNamespace(external_links=[SimpleNamespace(
                external_link="https://localhost/query?sig=secret",
                chunk_index=0,
            )]),
        ))
        with patch("requests.get") as download:
            with self.assertRaisesRegex(ValueError,"Unapproved"):
                _genie_external_rows(response)
        download.assert_not_called()

    def test_no_rows_never_manufactures_an_answer(self):
        generated=[]
        def fake_ask(question,**kwargs):
            return {
                "answer_text":"Group reported numbers unavailable.",
                "data":pd.DataFrame(),"sql":None,
                "conversation_id":"real-42","scope":"ABN AMRO Group",
                "source":"Real Genie · approved reporting tables",
            }
        answer=answer_real_genie_question(
            "What is 2023 Group CET1?",ask=fake_ask,
            generate=lambda prompt:generated.append(prompt) or "Invented",
        )
        self.assertFalse(answer["has_rows"])
        self.assertIn("no query rows",answer["answer"].lower())
        self.assertEqual(generated,[])
        self.assertTrue(answer["used_genie"])

    def test_analysis_uses_only_rows_and_no_synthetic_facts(self):
        prompts=[]
        def fake_ask(question,**kwargs):
            return {
                "answer_text":"NII in Q2 2026 is 1700 EUR millions.",
                "data":pd.DataFrame([
                    {"date":"2026-06-30","nii_m":1700.0,
                     "nim_bps":165.5,"nullable_col":float("nan")}
                ]),
                "sql":"SELECT date, nii_m, nim_bps FROM source",
                "conversation_id":"r9","scope":"ABN AMRO Group",
                "source":"Real Data Genie · UC",
            }
        answer=answer_real_genie_question(
            "Latest Group NII?",ask=fake_ask,
            generate=lambda text:prompts.append(text) or "Q2 2026 NII was EUR 1700m.",
        )
        self.assertTrue(answer["has_rows"])
        self.assertIn("1700m",answer["answer"])
        self.assertEqual(len(prompts),1)
        self.assertIn('"nii_m": 1700',prompts[0])
        self.assertIn('"nullable_col": null',prompts[0])
        self.assertIn("Never use Synthetic data",prompts[0])
        self.assertEqual(answer["sql"],"SELECT date, nii_m, nim_bps FROM source")

    def test_uc_bootstrap_exact_uploaded_csvs_and_no_replace(self):
        spec=importlib.util.spec_from_file_location(
            "real_genie_setup",Path("setup/real_genie_uc_setup.py"),
        )
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        root=Path("data")
        for name,expected in (
            ("cfo_group_quarterly",10),
            ("cfo_segment_quarterly",28),
            ("cfo_group_nii_nim_2021",22),
        ):
            frame=module._load(name,root)
            self.assertEqual(len(frame),expected)
            self.assertEqual(frame["date"].iloc[-1],"2026-06-30")
        group=module._load("cfo_group_quarterly",root)
        self.assertTrue(pd.isna(group.iloc[0]["cet1_ratio_pct"]))
        self.assertIn("business_line",module._load(
            "cfo_segment_quarterly",root
        ).columns)
        src=Path("setup/real_genie_uc_setup.py").read_text("utf-8")
        self.assertIn('source.write.mode("ignore").saveAsTable(target)', src)
        self.assertIn('spark.catalog.tableExists', src)
        self.assertNotIn('mode("errorifexists")', src)
        self.assertNotIn('mode("overwrite")',src)
        guide=Path("setup/real_genie_agent_guide.md").read_text("utf-8")
        queries=Path("setup/real_genie_trusted_queries.sql").read_text("utf-8")
        self.assertIn("REAL_GENIE_SPACE_ID",guide)
        self.assertIn("REPLACE_CATALOG.REPLACE_SCHEMA",queries)
        self.assertIn("Wealth Management",queries)

    def test_both_real_chat_paths_are_independently_gated(self):
        src=Path("src/reported_copilot_balloon.py").read_text("utf-8")
        self.assertIn("REAL_GENIE_SPACE_ID",src)
        self.assertIn('method=_answer_method(compact=True)',src)
        self.assertIn('method=_answer_method(compact=False)',src)
        self.assertIn('topic="Real Genie · "+evidence["topic"]',src)
        self.assertIn("answer_real_genie_question(",src)
        self.assertIn('thread["genie_conversation_id"]',src)
        self.assertIn("Inspect Genie SQL and retrieved source rows",src)
        self.assertIn("answer_reported_question(",src)
        synthetic=Path("src/genie_partner.py").read_text("utf-8")
        self.assertIn("def ask_genie(",synthetic)
        self.assertIn("GENIE_SPACE_ID",synthetic)
        self.assertNotIn("REAL_GENIE_SPACE_ID",synthetic)
        rui=Path("src/reported_copilot.py").read_text("utf-8")
        self.assertIn("Real Genie",rui)


if __name__=="__main__":
    unittest.main()
