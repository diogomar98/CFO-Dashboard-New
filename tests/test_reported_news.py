"""Real News: official-source ingestion, AI triage and reviewed scenario gates."""
from datetime import date, datetime, timezone
from pathlib import Path
import json
import unittest
from unittest.mock import patch

from src.reported_news_partner import (
    DFR_URL, OFFICIAL_FEEDS, classify_headlines, fetch_ecb_articles,
    parse_ecb_rss, parse_ecb_rate_csv, verified_rate_scenario,
    load_official_news_snapshot, _safe_source_error,
)
from src.reported_news import current_verified_ecb_change, recent_official_articles
from src.public_horizon_engine import load_public_horizon_inputs
from src.real_data_mode import load_reported


RSS=b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>ECB press releases</title>
<item><title>Monetary policy decisions</title>
<link>https://www.ecb.europa.eu/press/pr/date/2026/html/test.en.html</link>
<pubDate>Thu, 10 Sep 2026 12:15:00 GMT</pubDate>
<description>ECB announced its decisions on the deposit facility.</description></item>
<item><title>Statistical press release &amp; bank credit</title>
<link>https://www.ecb.europa.eu/press/pr/date/2026/html/credit.en.html</link>
<pubDate>Wed, 30 Sep 2026 09:00:00 GMT</pubDate>
<description>Public credit data.</description></item></channel></rss>"""


class _Response:
    def __init__(self,content):
        self.content=content
        self.text=content.decode("utf-8")
    def raise_for_status(self):
        return None


class _Session:
    def __init__(self):
        self.calls=[]
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        return _Response(RSS)


class ReportedNewsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        group,_=load_reported()
        cls.financial=load_public_horizon_inputs(group)
        cls.now=datetime(2026,10,22,tzinfo=timezone.utc)
        cls.articles=parse_ecb_rss(RSS,"ECB press releases",now=cls.now)
        cls.policy_article=next(x for x in cls.articles
                                if x["headline"]=="Monetary policy decisions")

    def test_only_verified_ecb_hosts_and_rss_sources_accepted(self):
        self.assertEqual(len(self.articles),2)
        for a in self.articles:
            self.assertEqual(a["source"],"ECB press releases")
            self.assertTrue(a["url"].startswith("https://www.ecb.europa.eu/"))
        bad=RSS.replace(
            b"https://www.ecb.europa.eu/press/pr/date/2026/html/test.en.html",
            b"https://www.ecb.europa.eu.evil.example/test")
        self.assertEqual(len(parse_ecb_rss(bad,"ECB press releases",now=self.now)),1)
        entity=b'<!DOCTYPE rss [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        with self.assertRaises(ValueError):
            parse_ecb_rss(entity+RSS,"ECB press releases",now=self.now)

    def test_fixed_allowlist_requests_no_redirects_and_deduplicates(self):
        client=_Session()
        items,warnings=fetch_ecb_articles(session=client,now=self.now)
        self.assertFalse(warnings)
        self.assertEqual(len(items),2)
        self.assertEqual(len(client.calls),len(OFFICIAL_FEEDS))
        self.assertEqual({url for url,_ in client.calls},
                         {url for _,url in OFFICIAL_FEEDS})
        self.assertTrue(all(opts["allow_redirects"] is False
                            for _,opts in client.calls))

    def test_ai_classification_cannot_create_new_articles_or_stress_inputs(self):
        example=self.policy_article
        response={
            "articles":[
                {"id":example["id"],"relevance":"HIGH","metric":"Rates",
                 "reason":"ECB rate news could affect interest margins."},
                {"id":"fabricated-id","relevance":"HIGH","metric":"CET1",
                 "reason":"An unrelated fabricated article."},
            ]
        }
        with patch("src.reported_news_partner.generate_prompt_response",
                   return_value=json.dumps(response)) as llm:
            result=classify_headlines([example])
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["id"],example["id"])
        self.assertNotIn("rate_shock_bps",result[0])
        self.assertEqual(result[0]["metric"],"Rates")
        llm.assert_called_once()
        prompt=llm.call_args.args[0]
        self.assertIn(example["headline"],prompt)
        self.assertNotIn("data/abn_quarterly.csv",prompt)

    def test_real_headline_ai_confidence_is_optional_and_uncalibrated(self):
        example=self.policy_article
        result={
            "articles":[{
                "id":example["id"],"relevance":"HIGH","metric":"Rates",
                "reason":"Headline contains an ECB monetary-policy decision.",
                "confidence":0.81,
            }],
        }
        scored=classify_headlines(
            [example],generate=lambda _:json.dumps(result),
        )
        self.assertEqual(scored[0]["confidence"],0.81)
        self.assertIn("uncalibrated",scored[0]["classifier_status"])
        result["articles"][0]["confidence"]=5
        invalid=classify_headlines(
            [example],generate=lambda _:json.dumps(result),
        )
        self.assertIsNone(invalid[0]["confidence"])
        result["articles"][0].pop("confidence")
        missing=classify_headlines(
            [example],generate=lambda _:json.dumps(result),
        )
        self.assertIsNone(missing[0]["confidence"])

    def test_snapshot_news_uses_gateway_with_no_external_news_fetch(self):
        from src.reported_news import official_article_classifications
        with patch("src.reported_news.load_real_news_ai_classification",
                   return_value=[{"id":self.policy_article["id"],
                                  "relevance":"MEDIUM","metric":"Rates",
                                  "reason":"Potential impact","confidence":0.75}]) as model:
            classifications,error=official_article_classifications([self.policy_article])
        self.assertIsNone(error)
        model.assert_called_once()
        self.assertEqual(classifications[self.policy_article["id"]]["confidence"],0.75)
        with patch("src.reported_news.load_real_news_ai_classification",
                   side_effect=RuntimeError("unavailable")):
            classifications,error=official_article_classifications([self.policy_article])
        self.assertEqual(classifications[self.policy_article["id"]]["relevance"],"UNRATED")
        self.assertIsNone(classifications[self.policy_article["id"]]["confidence"])
        self.assertIsNotNone(error)

    def test_ecb_rate_event_requires_date_and_verified_post_close_change(self):
        events=parse_ecb_rate_csv(
            "TIME_PERIOD,OBS_VALUE\n"
            "2026-06-11,2.25\n"
            "2026-09-16,2.50\n"
        )
        scenario=verified_rate_scenario(
            self.policy_article,events,reported_dfr=2.25,today=date(2026,10,22))
        self.assertEqual(scenario["rate_shock_bps"],25)
        self.assertEqual(scenario["rate_effective_date"],"2026-09-16")
        self.assertEqual(scenario["official_data_url"],DFR_URL)
        # Reject a stale signal when later ECB decisions follow.
        stale=events+[(date(2026,10,10),2.75)]
        self.assertIsNone(verified_rate_scenario(
            self.policy_article,stale,today=date(2026,10,22)))
        unrelated=self.articles[0 if self.articles[0]!=self.policy_article else 1]
        self.assertIsNone(verified_rate_scenario(
            unrelated,events,today=date(2026,10,22)))

    def test_verified_change_derives_from_official_current_rate_not_ai(self):
        delta=current_verified_ecb_change(
            self.financial,events=[
                (date(2026,6,11),2.25),
                (date(2026,9,16),2.50)
            ],now=date(2026,10,22)
        )
        self.assertEqual(delta["rate_shock_bps"],25)
        self.assertEqual(delta["q2_2026_dfr_pct"],2.25)
        self.assertEqual(delta["latest_ecb_dfr_pct"],2.5)
        self.assertIsNone(current_verified_ecb_change(
            self.financial,events=[(date(2026,6,11),2.25)],
            now=date(2026,10,22)
        ))

    def test_saved_official_news_is_real_dated_and_host_allowlisted(self):
        entries,metadata=load_official_news_snapshot()
        self.assertGreaterEqual(len(entries),10)
        self.assertEqual(metadata["mode"],"snapshot")
        self.assertIn("2026-10-22",metadata["retrieved_at_utc"])
        self.assertTrue(all(a["source"].startswith("ECB ") for a in entries))
        self.assertTrue(all(a["url"].startswith("https://www.ecb.europa.eu/")
                            for a in entries))
        self.assertTrue(all(a.get("published") and a.get("headline")
                            for a in entries))

    def test_curated_publisher_selection_works_without_live_ecb(self):
        from src.reported_news_partner import load_curated_bank_news
        items,meta=load_curated_bank_news()
        self.assertEqual(meta["mode"],"curated")
        self.assertGreaterEqual(len(items),9)
        self.assertTrue(any("Bloomberg" in x["source"] for x in items))
        self.assertTrue(any("Yahoo Finance" in x["source"] for x in items))
        self.assertTrue(any("FD Partner" in x["source"] for x in items))
        self.assertTrue(any("Financial Times" in x["source"] for x in items))
        self.assertTrue(all(x["url"].startswith("https://") for x in items))
        self.assertEqual(len({x["url"] for x in items}),len(items))
        self.assertFalse(any("rate_shock_bps" in x for x in items))

    def test_curated_relevance_and_business_line_tags_match_reported_sources(self):
        from src.reported_news_partner import (
            load_curated_bank_news,REPORTED_NEWS_SEGMENTS,RELEVANCE_LEVELS,
        )
        from src.real_data_mode import build_reported_state
        items,_=load_curated_bank_news()
        actual=set(build_reported_state().reported_segments["business_line"])
        self.assertEqual(set(REPORTED_NEWS_SEGMENTS),actual)
        self.assertTrue(all(a["editorial_relevance"] in RELEVANCE_LEVELS
                            for a in items))
        self.assertTrue(all(a["segments"] for a in items))
        self.assertTrue(all(set(a["segments"]).issubset(actual) for a in items))
        self.assertTrue(all(a["editorial_reason"] for a in items))
        self.assertEqual(
            sum(a["editorial_relevance"]=="HIGH" for a in items),4,
        )

    def test_combined_filters_use_reviewed_relevance_and_exact_segment(self):
        from src.reported_news import (
            _effective_news_assessment,filter_financial_news,
        )
        from src.reported_news_partner import load_curated_bank_news
        items,_=load_curated_bank_news()
        assessments={
            a["id"]:_effective_news_assessment(a) for a in items
        }
        high=filter_financial_news(items,assessments,relevance="High")
        self.assertEqual(len(high),4)
        wealth=filter_financial_news(
            items,assessments,segment="Wealth Management",
        )
        self.assertTrue(wealth)
        self.assertTrue(all("Wealth Management" in a["segments"]
                            for a in wealth))
        high_wealth=filter_financial_news(
            items,assessments,relevance="High",segment="Wealth Management",
        )
        self.assertEqual(len(high_wealth),2)
        self.assertTrue(all(a["editorial_relevance"]=="HIGH"
                            for a in high_wealth))
        high_corporate=filter_financial_news(
            items,assessments,relevance="High",segment="Corporate Banking",
        )
        self.assertEqual(len(high_corporate),1)
        # Group Functions is not equivalent to all business segments.
        group=filter_financial_news(
            items,assessments,segment="Group Functions",
        )
        self.assertTrue(all("Group Functions" in a["segments"] for a in group))
        self.assertEqual(
            len(filter_financial_news(items,assessments)),len(items)
        )
        with self.assertRaises(ValueError):
            filter_financial_news(items,assessments,relevance="Critical")
        with self.assertRaises(ValueError):
            filter_financial_news(items,assessments,segment="Retail Banking")

    def test_editorial_review_not_silently_overridden_by_disagreeing_ai(self):
        from src.reported_news import _effective_news_assessment
        from src.reported_news_partner import load_curated_bank_news
        items,_=load_curated_bank_news()
        article=next(a for a in items if a["editorial_relevance"]=="HIGH")
        conflict=_effective_news_assessment(
            article,{"relevance":"LOW","reason":"Contradictory",
                     "confidence":0.99,"metric":"None"},
        )
        self.assertEqual(conflict["relevance"],"HIGH")
        self.assertEqual(conflict["relevance_origin"],"Editorial review")
        self.assertIsNone(conflict["confidence"])
        self.assertEqual(conflict["reason"],article["editorial_reason"])
        agreement=_effective_news_assessment(
            article,{"relevance":"HIGH","reason":"Direct governance change",
                     "confidence":0.8,"metric":"CET1"},
        )
        self.assertEqual(agreement["confidence"],0.8)
        self.assertTrue(agreement["ai_agrees"])
        self.assertEqual(agreement["reason"],"Direct governance change")

    def test_model_runs_on_all_curated_articles_in_batches(self):
        from src.reported_news import official_article_classifications
        from src.reported_news_partner import load_curated_bank_news
        items,_=load_curated_bank_news()
        batches=[]
        def classify(batch):
            batches.append(len(batch))
            return [{"id":a["id"],"relevance":a["editorial_relevance"],
                     "reason":"Potential financial relevance",
                     "metric":"NII","confidence":0.8} for a in batch]
        with patch("src.reported_news.load_real_news_ai_classification",
                   side_effect=classify):
            result,error=official_article_classifications(items)
        self.assertIsNone(error)
        self.assertEqual(batches,[8,3])
        self.assertEqual(len(result),11)
        self.assertTrue(all(result[a["id"]]["confidence"]==0.8 for a in items))
        # Corporate gateway unavailable: deterministic reviewed filters still work.
        with patch("src.reported_news.load_real_news_ai_classification",
                   side_effect=RuntimeError("Gateway unavailable")):
            reviewed,error=official_article_classifications(items)
        self.assertIsNotNone(error)
        self.assertEqual(len(reviewed),11)
        self.assertTrue(all(v["relevance"] in {"HIGH","MEDIUM","LOW"}
                            for v in reviewed.values()))
        self.assertTrue(all(v["confidence"] is None for v in reviewed.values()))

    def test_segment_labels_render_on_original_coloured_cards(self):
        from src.reported_news_partner import load_curated_bank_news
        from src.reported_brief import _official_article_card
        from src.reported_news import _effective_news_assessment
        items,_=load_curated_bank_news()
        item=next(a for a in items if "Wealth Management" in a["segments"])
        markup=_official_article_card(item,_effective_news_assessment(item),saved=True)
        self.assertIn("Potential business lines",markup)
        self.assertIn("Wealth Management",markup)
        self.assertIn("Reviewed relevance",markup)
        self.assertIn("Confidence · Not assessed",markup)
        self.assertIn("status-impact-",markup)
        view=Path("src/reported_news.py").read_text(encoding="utf-8")
        self.assertIn("rn_filter_relevance",view)
        self.assertIn("rn_filter_segment",view)
        self.assertIn("How is relevance defined?",view)
        self.assertIn("filter_financial_news(",view)
        self.assertIn("rn-news-scroll",view)

    def test_restricted_app_never_attempts_live_internet_for_curated_news(self):
        with patch("src.reported_news.load_real_public_news") as network:
            items,warnings,status=recent_official_articles(include_status=True)
            network.assert_not_called()
        self.assertGreaterEqual(len(items),9)
        self.assertEqual(status["mode"],"curated")
        self.assertFalse(warnings)
        self.assertTrue(all(x["snapshot"] for x in items))

    def test_curated_source_fallback_is_dated_official_ecb_archive(self):
        with patch("src.reported_news.load_curated_bank_news",
                   return_value=([],{"mode":"none"})):
            items,warnings,status=recent_official_articles(include_status=True)
        self.assertGreaterEqual(len(items),10)
        self.assertEqual(status["mode"],"snapshot")
        self.assertTrue(any("older ECB snapshot" in w for w in warnings))

    def test_source_diagnostics_suppress_internal_proxy_details(self):
        import requests
        for exc,label in (
            (requests.exceptions.SSLError("corp_proxy_login_secret"),"TLS/certificate"),
            (requests.exceptions.ProxyError("corp_proxy_login_secret"),"Corporate proxy"),
            (requests.exceptions.ConnectTimeout("corp_proxy_login_secret"),"timed out"),
        ):
            detail=_safe_source_error(exc)
            self.assertIn(label,detail)
            self.assertNotIn("secret",detail)

    def test_news_html_is_clearly_dated_not_a_synthetic_fallback(self):
        code=Path("src/reported_news.py").read_text(encoding="utf-8")
        brief=Path("src/reported_brief.py").read_text(encoding="utf-8")
        self.assertIn("recent_official_articles(include_status=True)",code)
        self.assertIn("rn-news-scroll",code)
        self.assertNotIn("Retry live ECB connection",code)
        self.assertNotIn("News connection diagnostics",code)
        self.assertIn("data/abn_news_curated.json",code)
        self.assertIn("recent_official_articles(include_status=True)",brief)
        self.assertIn("Multi-publisher financial news",brief)
        self.assertIn("AI relevance",brief)
        self.assertIn("Official excerpt",brief)
        self.assertIn("rb-news-grid",brief)
        self.assertNotIn("load_existing_news()",brief[brief.index("def _external_news()"):])

    def test_real_routing_and_synthetic_mode_untouched(self):
        mode=Path("src/real_data_mode.py").read_text(encoding="utf-8")
        self.assertIn('if module == "news":',mode)
        self.assertIn("from src.reported_news import render_reported_news",mode)
        self.assertIn('if module == "strategy":',mode)
        shell=Path("main.py").read_text(encoding="utf-8")
        self.assertIn("Financial news · AI relevance",shell)
        self.assertIn('f"#1 {top_strategy_name}"',shell)  # synthetic retained
        self.assertNotIn('"Strategic radar pending"',shell)
        synthetic=Path("src/modules/news.py").read_text(encoding="utf-8")
        self.assertIn("def render_news(s)",synthetic)
        self.assertIn("load_extracted_signals()",synthetic)
        scenario=Path("src/reported_scenario.py").read_text(encoding="utf-8")
        self.assertIn('st.session_state.get("rs_news_source")',scenario)
        self.assertIn("Official ECB rate update prepared",scenario)
        morning=Path("src/reported_brief.py").read_text(encoding="utf-8")
        self.assertIn("from src.reported_news import (",morning)
        self.assertIn("is-external rb-news-wide",morning)


if __name__=="__main__":
    unittest.main()
