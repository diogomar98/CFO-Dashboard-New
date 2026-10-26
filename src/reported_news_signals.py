"""Offline, user-supplied CFO news signals for Real Data News Intelligence.

The 26 article headlines, impact scores, direction and suggested actions are
PROTOTYPE assertions; none are independently verified. Never use these rows
as regulatory, market, customer-exposure or What-If model inputs.

This is deliberately separate from the original Synthetic news fixture and the
reviewed data/abn_news_curated.json used by the Real morning brief.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from src.reported_news_partner import REPORTED_NEWS_SEGMENTS, plain_text

NEWS_SIGNALS_PATH = Path(__file__).resolve().parent.parent / "data" / "news_signals.csv"
SIGNAL_FIELDS = (
    "news_id", "published_date", "headline", "source", "source_url", "category",
    "geographic_scope", "summary", "primary_affected_metric", "secondary_metrics",
    "impact_direction", "potential_impact_level", "relevance_score",
    "confidence_score", "bank_impact_summary", "suggested_action",
    "linked_scenario", "scenario_status", "classification_method",
    "is_public_source", "geo_profile",
)
COUNTRIES = ("Netherlands", "Germany", "France", "Belgium", "Europe")
GEO_BY_PROFILE = {
    "NL_DIRECT": "Netherlands", "DE_DIRECT": "Germany",
    "FR_DIRECT": "France", "BE_DIRECT": "Belgium",
    "EUROPE_ALL": "Europe",
}
SEGMENT_RULES = {
    "Personal & Business Banking": (
        "retail", "consumer", "mortgage", "household", "deposit",
        "credit quality", "loan growth", "nim", "inflation",
    ),
    "Corporate Banking": (
        "corporate", "manufacturing", "industrial", "trade finance",
        "wholesale", "loan growth", "credit quality", "fee income",
        "investment", "export", "import",
    ),
    "Wealth Management": (
        "wealth", "investment", "strategic position", "nim",
        "deposits", "rate",
    ),
    "Group Functions": (
        "operating costs", "provisions", "strategic position",
        "technology", "regulation", "liquidity", "cet1", "ecb rate",
        "inflation", "banking sector risk",
    ),
}


def illustrative_segments(item):
    """Illustrative theme tags only, not verified ABN customer exposures."""
    terms = " ".join(str(item.get(k) or "") for k in (
        "category", "headline", "primary_affected_metric",
        "secondary_metrics", "bank_impact_summary",
    )).lower()
    return [
        segment for segment in REPORTED_NEWS_SEGMENTS
        if any(term in terms for term in SEGMENT_RULES[segment])
    ]


def load_prototype_news_signals(path=None, *, as_of=None):
    """Read all 26 source records and preserve their declared provenance.

    Country comes from the explicit geographic_scope or country profile.
    The input can be displayed but it must NEVER be promoted to verified news.
    """
    target = Path(path) if path is not None else NEWS_SIGNALS_PATH
    if not target.is_file() or target.stat().st_size > 120_000:
        return [], {"mode": "none", "error": "news_signals CSV missing"}
    checked_at = as_of or datetime.now(timezone.utc).date()
    try:
        with target.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != SIGNAL_FIELDS:
                raise ValueError("Unexpected news_signals fields")
            rows = list(reader)
        if not 1 <= len(rows) <= 80:
            raise ValueError("Unexpected number of news signals")
        if len({r["news_id"] for r in rows}) != len(rows):
            raise ValueError("Duplicate signal IDs")

        out = []
        for row in rows:
            if None in row or any(v is None for v in row.values()):
                raise ValueError("Misaligned CSV fields")
            if row["classification_method"] != (
                "Synthetic prototype classification layered on public source"
            ):
                raise ValueError("Unapproved prototype classification description")
            day = date.fromisoformat(row["published_date"])
            if day > checked_at + timedelta(days=1):
                raise ValueError("Future-dated article")
            parsed = urlsplit(row["source_url"])
            if (parsed.scheme != "https" or not parsed.hostname
                    or parsed.username or parsed.password):
                raise ValueError("Invalid publisher URL")
            country = GEO_BY_PROFILE.get(row["geo_profile"])
            if country is None:
                raise ValueError("Unsupported country profile")
            supplied = row["geographic_scope"].strip()
            # The source has inconsistent labels e.g. EU/Euro area/Europe.
            # Use its explicit geo_profile as grouping metadata.
            tier = row["potential_impact_level"].strip().upper()
            if tier not in {"HIGH", "MEDIUM", "LOW"}:
                raise ValueError("Unsupported prototype tier")
            direction = row["impact_direction"].strip().title()
            if direction not in {"Positive", "Negative", "Mixed"}:
                raise ValueError("Unsupported prototype impact direction")
            score = float(row["relevance_score"])
            confidence = float(row["confidence_score"])
            if not (0 <= score <= 100 and 0 <= confidence <= 1):
                raise ValueError("Prototype scores outside expected range")
            fields = [x.strip() for x in row["secondary_metrics"].split(";") if x.strip()]
            out.append({
                "id": row["news_id"], "news_id": row["news_id"],
                "headline": plain_text(row["headline"])[:220],
                "url": row["source_url"], "source": row["source"][:90],
                "published": day.isoformat()+"T12:00:00+00:00",
                "summary": plain_text(row["summary"])[:450],
                "category": row["category"].strip() or "Uncategorised",
                "country": country, "geographic_scope": supplied,
                "geo_profile": row["geo_profile"],
                "primary_affected_metric": row["primary_affected_metric"].strip(),
                "secondary_metrics": fields,
                "impact_direction": direction,
                "editorial_relevance": tier,
                "relevance_origin": "Prototype classification",
                "relevance_score": score,
                "confidence_score": confidence,
                "bank_impact_summary": plain_text(row["bank_impact_summary"])[:600],
                "suggested_action": plain_text(row["suggested_action"])[:450],
                "linked_scenario": row["linked_scenario"].strip(),
                "scenario_status": row["scenario_status"].strip(),
                "classification_method": row["classification_method"],
                "is_public_source": row["is_public_source"].lower()=="true",
                "segments": illustrative_segments(row),
                "segments_origin": "Illustrative theme mapping, not assessed ABN exposures",
                "editorial_reason": plain_text(row["bank_impact_summary"])[:220],
                "priority": int(score),
                "relevant_terms": fields,
                "snapshot": True,
                "prototype": True,
            })
        out.sort(key=lambda a:(a["priority"],a["published"]),reverse=True)
        return out, {
            "mode": "prototype_signals",
            "source": "User-provided prototype news_signals CSV — unverified",
            "retrieved_at_utc":checked_at.isoformat(),
            "count":len(out),
        }
    except (ValueError, TypeError, KeyError, OSError, OverflowError):
        return [], {"mode":"none","error":"Prototype news_signals failed validation"}
