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
    # Public, official source data only. The base64 marker is machine-readable
    # so a reviewed point-in-time snapshot can be committed as an offline
    # display fallback when the ABN app's outbound RSS is blocked.
    from datetime import datetime, timezone
    from base64 import b64encode
    snapshot={
        "source_type":"official_ecb_rss",
        "retrieved_at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "description":"Verified ECB RSS headlines; not a continuously refreshing news feed",
        "articles":articles[:24],
    }
    encoded=b64encode(json.dumps(snapshot,ensure_ascii=False,separators=(",",":")).encode("utf-8")).decode("ascii")
    print("ECB_NEWS_SNAPSHOT_BASE64="+encoded)

if __name__=="__main__":
    main()
