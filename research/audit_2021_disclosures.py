#!/usr/bin/env python3
"""Independent disclosure-shape/figure audit for public ABN factsheets since 2021.

Not a forecasting input. Only exact workbook cells and header context are
reported. All ambiguous lines are explicitly kept UNAPPROVED.
"""
import csv
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path

import openpyxl
import requests

from fetch_public_abn_sources import KNOWN_DIRECT, UA

OUT=Path("research/2021_audit_output")
OUT.mkdir(parents=True,exist_ok=True)
TERMS={
 "NII":re.compile(r"^(?:net\s+interest\s+income|interest\s+income\s*,?\s*net)$",re.I),
 "NIM":re.compile(r"^(?:net\s+interest\s+margin|nim)(?:\s*\(.*\))?$",re.I),
 "NET_PROFIT":re.compile(r"^(?:net\s+(?:profit|result)|profit\s+for\s+the\s+period)$",re.I),
 "LOANS":re.compile(r"^(?:loans\s+and\s+advances\s+to\s+customers|customer\s+loans)$",re.I),
 "DEPOSITS":re.compile(r"^(?:due\s+to\s+customers|customer\s+deposits)$",re.I),
 "CET1":re.compile(r"^(?:cet1\s+ratio|common\s+equity\s+tier\s*1\s+ratio)$",re.I),
}
def clean(v):
 return re.sub(r"\s+"," ",str(v or "").replace("\n"," ")).strip()

def source_set():
 return [(q,label,url) for q,label,url in KNOWN_DIRECT if int(q[:4])>=2021]

def audit_file(q,label,url,session):
 response=session.get(url,headers=UA,timeout=38)
 response.raise_for_status()
 raw=response.content
 digest=hashlib.sha256(raw).hexdigest()
 book=openpyxl.load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
 sheets=book.sheetnames
 candidates=[]
 for sheet in book:
  try:
   for rn,row in enumerate(sheet.iter_rows(max_row=min(500,sheet.max_row or 500),
                                          max_col=min(42,sheet.max_column or 42),
                                          values_only=True),start=1):
    for idx,v in enumerate(row):
     if not isinstance(v,str) or len(v)>120: continue
     text=clean(v).strip(" :-")
     match=next((k for k,rx in TERMS.items() if rx.fullmatch(text)),None)
     if not match: continue
     vals=[]
     for col in range(idx+1,min(len(row),idx+19)):
      candidate=row[col]
      if isinstance(candidate,(int,float)) and not isinstance(candidate,bool):
       vals.append({"col":col+1,"value":round(float(candidate),6)})
     candidates.append({
      "period":q, "document":label,"metric":match,
      "sheet":sheet.title,"cell":f"{openpyxl.utils.get_column_letter(idx+1)}{rn}",
      "row_label":text,"right_numbers":json.dumps(vals[:9]),
      "source_url":url,"sha256":digest,
     })
  except Exception as exc:
   print(f"SHEET_SCAN_ERROR {q} {sheet.title} {type(exc).__name__}:{str(exc)[:100]}")
 book.close()
 return sheets,candidates

def ecb_links(session):
 links=[
  ("ECB rate history user-friendly","https://www.ecb.europa.eu/stats/policy_and_exchange_rates/key_ecb_interest_rates/html/index.en.html"),
  ("ECB official API DFR","https://data-api.ecb.europa.eu/service/data/FM/B.U2.EUR.4F.KR.DFR.LEV?startPeriod=2021-01-01&endPeriod=2026-06-30&format=csvdata"),
  ("ECB original portal","https://data.ecb.europa.eu/key-figures/ecb-interest-rates-and-exchange-rates/key-ecb-interest-rates"),
 ]
 results=[]
 for label,url in links:
  try:
   r=session.get(url,timeout=20,headers=UA)
   results.append({"label":label,"url":url,"status":r.status_code,"bytes":len(r.content),"content_type":r.headers.get("Content-Type","")})
  except Exception as exc:
   results.append({"label":label,"url":url,"status":"ERROR","detail":str(exc)[:190]})
 return results

def main():
 sources=source_set()
 tab_rows=[]
 candidates=[]
 with requests.Session() as session:
  for ix,(q,label,url) in enumerate(sources):
   print(f"START {ix+1}/{len(sources)} {q} {label}",flush=True)
   try:
    tabs,matched=audit_file(q,label,url,session)
    tab_rows.append({"period":q,"source_label":label,"source_url":url,"tabs":len(tabs),"tab_names":" | ".join(tabs),
                     "candidates":len(matched),"status":"OOXML scanned"})
    candidates.extend(matched)
    print(f"AUDIT_SUMMARY {q} {label}: {len(tabs)} tabs; {len(matched)} exact-name candidate rows; "
          f"matches by line: {dict(Counter(x['metric'] for x in matched))}",flush=True)
    if q in ("2021-Q4","2022-Q1","2025-Q4","2026-Q2"):
     for x in matched[:45]:
      print(f"CANDIDATE {q} {label} {x['metric']} {x['sheet']}:{x['cell']} "
            f"{x['row_label']} RIGHT={x['right_numbers']}",flush=True)
   except Exception as exc:
    tab_rows.append({"period":q,"source_label":label,"source_url":url,
                     "tabs":0,"tab_names":"","candidates":0,"status":str(exc)[:170]})
    print(f"FAIL {q} {label} {exc}",flush=True)
  checks=ecb_links(session)
  for c in checks:
   print("ECB_LINK "+json.dumps(c),flush=True)
 with (OUT/"sheet_inventory.csv").open("w",newline="",encoding="utf-8") as o:
  writer=csv.DictWriter(o,fieldnames=tab_rows[0].keys())
  writer.writeheader();writer.writerows(tab_rows)
 if candidates:
  with (OUT/"exact_label_candidates.csv").open("w",newline="",encoding="utf-8") as o:
   writer=csv.DictWriter(o,fieldnames=candidates[0].keys())
   writer.writeheader();writer.writerows(candidates)
 (OUT/"ecb_links.json").write_text(json.dumps(checks,indent=2),encoding="utf-8")
 (OUT/"audit_scope.md").write_text(
  "# 2021-on public factsheet source audit\n"
  f"Public workbook variants scanned: {len(sources)}; distinct periods: {len(set(x[0] for x in sources))}.\n\n"
  "The exact_label_candidates.csv contains POSSIBLE source cell locations, NOT approved "
  "numeric data. Figures in right_numbers have not been associated with a named quarter, "
  "currency, unit or Group scope. Adjacent-workbook and independent PDF value "
  "reconciliation are required before use in the model.\n\n"
  "Starting in 2021 does not eliminate reporting-method changes: 2021 Q4 has "
  "two reporting-structure versions, and 2026 acquisition impacts also need assessment.\n",
  encoding="utf-8")
 print(f"FINAL {len(tab_rows)} workbooks; {len(candidates)} candidates; "
       f"{len(set(x['period'] for x in tab_rows))} quarters",flush=True)

if __name__=="__main__":
 main()
