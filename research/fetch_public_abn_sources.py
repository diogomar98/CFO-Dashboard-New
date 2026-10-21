#!/usr/bin/env python3
"""Download ABN AMRO's *public* financial factsheets as auditable raw evidence.

No private bank files, no synthetic data, no forecasting or harmonization.
Produces exact original source URLs, SHA-256 digests, workbook tab counts and
an extraction approval queue. Intended to run on GitHub Actions where external
downloads are permitted. The raw files are retained only as a CI artifact.
"""
import argparse
import csv
import hashlib
import io
import re
import sys
import time
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


ARCHIVE = "https://www.abnamro.com/en/investor-relations/information/all-financial-reports"
FIRST, LAST = (2016, 1), (2026, 2)
UA = {"User-Agent": "CFO-Dashboard-New-public-source-research/1.0 (financial research)"}
# Direct download fallbacks obtained from the OFFICIAL archive's own links.
# These are not alternatives to approving the full 42-quarter extraction.
KNOWN_DIRECT = [
    ("2016-Q1", "Factsheet 2016 Q1", "https://assets.ctfassets.net/1u811bvgvthc/4iXV2NIj6qwUI3qidXIb7I/e697ee0d0ca7839a742dc361122c8c9d/ABN_AMRO_Factsheet_2016_Q1.xlsx"),
    ("2016-Q4", "Factsheet 2016 Q4 updated segmentation", "https://assets.ctfassets.net/1u811bvgvthc/5FOOKmmRGaWzOeRynusrpi/4c7d7d905737e73fc61c1106791cd6e8/ABN_AMRO_Factsheet_2016_Q4_-_updated_for_new_segmentation.xlsx"),
    ("2018-Q1", "Factsheet 2018 Q1 restated", "https://assets.ctfassets.net/1u811bvgvthc/1PuPAM6i1jCm1T3uoRkZzW/333e60cba35a8b9f4546eb431892d4b8/ABN_AMRO_Factsheet_Q1_2018__Restated_.xlsx"),
    ("2019-Q4", "Factsheet 2019 Q4", "https://assets.ctfassets.net/1u811bvgvthc/4WRJtpio5j27cSTQlmHgtN/4aeef72df1f2b596aea8e4445dac1138/ABN_AMRO_Factsheet_2019_Q4__2_.xlsx"),
    ("2021-Q4", "Factsheet 2021 Q4 new reporting structure", "https://assets.ctfassets.net/1u811bvgvthc/4qIOrmfesGYSTMkutAAIuk/1402e46bd72d2bb4b2713d1156330134/ABN_AMRO_Q4_2021_Factsheets_-_new_reporting_structure.xlsx"),
    ("2026-Q1", "Factsheet 2026 Q1", "https://assets.ctfassets.net/1u811bvgvthc/4WnEgk8vQdDaiR21JHFBGS/37896043f4465543871c346f6bd75d05/ABN_AMRO_Q1_2026_-_Factsheet.xlsx"),
    ("2026-Q2", "Factsheet 2026 Q2", "https://assets.ctfassets.net/1u811bvgvthc/3NXVEnkipu3eJEBz2RFSfu/c7b45bb6ed809320f23d5ae47fcf58ea/ABN_AMRO_Q2_2026_-_Factsheet.xlsx"),
]


def seeded_catalog():
    result = []
    for period, label, url in KNOWN_DIRECT:
        result.append({
            "period": period, "publication": "Direct official archive link",
            "document_label": label,
            "version_review": "Review alternative/restated" if (
                "restated" in label.lower() or "new reporting" in label.lower()
                or "updated" in label.lower()
            ) else "Original publication",
            "source_url": url,
            "archive_url": ARCHIVE + "?selectedTab=" + period[:4],
            "sha256": "", "size_bytes": "", "tab_count": "",
            "workbook_integrity": "", "download_status": "pending",
            "review_status": "4-eyes review required",
            "retrieval_time_utc": "",
        })
    return result


FIELDS = [
    "period", "publication", "document_label", "version_review",
    "source_url", "archive_url", "sha256", "size_bytes", "tab_count",
    "workbook_integrity", "download_status", "review_status", "retrieval_time_utc",
]


def quarter_ids():
    return [f"{year}-Q{q}" for year in range(2016, 2027)
            for q in range(1, 5) if (year, q) <= LAST]


def _period(text):
    compact = re.sub(r"\s+", " ", text)
    found = re.search(r"\b(20(?:1[6-9]|2[0-6]))\s*[-/_ ]*Q([1-4])\b", compact, re.I)
    if not found:
        found = re.search(r"\bQ([1-4])\s*[-/_ ]*(20(?:1[6-9]|2[0-6]))\b", compact, re.I)
        return f"{found.group(2)}-Q{found.group(1)}" if found else None
    return f"{found.group(1)}-Q{found.group(2)}"


def catalog(html):
    soup = BeautifulSoup(html, "html.parser")
    listed = []
    seen = set()
    for tag in soup.select("a[href]"):
        href = urljoin(ARCHIVE, tag.get("href", "").strip())
        label = tag.get_text(" ", strip=True)
        if not (href.lower().split("?")[0].endswith(".xlsx") and
                "factsheet" in (label + " " + href).lower()):
            continue
        host = urlparse(href).netloc
        if host not in {"assets.ctfassets.net", "downloads.ctfassets.net"}:
            continue
        parent = tag.find_parent("tr")
        parent_text = parent.get_text(" ", strip=True) if parent else ""
        period = _period(label) or _period(href) or _period(parent_text)
        if period not in quarter_ids() or href in seen:
            continue
        seen.add(href)
        version = "Review alternative/restated" if (
            re.search(r"updated|restated|new reporting structure", label, re.I)
            or re.search(r"updated|restated|new.reporting.structure", href, re.I)
        ) else "Original publication"
        listed.append({
            "period": period, "publication": parent_text[:60],
            "document_label": label, "version_review": version,
            "source_url": href,
            "archive_url": ARCHIVE + "?selectedTab=" + period[:4],
            "sha256": "", "size_bytes": "", "tab_count": "",
            "workbook_integrity": "", "download_status": "pending",
            "review_status": "4-eyes review required",
            "retrieval_time_utc": "",
        })
    return sorted(listed, key=lambda r: (r["period"], r["version_review"], r["document_label"]))


def retrieve(session, row, output):
    filename = row["period"] + ("_ALTERNATIVE" if row["version_review"] != "Original publication" else "")
    path = output / (filename + ".xlsx")
    if path.exists():
        filename += "_" + hashlib.sha256(row["source_url"].encode()).hexdigest()[:8]
        path = output / (filename + ".xlsx")
    try:
        with session.get(row["source_url"], timeout=50, headers=UA, stream=True) as response:
            response.raise_for_status()
            raw = bytearray()
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if chunk:
                    raw.extend(chunk)
                if len(raw) > 12_000_000:
                    raise ValueError("File >12 MB; source needs manual approval.")
        blob = bytes(raw)
        row["size_bytes"] = len(blob)
        row["sha256"] = hashlib.sha256(blob).hexdigest()
        with zipfile.ZipFile(io.BytesIO(blob)) as workbook:
            names = workbook.namelist()
            if "xl/workbook.xml" not in names:
                raise ValueError("Missing OOXML xl/workbook.xml.")
            if workbook.testzip() is not None:
                raise ValueError("Corrupt entry in OOXML ZIP container.")
            data = workbook.read("xl/workbook.xml")
            row["tab_count"] = len(re.findall(rb"<(?:[A-Za-z0-9_]+:)?sheet\b", data))
            if int(row["tab_count"]) < 1:
                raise ValueError("No workbook sheet metadata.")
        row["workbook_integrity"] = "Valid OOXML container"
        row["download_status"] = "Downloaded and ZIP-checked"
        path.write_bytes(blob)
    except Exception as ex:
        row["workbook_integrity"] = str(ex)[:250]
        row["download_status"] = "FAILED"
        if path.exists():
            path.unlink()
    row["retrieval_time_utc"] = datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="research/evidence")
    args = parser.parse_args()
    base = Path(args.out)
    originals = base / "original_workbooks"
    originals.mkdir(parents=True, exist_ok=True)
    with requests.Session() as session:
        records = []
        archive_error = None
        try:
            response = session.get(ARCHIVE, timeout=22, headers=UA)
            response.raise_for_status()
            records = catalog(response.text)
        except requests.RequestException as error:
            archive_error = str(error)
            print("WARNING: Public archive blocked direct retrieval: " + archive_error, flush=True)
        # Retain an auditable subset of exact URLs verified from the official
        # indexed archive even if the website denies automated scraping.
        by_url = {r["source_url"]: r for r in records}
        for entry in seeded_catalog():
            by_url.setdefault(entry["source_url"], entry)
        records = sorted(by_url.values(), key=lambda r: (r["period"],r["document_label"]))
        for idx, entry in enumerate(records):
            print(f"{idx + 1}/{len(records)} {entry['period']} {entry['document_label'][:80]}", flush=True)
            retrieve(session, entry, originals)
            time.sleep(0.08)

    with (base / "source_manifest.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)
    periods = Counter(row["period"] for row in records)
    missing = [q for q in quarter_ids() if q not in periods]
    failed = [row["period"] + ": " + row["document_label"]
              for row in records if row["download_status"] == "FAILED"]
    bad_versions = [row["period"] + ": " + row["document_label"]
                    for row in records if row["version_review"] != "Original publication"]
    with (base / "REVIEW_SUMMARY.md").open("w", encoding="utf-8") as file:
        file.write(
            "# ABN AMRO historical factsheets — public retrieval, NOT approved normalized data\n\n"
            f"Retrieved at {datetime.now(timezone.utc).isoformat()}\n\n"
            f"Archive: {ARCHIVE}\n\n"
            f"Expected quarters: {len(quarter_ids())} (2016 Q1–2026 Q2)\n"
            f"Archive-listed distinct quarters: {len(periods)}\n"
            f"Archived workbook variants: {len(records)}\n"
            f"Passed OOXML container validation: {len(records)-len(failed)}\n"
            f"Missing quarter indexes: {', '.join(missing) or 'None'}\n"
            f"Failed downloads: {', '.join(failed) or 'None'}\n"
            f"Restated/alternative versions needing review: {', '.join(bad_versions) or 'None'}\n\n"
            "IMPORTANT: Downloading and ZIP-checking do NOT validate reporting line definitions, "
            "comparability, currency, units, periods, restatements, or correctness of financial "
            "figures. No numeric extraction has been approved or used in the app. "
            "Use source_manifest.csv for the four-eyes review, then build an approved "
            "line-level extraction and reconciliation map separately.\n"
        )
    print(f"Expected {len(quarter_ids())}; distinct archive-linked {len(periods)}; "
          f"download errors {len(failed)}; files {len(records)}", flush=True)
    if missing or failed:
        # Preserve the provenance inventory as an explicitly incomplete
        # research artifact; never mark this as a validated historical panel.
        print("INCOMPLETE SOURCE COVERAGE — DO NOT USE FOR FORECASTING", flush=True)


if __name__ == "__main__":
    main()
