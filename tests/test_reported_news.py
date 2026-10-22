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
        self.assertEqual(classifications,{})
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

    def test_blocked_abn_egress_keeps_real_snapshot_and_status(self):
        with patch("src.reported_news.load_real_public_news",
                   return_value=([],["ECB press releases: Outbound HTTPS/DNS connection failed"])):
            items,warnings,status=recent_official_articles(include_status=True)
        self.assertGreaterEqual(len(items),10)
        self.assertEqual(status["mode"],"snapshot")
        self.assertTrue(any("Live ECB feeds unavailable" in x for x in warnings))
        self.assertFalse(any("Synthetic" in x for x in warnings))
        self.assertNotIn("rate_shock_bps",items[0])

    def test_live_feed_takes_priority_over_saved_snapshot(self):
        with patch("src.reported_news.load_real_public_news",
                   return_value=(self.articles,[])):
            with patch("src.reported_news.load_official_news_snapshot") as loader:
                items,warnings,status=recent_official_articles(include_status=True)
                loader.assert_not_called()
        self.assertEqual(status["mode"],"live")
        self.assertEqual(items,self.articles)
        self.assertFalse(warnings)

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
        self.assertIn("News connection diagnostics",code)
        self.assertIn("Retry live ECB connection",code)
        self.assertIn("news is unavailable",code.lower())
        self.assertIn("recent_official_articles(include_status=True)",brief)
        self.assertIn("Saved official ECB headlines",brief)
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
        self.assertIn("Official ECB news · AI relevance",shell)
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
