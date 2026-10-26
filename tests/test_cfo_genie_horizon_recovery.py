"""Guarded Genie recovery and executive Horizon driver integration tests.

SQL calls are in-memory fakes: no bank API or warehouse is contacted.
"""
import unittest
from types import SimpleNamespace

from src.real_data_mode import load_reported
from src.reported_genie_partner import (
    _governed_sql_read_only,_requery_governed_genie_sql,
)
from src.reported_horizon_drivers import segment_driver_watchpoints
from src.reported_horizon import _lens
from src.public_horizon_engine import load_public_horizon_inputs,build_public_horizon


APPROVED_QUERY = (
    "WITH latest AS (SELECT MAX(date) AS max_date "
    "FROM `frbg3as_studio_a`.`cfo_cockpit`.`cfo_group_quarterly`) "
    "SELECT g.`date`, g.`cet1_ratio_pct` "
    "FROM `frbg3as_studio_a`.`cfo_cockpit`.`cfo_group_quarterly` AS g "
    "JOIN latest AS l ON g.`date`=l.`max_date`"
)


class RealGenieRecoveryTests(unittest.TestCase):
    def test_approved_cte_from_actual_genie_pattern(self):
        self.assertTrue(_governed_sql_read_only(APPROVED_QUERY))
        self.assertFalse(_governed_sql_read_only(
            "SELECT * FROM system.information_schema.tables"
        ))
        self.assertFalse(_governed_sql_read_only(
            "SELECT * FROM frbg3as_studio_a.cfo_cockpit.unknown"
        ))
        self.assertFalse(_governed_sql_read_only(
            APPROVED_QUERY+"; DELETE FROM t"
        ))
        self.assertFalse(_governed_sql_read_only(
            "DROP TABLE frbg3as_studio_a.cfo_cockpit.cfo_group_quarterly"
        ))

    def test_exact_genie_readonly_select_yields_verified_rows(self):
        queries=[]
        class SqlAPI:
            def execute_statement(self,**kwargs):
                queries.append(kwargs)
                return SimpleNamespace(
                    status=SimpleNamespace(state="SUCCEEDED"),
                    manifest=SimpleNamespace(schema=SimpleNamespace(columns=[
                        SimpleNamespace(name="date",type_name="DATE"),
                        SimpleNamespace(name="cet1_ratio_pct",type_name="DOUBLE"),
                    ]),total_row_count=1),
                    result=SimpleNamespace(
                        data_array=[["2026-06-30","15.859229928"]]
                    ),
                )
        rows,status=_requery_governed_genie_sql(
            SimpleNamespace(statement_execution=SqlAPI()),APPROVED_QUERY,
        )
        self.assertEqual(status,"sql_requery_verified_rows")
        self.assertAlmostEqual(rows.loc[0,"cet1_ratio_pct"],15.859229928)
        self.assertEqual(queries[0]["statement"],APPROVED_QUERY)
        self.assertEqual(queries[0]["warehouse_id"],"7405605052754358")
        self.assertEqual(queries[0]["row_limit"],50)

    def test_permissions_error_diagnostic_not_swallowed(self):
        class SqlAPI:
            def execute_statement(self,**kwargs):
                raise PermissionError("secret token would go here")
        rows,status=_requery_governed_genie_sql(
            SimpleNamespace(statement_execution=SqlAPI()),APPROVED_QUERY
        )
        self.assertTrue(rows.empty)
        self.assertEqual(status,"sql_requery_failed_PermissionError")
        self.assertNotIn("secret",status)


class HorizonDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.group,cls.segments=load_reported()

    def test_reported_watchpoints_reconcile_and_identify_segment(self):
        points=segment_driver_watchpoints(self.segments,self.group)
        self.assertEqual(len(points),3)
        self.assertEqual([x["topic"] for x in points],[
            "LENDING MOMENTUM","FUNDING WATCH","CAPITAL SENSITIVITY"
        ])
        self.assertEqual(points[0]["title"],"Corporate Banking")
        self.assertEqual(points[1]["title"],"Wealth Management")
        self.assertEqual(points[2]["title"],"Corporate Banking")
        self.assertIn("+4.68bn",points[0]["number"])
        self.assertIn("-12.08bn",points[1]["number"])
        self.assertIn("56.7%",points[2]["number"])

    def test_cannot_claim_driver_when_data_do_not_reconcile(self):
        broken=self.segments.copy()
        broken.loc[broken.index[-1],"rwa_m"]+=99
        self.assertEqual(segment_driver_watchpoints(broken,self.group),[])

    def test_forecast_panel_focuses_on_segments_not_duplicate_kpis(self):
        observed=load_public_horizon_inputs(self.group)
        path,model=build_public_horizon(observed)
        rendered=_lens(path,model,segments=self.segments,group=self.group)
        self.assertIn("Where should the CFO focus?",rendered)
        self.assertIn("Corporate Banking",rendered)
        self.assertIn("Wealth Management",rendered)
        self.assertIn("No segment-level NII/NIM is available",rendered)
        self.assertNotIn("Year-end margin outlook",rendered)
        self.assertNotIn("€6.74bn",rendered)


if __name__=="__main__":
    unittest.main()
