"""Independent public ECB news RSS connectivity smoke test (no AI token used)."""
import json
from src.reported_news_partner import fetch_ecb_articles, OFFICIAL_FEEDS

def main():
    articles, errors=fetch_ecb_articles()
    print("OFFICIAL_NEWS_SMOKE "+json.dumps({
        "configured_sources":[name for name,_ in OFFICIAL_FEEDS],
        "validated_headlines":len(articles),
        "warnings":errors,
        "sample_sources":[{"source":a["source"],"url":a["url"]}
                          for a in articles[:3]],
    }))
    if not articles:
        raise SystemExit("No official RSS articles retrieved; investigate source access.")

if __name__=="__main__":
    main()
