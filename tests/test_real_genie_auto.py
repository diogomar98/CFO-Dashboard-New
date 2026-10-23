"""Tests for the no-code ABN Real Genie bootstrap. No Databricks connections."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from setup.real_genie_auto import (
    CATALOG, SCHEMA, TABLES, TITLE, WAREHOUSE_ID, EXPECTED_ROWS,
    genie_serialized_space, trusted_sql_examples, create_or_reuse_agent,
    validate_existing_tables,
)

ROOT = Path(__file__).resolve().parents[1]


class RealGenieAutoTests(unittest.TestCase):
    def test_approved_catalog_schema_and_exact_tables(self):
        self.assertEqual((CATALOG, SCHEMA),
                         ("frbg3s_studio_a", "cfo_cockpit"))
        self.assertEqual(WAREHOUSE_ID, "7405605052754358")
        data = json.loads(genie_serialized_space(ROOT))
        self.assertEqual(data["version"], 2)
        targets = [x["identifier"] for x in data["data_sources"]["tables"]]
        self.assertEqual(
            targets,
            [f"{CATALOG}.{SCHEMA}.{table}" for table in TABLES],
        )
        self.assertEqual(len(data["config"]["sample_questions"]), 5)
        self.assertEqual(len(data["instructions"]["text_instructions"]), 1)
        self.assertIn("Never substitute Group figures",
                      data["instructions"]["text_instructions"][0]["content"][0])

    def test_single_run_deployment_uses_approved_warehouse_and_yaml(self):
        notebook = (ROOT / "setup" / "ABN_REAL_GENIE_SETUP.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("create_or_reuse_agent(", notebook)
        self.assertIn("client, WAREHOUSE_ID, REPO_ROOT", notebook)
        self.assertNotIn("dbutils.widgets", notebook)
        self.assertNotIn("YOUR_APPROVED_", notebook)

        yaml = (ROOT / "app.yaml").read_text(encoding="utf-8")
        self.assertIn("GENIE_SPACE_ID", yaml)
        self.assertIn("REAL_GENIE_SPACE_ID", yaml)
        self.assertIn("valueFrom: real-genie", yaml)
        self.assertIn("01f1ad042d3113b6b7a383586954667f", yaml)

    def test_ten_sql_examples_are_real_only_and_read_only(self):
        examples = trusted_sql_examples(ROOT)
        self.assertEqual(len(examples), 10)
        for sample in examples:
            sql = sample["sql"][0].lstrip()
            self.assertTrue(sql.upper().startswith("SELECT"))
            self.assertIn("frbg3s_studio_a.cfo_cockpit.", sql)
            self.assertNotIn("REPLACE_CATALOG", sql)
            self.assertNotIn("finance.gold", sql)
            self.assertNotIn(";", sql)
            self.assertEqual(len(sample["id"]), 32)
        self.assertEqual(len({x["id"] for x in examples}), 10)

    def test_creates_agent_with_exact_space_and_no_synthetic_write(self):
        calls = []
        class Genie:
            def list_spaces(self, **kwargs):
                return SimpleNamespace(spaces=[], next_page_token=None)
            def create_space(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(space_id="real-id")
        client = SimpleNamespace(genie=Genie())
        result = create_or_reuse_agent(client, "warehouse-42", ROOT)
        self.assertEqual(result, "real-id")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["warehouse_id"], "warehouse-42")
        self.assertEqual(calls[0]["title"], TITLE)
        self.assertEqual(
            {t["identifier"] for t in
             json.loads(calls[0]["serialized_space"])["data_sources"]["tables"]},
            {f"{CATALOG}.{SCHEMA}.{table}" for table in TABLES},
        )

    def test_existing_valid_agent_reused_without_update(self):
        calls = []
        class Genie:
            def list_spaces(self, **kwargs):
                return SimpleNamespace(
                    spaces=[SimpleNamespace(title=TITLE, space_id="real-id")],
                    next_page_token=None,
                )
            def get_space(self, **kwargs):
                calls.append(("get", kwargs))
                return SimpleNamespace(
                    warehouse_id="warehouse-42",
                    serialized_space=genie_serialized_space(ROOT),
                )
            def create_space(self, **kwargs):
                raise AssertionError("Should not create duplicate Genie Agent")
        self.assertEqual(
            create_or_reuse_agent(
                SimpleNamespace(genie=Genie()), "warehouse-42", ROOT
            ), "real-id"
        )
        self.assertTrue(calls)

    def test_existing_incorrect_agent_rejected(self):
        bad = json.loads(genie_serialized_space(ROOT))
        bad["data_sources"]["tables"].append(
            {"identifier": "old_catalog.synthetic_schema.synthetic_table"}
        )
        class Genie:
            def list_spaces(self, **kwargs):
                return SimpleNamespace(
                    spaces=[SimpleNamespace(title=TITLE, space_id="unsafe-id")],
                    next_page_token=None,
                )
            def get_space(self, **kwargs):
                return SimpleNamespace(
                    warehouse_id="warehouse-42",
                    serialized_space=json.dumps(bad),
                )
        with self.assertRaisesRegex(RuntimeError, "differ"):
            create_or_reuse_agent(
                SimpleNamespace(genie=Genie()), "warehouse-42", ROOT
            )

    def test_partially_existing_tables_fail_closed(self):
        class Catalog:
            def tableExists(self, name):
                return name.endswith(".cfo_group_quarterly")
        with self.assertRaisesRegex(RuntimeError, "Only some"):
            validate_existing_tables(
                SimpleNamespace(catalog=Catalog()), ROOT
            )


if __name__ == "__main__":
    unittest.main()
