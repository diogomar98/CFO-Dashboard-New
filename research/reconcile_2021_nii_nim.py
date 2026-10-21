#!/usr/bin/env python3
"""Independent public Group NII/NIM dual-source reconciliation for 2021–Q2 2026.

Eyes 1: the observation in its own official ABN factsheet, sheet 1.1, column C.
Eyes 2: the *same quarter* in the next officially published factsheet, column D.
Eyes 3: selected independent ABN press releases with rounding thresholds.
Both Q4 2021 variants are included; no restatement is silently substituted.

Explicit limits: this cannot validate segment comparability, interest-earning
assets, acquisition adjustments, forecasts, or 99% interval coverage.
"""
import csv
import io
import json
import re
from pathlib import Path
from collections import Counter

import openpyxl
import requests

from fetch_public_abn_sources import KNOWN_DIRECT, UA

OUT=Path("research/2021_reconciliation_output")
OUT.mkdir(exist_ok=True,parents=True)
PRESS={
    "2022-Q1": {"NII_EUR_M": (1310.0, "https://www.abnamro.com/en/news/abn-amro-reports-net-profit-of-eur-295-million-in-the-first-quarter")},
    "2022-Q4": {"NII_EUR_M": (1564.0, "https://www.abnamro.com/en/news/abn-amro-reports-net-profit-of-eur-1-876-million-for-fy2022-and-share-buyback")},
    "2023-Q1": {"NII_EUR_M": (1620.0, "https://www.abnamro.com/en/news/abn-amro-reports-net-profit-of-eur-523-million-for-q1-2023")},
    "2026-Q2": {"NII_EUR_M": (1700.0, "https://www.abnamro.com/en/news/abn-amro-posts-net-profit-of-eur-781-million-in-q2-2026"),
                "NIM_BPS": (149.0, "https://www.abnamro.com/en/investor-relations/information/all-financial-reports")},
}

def chosen_links():
    links={}
    for q,label,url in KNOWN_DIRECT:
        if int(q[:4]) < 2021: continue
        if q == "2021-Q4":
            if "new reporting" in label.lower(): links[q]=(label,url)
        else:
            links[q]=(label,url)
    expected=[f"{y}-Q{k}" for y in range(2021,2027) for k in range(1,5) if (y,k)<=(2026,2)]
    assert len(links)==len(expected)==22
    assert all(q in links for q in expected)
    return links,expected

def parse(source,label):
    wb=openpyxl.load_workbook(io.BytesIO(source),read_only=True,data_only=True)
    opts=[s for s in wb if s.title.strip().lower().startswith("1.1")]
    if len(opts)!=1: raise ValueError(f"{label}: expected unique Group quarterly P&L tab, got {[x.title for x in opts]}")
    ws=opts[0];matches={}
    for row in ws.iter_rows(min_row=1,max_row=70,max_col=5):
        title=row[1].value
        if not isinstance(title,str):continue
        title=re.sub(r"\s+"," ",title).strip().lower()
        if title=="net interest income": key="NII_EUR_M"
        elif title=="nim (in bps)" or title=="nim":key="NIM_BPS"
        else: continue
        if key in matches: raise ValueError(f"Ambiguous Group label {key} in {label}")
        values=[row[2].value,row[3].value]
        if any(not isinstance(v,(int,float)) or isinstance(v,bool) for v in values):
            raise ValueError(f"Non-numeric Group {key} in {label}")
        matches[key]={"latest":float(values[0]),"prior":float(values[1]),
                      "sheet":ws.title,"current_cell":row[2].coordinate,
                      "prior_cell":row[3].coordinate}
    wb.close()
    if set(matches)!={"NII_EUR_M","NIM_BPS"}:
        raise ValueError(f"Missing Group NII or NIM: {label}: {list(matches)}")
    return matches

def main():
    links,quarters=chosen_links()
    per_period={}
    with requests.Session() as session:
        for q in quarters:
            label,url=links[q]
            data=session.get(url,headers=UA,timeout=35)
            data.raise_for_status()
            record=parse(data.content,label)
            per_period[q]={"source_label":label,"source_url":url,"metrics":record}
            print(f"SOURCED {q} Group NII €{record['NII_EUR_M']['latest']:.3f}m "
                  f"NIM {record['NIM_BPS']['latest']:.3f}bps",flush=True)
        # Same-quarter old/new structure check: public independent workbooks
        original=[(label,url) for q,label,url in KNOWN_DIRECT
                  if q=="2021-Q4" and "original" in label.lower()]
        assert len(original)==1
        response=session.get(original[0][1],headers=UA,timeout=35)
        response.raise_for_status()
        original_data=parse(response.content,"2021 Q4 original structure")

    comparisons=[]
    for idx,q in enumerate(quarters):
        for metric in ("NII_EUR_M","NIM_BPS"):
            value=per_period[q]["metrics"][metric]["latest"]
            if idx<len(quarters)-1:
                next_q=quarters[idx+1]
                next_value=per_period[next_q]["metrics"][metric]["prior"]
                difference=value-next_value
                passed=abs(difference)<0.005
                comparisons.append({
                  "period":q,"metric":metric,"check":"Two separate published workbooks: Q observed vs successor Q prior",
                  "workbook_1_value":round(value,6),
                  "workbook_2_value":round(next_value,6),
                  "absolute_difference":round(abs(difference),6),
                  "status":"PASS" if passed else "REVIEW",
                  "first_source":per_period[q]["source_url"],
                  "first_sheet_cell":per_period[q]["metrics"][metric]["sheet"]+":"+per_period[q]["metrics"][metric]["current_cell"],
                  "second_source":per_period[next_q]["source_url"],
                  "second_sheet_cell":per_period[next_q]["metrics"][metric]["sheet"]+":"+per_period[next_q]["metrics"][metric]["prior_cell"],
                })
            if q in PRESS and metric in PRESS[q]:
                target,public_link=PRESS[q][metric]
                diff=abs(value-target)
                comparisons.append({
                  "period":q,"metric":metric,"check":"ABN press release independently rounded disclosure",
                  "workbook_1_value":round(value,6),
                  "workbook_2_value":target,
                  "absolute_difference":round(diff,6),
                  "status":"PASS" if diff <= .5 else "REVIEW",
                  "first_source":per_period[q]["source_url"],
                  "first_sheet_cell":per_period[q]["metrics"][metric]["sheet"]+":"+per_period[q]["metrics"][metric]["current_cell"],
                  "second_source":public_link,"second_sheet_cell":"ABN investor release narrative",
                })

    for metric in ("NII_EUR_M","NIM_BPS"):
        diff=abs(per_period["2021-Q4"]["metrics"][metric]["latest"]-original_data[metric]["latest"])
        comparisons.append({
          "period":"2021-Q4","metric":metric,"check":"Original 2021 Q4 vs new-reporting-structure workbook: Group value",
          "workbook_1_value":round(per_period["2021-Q4"]["metrics"][metric]["latest"],6),
          "workbook_2_value":round(original_data[metric]["latest"],6),
          "absolute_difference":round(diff,6),
          "status":"PASS" if diff<.005 else "REVIEW",
          "first_source":per_period["2021-Q4"]["source_url"],
          "first_sheet_cell":per_period["2021-Q4"]["metrics"][metric]["sheet"]+":"+per_period["2021-Q4"]["metrics"][metric]["current_cell"],
          "second_source":original[0][1],
          "second_sheet_cell":original_data[metric]["sheet"]+":"+original_data[metric]["current_cell"],
        })

    with (OUT/"independent_cross_checks.csv").open("w",newline="",encoding="utf-8") as file:
      writer=csv.DictWriter(file,fieldnames=list(comparisons[0].keys()));writer.writeheader();writer.writerows(comparisons)
    series=[]
    for q in quarters:
      x=per_period[q]
      series.append({
        "quarter":q,"nii_m":round(x["metrics"]["NII_EUR_M"]["latest"],6),
        "nim_bps":round(x["metrics"]["NIM_BPS"]["latest"],6),
        "nii_cell":x["metrics"]["NII_EUR_M"]["sheet"]+":"+x["metrics"]["NII_EUR_M"]["current_cell"],
        "nim_cell":x["metrics"]["NIM_BPS"]["sheet"]+":"+x["metrics"]["NIM_BPS"]["current_cell"],
        "source_url":x["source_url"],"review_status":"CROSS-CHECKED — NOT MODEL-APPROVED",
      })
    with (OUT/"group_nii_nim_candidate_2021_2026.csv").open("w",newline="",encoding="utf-8") as file:
      writer=csv.DictWriter(file,fieldnames=list(series[0].keys()));writer.writeheader();writer.writerows(series)
    checks=Counter(x["status"] for x in comparisons)
    issues=[x for x in comparisons if x["status"]!="PASS"]
    (OUT/"RECONCILIATION_SUMMARY.md").write_text(
      "# Independent cross-reconciliation · ABN Group NII and NIM (2021 Q1–2026 Q2)\n\n"
      f"22 quarters. {len(comparisons)} checks: {dict(checks)}.\n\n"
      "CFO caution: Checks validate extracted group NII/NIM figures against the immediate "
      "successor factsheet and selected ABN official press releases. They do NOT validate "
      "loan/deposit growth, interest-earning assets, all capital definitions, 2026 NIBC "
      "perimeter or forecasting stability. The new-structure Q4 2021 workbook was selected "
      "for Group NII/NIM only because of the explicit two-version cross-check. "
      "No 99% forecast interval has been estimated or empirically validated.\n\n"
      "Review items: "+json.dumps(issues[:25],indent=2)+"\n",
      encoding="utf-8")
    print("FINAL_RECONCILIATION "+json.dumps({"quarters":len(quarters),"checks":len(comparisons),
                                              "statuses":dict(checks),"exceptions":issues[:12]}),flush=True)

if __name__=="__main__":
 main()
