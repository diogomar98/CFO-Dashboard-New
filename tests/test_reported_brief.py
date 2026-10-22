"""Real-data Morning Brief source checks; no Databricks connection is required."""
import unittest
from pathlib import Path

import pandas as pd

from src.real_data_mode import load_reported, build_reported_state
from src.reported_brief import (
    METRICS, EXTRA, SEGMENT_METRICS, BRIEF_CSS,
    chart_rows, compare_actuals, _metric_bar_chart, _primary_card, _key_insights,
    _prototype_article, load_existing_news,
)


class ReportedBriefTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.group, cls.segments = load_reported()

    def test_six_factsheet_metrics_do_not_duplicate_headline_cards(self):
        self.assertEqual(len(METRICS), 6)
        self.assertEqual(len({key for key, _, _ in METRICS}), 6)
        self.assertTrue({"net_profit_m", "cet1_ratio_pct", "lcr_pct"}.isdisjoint(
            {key for key, _, _ in METRICS}
        ))
        for key, _, unit in METRICS + EXTRA:
            self.assertIn(key, self.group.columns)
            self.assertIn(unit, {"€m", "%", "bps"})
            self.assertGreaterEqual(self.group[key].count(), 5)

    def test_five_quarter_grid_only_has_actual_figures(self):
        for metric, _, _ in METRICS:
            rows = chart_rows(self.group, metric)
            self.assertEqual(len(rows), 5, metric)
            self.assertEqual(rows[0][0], "Q2 2025")
            self.assertEqual(rows[-1][0], "Q2 2026")
            self.assertAlmostEqual(rows[-1][1], float(self.group.iloc[-1][metric]))

    def test_financial_comparisons_use_the_reported_quarters(self):
        profit = compare_actuals(self.group, "net_profit_m")
        self.assertAlmostEqual(profit["now"], 780.531615084)
        self.assertAlmostEqual(profit["previous"], 692.695881070)
        self.assertAlmostEqual(profit["year_ago"], 605.688745593)
        ratio = compare_actuals(self.group, "cet1_ratio_pct")
        self.assertAlmostEqual(ratio["previous"], 15.542293272)
        self.assertAlmostEqual(ratio["now"], 15.859229928)

    def test_expanded_bars_have_all_quarter_labels(self):
        rows = chart_rows(self.group, "net_profit_m")
        markup = _metric_bar_chart(rows, "Net profit", "€m")
        self.assertEqual(markup.count('class="rb-col'), 5)
        self.assertIn("Q2 &#x27;25", markup)
        self.assertIn("Q2 &#x27;26", markup)
        self.assertIn("€781m", markup)
        self.assertNotIn("<svg", markup)
        self.assertIn('class="rb-bar is-latest"', markup)

    def test_negative_cost_of_risk_is_rendered_not_suppressed(self):
        rows = chart_rows(self.group, "cost_of_risk_bps")
        self.assertLess(min(v for _, v in rows), 0.0)
        markup = _metric_bar_chart(rows, "Cost of risk", "bps")
        self.assertIn("−", markup) if "−" in markup else self.assertIn("-", markup)
        self.assertEqual(markup.count('class="rb-col'), 5)

    def test_hover_chart_and_insight_are_source_based(self):
        state = build_reported_state()
        rows = chart_rows(self.group, "cet1_ratio_pct", quarters=10)
        markup = _primary_card(
            "CET1 ratio", "15.86%", "+0.32pp", 
            [d for d, _ in rows], [v for _, v in rows], "ABN AMRO Group",
        )
        self.assertIn("rb-hover-trend", markup)
        self.assertIn("kpi-mini-segment", markup)
        self.assertIn("Q2 2026", markup)
        self.assertIn(":hover .rb-hover-trend", BRIEF_CSS)
        narratives = _key_insights(state)
        self.assertEqual(len(narratives), 3)
        self.assertIn("CET1 capital", narratives[1])

    def test_segment_scope_is_not_misrepresented_as_group_profit(self):
        wm = self.segments[self.segments["business_line"] == "Wealth Management"]
        self.assertEqual(len(SEGMENT_METRICS), 3)
        self.assertNotIn("net_profit_m", [x[0] for x in SEGMENT_METRICS])
        self.assertEqual(chart_rows(wm, "loans_m")[-1][0], "Q2 2026")
        self.assertEqual(chart_rows(wm, "net_profit_m"), [])
        state = build_reported_state("Wealth Management")
        self.assertEqual(len(_key_insights(state)), 3)

    def test_real_morning_uses_official_feeds_with_original_news_card_style(self):
        code = Path("src/reported_brief.py").read_text(encoding="utf-8")
        self.assertIn("from src.reported_news import recent_official_articles",code)
        self.assertIn("Official ECB RSS",code)
        self.assertIn("is-external rb-news-wide",code)
        self.assertIn("rb-news-grid",code)
        self.assertIn("No synthetic news records have been substituted",code)
        self.assertIn("src.reported_brief",
                      Path("src/real_data_mode.py").read_text(encoding="utf-8"))

    def test_news_deduplication_ranking_from_existing_sources(self):
        from unittest.mock import patch
        news = pd.DataFrame([
            {"news_id":"a","published_date":"2026-10-16","headline":"A",
             "relevance_score":90},
            {"news_id":"b","published_date":"2026-10-14","headline":"B",
             "relevance_score":80},
            {"news_id":"c","published_date":"2026-09-10","headline":"Old",
             "relevance_score":99},
        ])
        geo = pd.DataFrame([
            {"news_id":"a","country":"NL","geo_impact_score":10},
            {"news_id":"a","country":"FR","geo_impact_score":5},
            {"news_id":"b","country":"DE","geo_impact_score":8},
            {"news_id":"c","country":"NL","geo_impact_score":9},
        ])
        with patch("src.reported_brief.load_news_signals", return_value=news):
            with patch("src.reported_brief.load_news_geo_impact", return_value=geo):
                selected = load_existing_news()
        self.assertEqual(selected["news_id"].tolist(), ["a","b"])
        self.assertEqual(selected.iloc[0]["country"], "NL")

    def test_prototype_article_keeps_blue_feed_and_safe_links(self):
        row = pd.Series({
            "headline":"Market & credit","published_date":"2026-10-16",
            "category":"Monetary Policy","source":"External source",
            "source_url":"https://example.org/article",
            "potential_impact_level":"HIGH",
            "primary_affected_metric":"NIM",
            "bank_impact_summary":"Prototype impact",
            "confidence_score":0.95,
        })
        rendered = _prototype_article(row)
        self.assertIn("feed-item", rendered)
        self.assertIn("status-impact-high", rendered)
        self.assertIn("https://example.org/article", rendered)
        self.assertIn("Market &amp; credit", rendered)
        self.assertIn("Prototype", rendered)
        row["source_url"] = "javascript:alert(1)"
        self.assertNotIn('href="javascript:', _prototype_article(row))

    def test_visible_headline_trends_and_expand_collapse_behavior(self):
        code = Path("src/reported_brief.py").read_text(encoding="utf-8")
        self.assertIn("opacity: 1", code)
        self.assertNotIn(".rb-hover-trend {display:none;}", code)
        self.assertIn('st.session_state.pop("rb_focus", None)', code)
        self.assertNotIn('elif st.session_state.get("rb_focus")', code)
        self.assertIn('st.session_state["rb_expanded"] = True', code)



if __name__ == "__main__":
    unittest.main()
