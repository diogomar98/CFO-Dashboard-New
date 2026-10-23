"""Real Genie result response tests; all payloads are local test objects."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import sys

import pandas as pd

from src.reported_genie_rows import decode_genie_rows
from src.reported_genie_partner import _verified_query_rows


class GenieRowsTests(unittest.TestCase):
    def test_inline_array_sdk_objects(self):
        response=SimpleNamespace(statement_response=SimpleNamespace(
            manifest=SimpleNamespace(schema=SimpleNamespace(columns=[
                SimpleNamespace(name="date",type_name="DATE"),
                SimpleNamespace(name="net_profit_m",type_name="DOUBLE"),
            ]),total_row_count=1),
            result=SimpleNamespace(data_array=[["2026-06-30","781.25"]]),
        ))
        rows,status=decode_genie_rows(response)
        self.assertEqual(status,"rows_retrieved")
        self.assertEqual(rows.iloc[0].to_dict(),{
            "date":"2026-06-30","net_profit_m":781.25
        })

    def test_typed_rows_raw_api(self):
        response={
            "statement_response":{
                "manifest":{"schema":{"columns":[
                    {"name":"date","type_name":"DATE"},
                    {"name":"net_profit_m","type_name":"DECIMAL(12,3)"},
                ]},"total_row_count":1},
                "result":{"data_typed_array":[
                    {"values":[{"str":"2026-06-30"},{"str":"781.125"}]}
                ]},
            },
        }
        rows,status=decode_genie_rows(response)
        self.assertEqual(status,"rows_retrieved")
        self.assertEqual(rows["date"].iloc[0],"2026-06-30")
        self.assertEqual(float(rows["net_profit_m"].iloc[0]),781.125)

    def test_null_values_and_absent_rows(self):
        content={"statement_response":{
            "manifest":{"schema":{"columns":[{"name":"net_profit_m"}]},
                        "total_row_count":2},
            "result":{"data_typed_array":[
                {"values":[{"str":"700.0"}]},
                {"values":[{"is_null":True}]},
            ]},
        }}
        rows,status=decode_genie_rows(content)
        self.assertEqual(status,"rows_retrieved")
        self.assertTrue(pd.isna(rows.iloc[1,0]))
        content["statement_response"]["result"]={}
        rows,status=decode_genie_rows(content)
        self.assertEqual(status,"unknown_result_format")
        self.assertTrue(rows.empty)
        content["statement_response"]["manifest"]["total_row_count"]=0
        rows,status=decode_genie_rows(content)
        self.assertEqual(status,"zero_query_rows")

    def test_never_claim_zero_if_rows_are_external(self):
        response={
            "statement_response":{
                "manifest":{"total_row_count":1},
                "result":{"external_links":[{"external_link":"https://not-a-real-link"}]},
            },
        }
        rows,status=decode_genie_rows(response)
        self.assertTrue(rows.empty)
        self.assertEqual(status,"external_links_only")

    def test_sdk_stripped_typed_rows_recovers_via_raw_api(self):
        calls=[]
        typed={
            "statement_response":{
                "manifest":{"schema":{"columns":[
                    {"name":"date","type_name":"DATE"},
                    {"name":"net_profit_m","type_name":"DOUBLE"},
                ]},"total_row_count":1},
                "result":{"data_typed_array":[
                    {"values":[{"str":"2026-06-30"},{"str":"781.25"}]}
                ]},
            },
        }
        def api_do(method,path):
            calls.append((method,path))
            return typed
        client=SimpleNamespace(api_client=SimpleNamespace(do=api_do))
        fake_sdk=SimpleNamespace(
            _fetch_query_result=lambda *a,**kw:SimpleNamespace(
                statement_response=SimpleNamespace(
                    manifest=SimpleNamespace(total_row_count=1),
                    result=SimpleNamespace(),
                ),
            ),
            _parse_rest_query_result=lambda raw:raw,
        )
        with patch.dict(sys.modules,{"src.genie_partner":fake_sdk}):
            rows,status=_verified_query_rows(
                client,"real-space","conv-1","message-1","attachment-1",
            )
        self.assertEqual(status,"rows_retrieved")
        self.assertEqual(len(rows),1)
        self.assertEqual(rows["net_profit_m"].iloc[0],781.25)
        self.assertEqual(calls[0][0],"GET")
        self.assertTrue(calls[0][1].endswith(
            "/messages/message-1/attachments/attachment-1/query-result"
        ))

    def test_reads_existing_genie_statement_by_statement_id(self):
        calls=[]
        actual=SimpleNamespace(
            status=SimpleNamespace(state="SUCCEEDED"),
            manifest=SimpleNamespace(schema=SimpleNamespace(columns=[
                SimpleNamespace(name="date",type_name="DATE"),
                SimpleNamespace(name="net_profit_m",type_name="DOUBLE"),
            ]),total_row_count=1),
            result=SimpleNamespace(data_array=[["2026-06-30","780.531615084"]]),
        )
        class Statements:
            def get_statement(self, *, statement_id):
                calls.append(statement_id)
                return actual
        db=SimpleNamespace(
            statement_execution=Statements(),
            api_client=None,
        )
        fake=SimpleNamespace(
            _fetch_query_result=lambda *args:SimpleNamespace(
                statement_response=None
            ),
        )
        with patch.dict(sys.modules,{"src.genie_partner":fake}):
            rows,status=_verified_query_rows(
                db,"real-space","conv-1","msg-1","attachment-1",
                statement_id="genie-statement-id",
            )
        self.assertEqual(status,"sql_statement_rows_retrieved")
        self.assertEqual(calls,["genie-statement-id"])
        self.assertEqual(rows.iloc[0]["date"],"2026-06-30")
        self.assertAlmostEqual(rows.iloc[0]["net_profit_m"],780.531615084)

    def test_sql_scope_error_is_explicit_without_faking_rows(self):
        class Statements:
            def get_statement(self, *, statement_id):
                raise PermissionError("Sensitive authorization message")
        db=SimpleNamespace(
            statement_execution=Statements(),
            api_client=None,
        )
        fake=SimpleNamespace(
            _fetch_query_result=lambda *args:SimpleNamespace(
                statement_response=None
            ),
        )
        with patch.dict(sys.modules,{"src.genie_partner":fake}):
            rows,status=_verified_query_rows(
                db,"real-space","conv-1","msg-1","attachment-1",
                statement_id="genie-statement-id",
            )
        self.assertTrue(rows.empty)
        self.assertEqual(status,"sql_statement_fetch_failed_PermissionError")
        self.assertNotIn("Sensitive",status)

    def test_limited_to_fifty_rows(self):
        response={"statement_response":{
            "manifest":{"schema":{"columns":[{"name":"amount"}]},
                        "total_row_count":100},
            "result":{"data_array":[[str(i)] for i in range(100)]}
        }}
        rows,status=decode_genie_rows(response,max_rows=50)
        self.assertEqual(status,"rows_retrieved")
        self.assertEqual(len(rows),50)


if __name__=="__main__":
    unittest.main()
