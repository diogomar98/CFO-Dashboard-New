"""Offline Real Data News integration, country splits and source integrity tests."""
import unittest
from pathlib import Path

from src.reported_news_signals import (
    COUNTRIES, load_prototype_news_signals, illustrative_segments,
)
from src.reported_news import (
    filter_financial_news, _effective_news_assessment, _card,
)


class RealNewsSignalsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.news, cls.status = load_prototype_news_signals()
        cls.assessments = {
            item["id"]: _effective_news_assessment(item) for item in cls.news
        }

    def test_all_twenty_six_rows_read_from_supplied_csv(self):
        self.assertEqual(len(self.news), 26)
        self.assertEqual(self.status["mode"], "prototype_signals")
        self.assertEqual(len({a["id"] for a in self.news}), 26)
        self.assertTrue(all(a.get("prototype") for a in self.news))
        self.assertTrue(all(a["classification_method"].startswith(
            "Synthetic prototype classification"
        ) for a in self.news))

    def test_country_profile_groups_and_filters(self):
        by_country={c:sum(x["country"]==c for x in self.news) for c in COUNTRIES}
        self.assertEqual(
            by_country,
            {"Netherlands":5, "Germany":5, "France":5,
             "Belgium":5, "Europe":6},
        )
        self.assertEqual(
            len(filter_financial_news(
                self.news, self.assessments,country="Germany",
            )), 5
        )
        all_europe=filter_financial_news(
            self.news,self.assessments,country="Europe",
        )
        self.assertEqual(len(all_europe),6)
        self.assertTrue(all(x["geo_profile"]=="EUROPE_ALL" for x in all_europe))

    def test_missing_source_metadata_not_fabricated(self):
        item=next(a for a in self.news if a["id"]=="NEWS_015")
        self.assertEqual(item["category"],"Uncategorised")
        self.assertEqual(item["country"],"France")
        self.assertEqual(item["geographic_scope"],"")

    def test_prototype_confidence_not_accepted_as_verified(self):
        item=next(x for x in self.news if x["id"]=="NEWS_021")
        assessment=self.assessments[item["id"]]
        self.assertEqual(assessment["relevance"],"HIGH")
        self.assertEqual(assessment["relevance_origin"],"Prototype classification")
        self.assertIsNone(assessment["confidence"])
        html=_card(item,assessment,saved=True)
        self.assertIn("Prototype assessment (unverified)",html)
        self.assertIn("Confidence · Not assessed",html)
        self.assertIn("status-impact-high",html)
        self.assertIn("Prototype",html)
        self.assertIn("source",html.lower())

    def test_filters_combine_relevance_country_metric_direction_and_segment(self):
        german=filter_financial_news(
            self.news,self.assessments,country="Germany",
            relevance="High",direction="Negative",
        )
        self.assertTrue(german)
        self.assertTrue(all(x["country"]=="Germany" and
                            x["editorial_relevance"]=="HIGH" and
                            x["impact_direction"]=="Negative" for x in german))
        metric=german[0]["primary_affected_metric"]
        subset=filter_financial_news(
            self.news,self.assessments,country="Germany",
            relevance="High",direction="Negative",metric=metric,
        )
        self.assertTrue(subset)
        self.assertTrue(all(x["primary_affected_metric"]==metric for x in subset))
        segments=illustrative_segments({
            "category":"Macroeconomy",
            "headline":"corporate export",
            "primary_affected_metric":"Credit Quality",
            "secondary_metrics":"",
            "bank_impact_summary":"",
        })
        self.assertIn("Corporate Banking",segments)
        self.assertIn("Personal & Business Banking",segments)
        with self.assertRaises(ValueError):
            filter_financial_news(self.news,self.assessments,country="Spain")
        with self.assertRaises(ValueError):
            filter_financial_news(self.news,self.assessments,direction="Profitable")
        with self.assertRaises(ValueError):
            filter_financial_news(self.news,self.assessments,metric="Invented Metric")

    def test_curated_snapshot_is_still_separate_and_synthetic_unchanged(self):
        from src.reported_news import recent_official_articles
        items,warnings,status=recent_official_articles(include_status=True)
        self.assertEqual(status["mode"],"curated")
        self.assertGreaterEqual(len(items),9)
        self.assertFalse(warnings)
        self.assertFalse(any(item.get("prototype") for item in items))
        code=Path("src/reported_news.py").read_text(encoding="utf-8")
        self.assertIn("rn_filter_country",code)
        self.assertIn("rn_filter_relevance",code)
        self.assertIn("rn_filter_segment",code)
        self.assertIn("rn_filter_metric",code)
        self.assertIn("rn_filter_direction",code)
        self.assertIn("rn-country-title",code)
        self.assertIn("news_signals",code)
        self.assertIn("do not",code.lower())
        original=Path("src/modules/news.py").read_text(encoding="utf-8")
        self.assertIn("def render_news(s)",original)


if __name__=="__main__":
    unittest.main()
