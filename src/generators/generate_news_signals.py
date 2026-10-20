from pathlib import Path
import pandas as pd

PUBLIC_NEWS = [
    {
        'published_date': '2026-09-02', 
        'headline': 'European bank shares continue to outperform the market', 
        'source': 'ING Market News', 
        'source_url': 'https://www.ing.nl/en/personal/investing/market-news-and-views/number-of-the-week-european-banks-continue-to-outperform-the-market', 
        'category': 'Markets & Peer Valuation', 
        'geographic_scope': 'Europe', 
        'geo_profile': 'EUROPE_ALL', 
        'summary': 'European bank equities, including ABN AMRO and ING, maintained their outperformance in early September driven by stable interest margins and share buybacks.', 
        'primary_affected_metric': 'Strategic Position', 
        'secondary_metrics': 'Market Valuation; RoTE', 
        'impact_direction': 'Mixed', 
        'relevance_score': 65, 
        'confidence_score': 0.90, 
        'bank_impact_summary': 'Rising valuations for Dutch and European peers elevate market expectations for return on equity and capital distributions.', 
        'suggested_action': 'Review peer capital return policies and benchmark against domestic rivals.', 
        'linked_scenario': '', 
        'scenario_status': 'NONE'
    },
    {
        'published_date': '2026-09-10', 
        'headline': 'ECB holds key interest rate steady at 2.65%', 
        'source': 'European Central Bank', 
        'source_url': 'https://forexfundamentals.com/economic-calendar/ecb/2026-09-10', 
        'category': 'Monetary Policy', 
        'geographic_scope': 'Euro area', 
        'geo_profile': 'EUROPE_ALL', 
        'summary': 'The European Central Bank maintained its benchmark interest rate at 2.65%, matching market forecasts and pausing further rate increases.', 
        'primary_affected_metric': 'NIM', 
        'secondary_metrics': 'NII; Deposits; Loan Growth', 
        'impact_direction': 'Mixed', 
        'relevance_score': 95, 
        'confidence_score': 0.99, 
        'bank_impact_summary': 'A steady rate hold provides stability for short-term repricing expectations, avoiding immediate deposit cost hikes while preserving asset margins.', 
        'suggested_action': 'Maintain base case rate scenarios and track deposit betas carefully.', 
        'linked_scenario': '', 
        'scenario_status': 'NONE'
    },
    {
        'published_date': '2026-09-17', 
        'headline': 'ING announces early redemption of USD 1.5 billion AT1 Capital Securities', 
        'source': 'ING', 
        'source_url': 'https://ing.com/newsroom/news/press-release', 
        'category': 'Peer & Competitor', 
        'geographic_scope': 'Netherlands', 
        'geo_profile': 'NL_DIRECT', 
        'summary': 'ING announced the redemption of its 5.750% Perpetual AT1 Contingent Convertible Capital Securities to optimize its capital structure.', 
        'primary_affected_metric': 'Strategic Position', 
        'secondary_metrics': 'CET1; Funding Costs', 
        'impact_direction': 'Negative', 
        'relevance_score': 78, 
        'confidence_score': 0.95, 
        'bank_impact_summary': 'Proactive capital optimization by a primary domestic peer sets a competitive standard for active liability and AT1 management.', 
        'suggested_action': 'Assess current capital structure efficiency and potential call dates for outstanding AT1 instruments.', 
        'linked_scenario': '', 
        'scenario_status': 'NONE'
    },
    {
        'published_date': '2026-09-23', 
        'headline': 'EU technical standards on operational risk under CRR enter into force', 
        'source': 'EU Official Journal', 
        'source_url': 'https://www.algoodbody.com/insights-publications/financial-services-regulation-and-compliance-banking-and-payments-september-2026', 
        'category': 'Regulation & Capital', 
        'geographic_scope': 'EU', 
        'geo_profile': 'EUROPE_ALL', 
        'summary': 'New regulatory technical standards specifying operational risk requirements for credit institutions under the Capital Requirements Regulation formally took effect.', 
        'primary_affected_metric': 'Operating Costs', 
        'secondary_metrics': 'Operational Risk; RWA', 
        'impact_direction': 'Negative', 
        'relevance_score': 82, 
        'confidence_score': 0.98, 
        'bank_impact_summary': 'Stricter specifications for operational risk management and loss data capture may lead to increased compliance and IT system costs.', 
        'suggested_action': 'Review operational risk framework for gaps against the new CRR technical standards.', 
        'linked_scenario': '', 
        'scenario_status': 'NONE'
    },
    {
        'published_date': '2026-09-24', 
        'headline': 'EBA reviews MiCA regulation regarding crypto-asset reserve requirements', 
        'source': 'European Banking Authority', 
        'source_url': 'https://www.slaughterandmay.com/insights/financial-regulation-weekly-bulletin/financial-regulation-weekly-bulletin-24-september-2026/', 
        'category': 'Regulation & Technology', 
        'geographic_scope': 'EU', 
        'geo_profile': 'EUROPE_ALL', 
        'summary': 'The EBA responded to the EC consultation on MiCA, addressing definitions and reserve requirements for asset-referenced and e-money tokens.', 
        'primary_affected_metric': 'Strategic Position', 
        'secondary_metrics': 'Technology; Deposits', 
        'impact_direction': 'Mixed', 
        'relevance_score': 60, 
        'confidence_score': 0.92, 
        'bank_impact_summary': 'Regulatory clarity on crypto-assets opens strategic opportunities but also signals potential disintermediation risks from e-money tokens.', 
        'suggested_action': 'Feed MiCA framework developments into digital asset strategy planning.', 
        'linked_scenario': '', 
        'scenario_status': 'NONE'
    },
    {
        'published_date': '2026-10-09', 
        'headline': 'ING continues massive share buyback programme execution in Q4', 
        'source': 'ING', 
        'source_url': 'https://ing.com/newsroom/news/press-release', 
        'category': 'Peer & Competitor', 
        'geographic_scope': 'Netherlands', 
        'geo_profile': 'NL_DIRECT', 
        'summary': 'ING announced the ongoing purchase of millions of shares weekly into October, reflecting robust capital levels and shareholder return commitments.', 
        'primary_affected_metric': 'Strategic Position', 
        'secondary_metrics': 'CET1', 
        'impact_direction': 'Negative', 
        'relevance_score': 80, 
        'confidence_score': 0.98, 
        'bank_impact_summary': 'Aggressive capital returns by ING place direct competitive pressure on other Dutch banks to justify their own capital retention strategies to investors.', 
        'suggested_action': 'Prepare defense of current capital payout ratios ahead of earnings.', 
        'linked_scenario': '', 
        'scenario_status': 'NONE'
    },
    {
        'published_date': '2026-10-16', 
        'headline': 'Euro-area inflation jumps to 3.8% in September', 
        'source': 'Eurostat', 
        'source_url': 'https://ec.europa.eu/eurostat/web/products-euro-indicators/w/2-16102026-ap', 
        'category': 'Inflation & Monetary Policy', 
        'geographic_scope': 'Euro area', 
        'geo_profile': 'EUROPE_ALL', 
        'summary': 'Euro-area annual inflation rose significantly to 3.8% in September 2026, up from 3.2% in August, driven by energy and services.', 
        'primary_affected_metric': 'NIM', 
        'secondary_metrics': 'ECB Rate; Credit Quality; Operating Costs', 
        'impact_direction': 'Mixed', 
        'relevance_score': 96, 
        'confidence_score': 0.99, 
        'bank_impact_summary': 'An unexpected spike in inflation makes near-term rate cuts highly unlikely, supporting NIM but drastically increasing credit default risk among vulnerable borrowers.', 
        'suggested_action': 'Instantly refresh upside rate scenarios and initiate a review of Stage 2 loan migration.', 
        'linked_scenario': 'Rate +25bps', 
        'scenario_status': 'PLANNED'
    },
    {
        'published_date': '2026-10-17', 
        'headline': 'ECB President highlights euro area economic resilience amid energy shocks', 
        'source': 'European Central Bank', 
        'source_url': 'https://www.bis.org/speeches/20261020-imfc-statement', 
        'category': 'Macroeconomy', 
        'geographic_scope': 'Euro area', 
        'geo_profile': 'EUROPE_ALL', 
        'summary': 'ECB President Christine Lagarde stated the euro area economy has proven resilient with broad-based growth despite global headwinds and an ongoing energy shock.', 
        'primary_affected_metric': 'Loan Growth', 
        'secondary_metrics': 'Credit Quality', 
        'impact_direction': 'Positive', 
        'relevance_score': 72, 
        'confidence_score': 0.96, 
        'bank_impact_summary': 'A resilient macro environment supports baseline corporate credit demand and limits severe near-term portfolio deterioration.', 
        'suggested_action': 'Validate resilient economic baseline against internal portfolio early warning indicators.', 
        'linked_scenario': '', 
        'scenario_status': 'NONE'
    }
]

PROFILE_WEIGHTS = {
    'EUROPE_ALL': {'Netherlands': 1.0, 'Germany': 1.0, 'France': 1.0, 'Belgium': 1.0},
    'NL_DIRECT': {'Netherlands': 1.0, 'Germany': 0.18, 'France': 0.12, 'Belgium': 0.2},
    'DE_DIRECT': {'Netherlands': 0.2, 'Germany': 1.0, 'France': 0.15, 'Belgium': 0.14},
    'FR_DIRECT': {'Netherlands': 0.15, 'Germany': 0.15, 'France': 1.0, 'Belgium': 0.28},
    'BE_DIRECT': {'Netherlands': 0.24, 'Germany': 0.12, 'France': 0.3, 'Belgium': 1.0},
    'NL_DE_BE': {'Netherlands': 1.0, 'Germany': 0.9, 'France': 0.18, 'Belgium': 0.78},
    'FR_BE': {'Netherlands': 0.18, 'Germany': 0.15, 'France': 1.0, 'Belgium': 0.82},
}

COUNTRY_CODES = {'Netherlands': 'NL', 'Germany': 'DE', 'France': 'FR', 'Belgium': 'BE'}

DEFAULT_EXPOSURE = {'Netherlands': 0.4541, 'Germany': 0.2244, 'France': 0.1852, 'Belgium': 0.1362}

DIRECTION_SIGN = {'Positive': 1, 'Negative': -1, 'Mixed': 0}

def _load_exposure(bank_daily_path: Path) -> dict:
    exposure = DEFAULT_EXPOSURE.copy()
    if bank_daily_path.exists():
        d = pd.read_csv(bank_daily_path, parse_dates=["date"])
        latest = d["date"].max()
        x = (
            d[d["date"] == latest]
            .groupby("country", as_index=True)
            .agg(
                loans_m=("loan_balance_m", "sum"),
                deposits_m=("deposit_balance_m", "sum"),
            )
        )
        x["exposure"] = x["loans_m"] + x["deposits_m"]
        exposure.update(
            {k: float(v) for k, v in (x["exposure"] / x["exposure"].sum()).to_dict().items()}
        )
    return exposure

def generate_news_datasets(
    bank_daily_path: str = "data/bank_daily_signals.csv",
    output_dir: str = "data",
):
    """
    Create:
    1) news_signals.csv
       One row per curated public news/release item.
       Public facts are paraphrased from the source URL.
       Bank relevance / impact fields are synthetic prototype classifications.

    2) news_geo_impact.csv
       One row per news item x core geography, with an exposure-aware
       geographic impact component for interactive mapping.

    The impact classifications are NOT statements made by the cited sources.
    They are synthetic analytical labels for the fictional bank prototype.
    """
    news = pd.DataFrame(PUBLIC_NEWS)
    news.insert(0, "news_id", [f"NEWS_{i:03d}" for i in range(1, len(news) + 1)])
    news["published_date"] = pd.to_datetime(news["published_date"])
    news["potential_impact_level"] = pd.cut(
        news["relevance_score"],
        bins=[-1, 49, 79, 101],
        labels=["LOW", "MEDIUM", "HIGH"],
    ).astype(str)
    news["classification_method"] = (
        "Synthetic prototype classification layered on public source"
    )
    news["is_public_source"] = True

    news = news[[
        "news_id", "published_date", "headline", "source", "source_url",
        "category", "geographic_scope", "summary",
        "primary_affected_metric", "secondary_metrics",
        "impact_direction", "potential_impact_level",
        "relevance_score", "confidence_score",
        "bank_impact_summary", "suggested_action",
        "linked_scenario", "scenario_status",
        "classification_method", "is_public_source", "geo_profile",
    ]]

    exposure = _load_exposure(Path(bank_daily_path))
    max_exposure = max(exposure.values())

    geo_rows = []
    for row in news.itertuples(index=False):
        weights = PROFILE_WEIGHTS[row.geo_profile]

        for country, geo_weight in weights.items():
            exp_factor = 0.70 + 0.30 * (exposure[country] / max_exposure)

            score = (
                float(row.relevance_score)
                * float(row.confidence_score)
                * float(geo_weight)
                * exp_factor
            )
            score = round(min(score, 100), 1)

            if score >= 60:
                bucket = "HIGH"
            elif score >= 30:
                bucket = "MEDIUM"
            else:
                bucket = "LOW"

            if geo_weight >= 0.80:
                reason = "Direct or broad geographic relevance"
            elif geo_weight >= 0.25:
                reason = "Meaningful regional spillover"
            else:
                reason = "Limited cross-border spillover"

            geo_rows.append({
                "news_id": row.news_id,
                "published_date": row.published_date,
                "country": country,
                "country_code": COUNTRY_CODES[country],
                "bank_exposure_share_pct": round(exposure[country] * 100, 2),
                "geographic_relevance_weight": round(geo_weight, 2),
                "geo_impact_score": score,
                "map_impact_level": bucket,
                "impact_direction": row.impact_direction,
                "signed_geo_score": round(
                    score * DIRECTION_SIGN.get(row.impact_direction, 0), 1
                ),
                "exposure_reason": reason,
            })

    geo = pd.DataFrame(geo_rows)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    news_path = output / "news_signals.csv"
    geo_path = output / "news_geo_impact.csv"

    news.to_csv(news_path, index=False, date_format="%Y-%m-%d")
    geo.to_csv(geo_path, index=False, date_format="%Y-%m-%d")

    return news, geo

if __name__ == "__main__":
    news, geo = generate_news_datasets()
    print(f"Created news_signals.csv with {len(news)} rows.")
    print(f"Created news_geo_impact.csv with {len(geo)} rows.")
