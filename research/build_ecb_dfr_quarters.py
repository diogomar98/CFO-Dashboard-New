#!/usr/bin/env python3
"""Create dated 2021–2026 ECB Deposit Facility Rate quarterly calendar averages.

The ECB FM.B...DFR.LEV series reports RATE CHANGES, not every day.
We carry each officially effective rate forward by calendar day, then average.
Only past and same-quarter rates are used. No future rate path invented.
"""
import csv
import hashlib
import io
import json
from datetime import date, timedelta
from pathlib import Path

import requests

URL="https://data-api.ecb.europa.eu/service/data/FM/B.U2.EUR.4F.KR.DFR.LEV?startPeriod=2019-01-01&endPeriod=2026-06-30&format=csvdata"
OUT=Path("research/ecb_dfr_evidence")
OUT.mkdir(parents=True,exist_ok=True)

def main():
    r=requests.get(URL,timeout=35,headers={"Accept":"text/csv","User-Agent":"CFO-public-rates-research/1.0"})
    r.raise_for_status()
    digest=hashlib.sha256(r.content).hexdigest()
    (OUT/"ecb_original.csv").write_bytes(r.content)
    reader=list(csv.DictReader(io.StringIO(r.text)))
    assert reader and all("TIME_PERIOD" in row and "OBS_VALUE" in row for row in reader)
    events=[]
    for row in reader:
        try:
            events.append((date.fromisoformat(row["TIME_PERIOD"]),float(row["OBS_VALUE"])))
        except (ValueError,TypeError,KeyError):
            continue
    events.sort()
    assert len(events)>=10, f"Too few official ECB rate change observations: {len(events)}"
    start=date(2021,1,1); end=date(2026,6,30)
    initial=[v for d,v in events if d<=start]
    assert initial, "Missing policy rate effective at start of Group sample"
    rate=initial[-1];day=start; index=0
    while index<len(events) and events[index][0]<=start: index+=1
    sums={};counts={};ends={}
    while day<=end:
        while index<len(events) and events[index][0]<=day:
            rate=events[index][1];index+=1
        period=f"{day.year}-Q{(day.month-1)//3+1}"
        sums[period]=sums.get(period,0.0)+rate
        counts[period]=counts.get(period,0)+1
        ends[period]=rate
        day+=timedelta(days=1)
    rows=[]
    for q in sorted(sums):
        y,n=q.split("-Q");y=int(y);n=int(n)
        from calendar import monthrange
        m=n*3
        date_end=f"{y}-{m:02d}-{monthrange(y,m)[1]}"
        rows.append({
            "date":date_end,
            "dfr_qavg_pct":round(sums[q]/counts[q],9),
            "dfr_qend_pct":ends[q],
            "days":counts[q],
            "source_url":URL,
            "source_sha256":digest,
            "method":"calendar-day effective-rate average from ECB raw rate-change observations",
        })
    assert len(rows)==22 and rows[0]["date"]=="2021-03-31" and rows[-1]["date"]=="2026-06-30"
    assert abs(rows[0]["dfr_qavg_pct"]+0.5)<.00001, "2021Q1 ECB published -0.50pct anchor not recovered"
    assert all(-1.0<=r["dfr_qavg_pct"]<=6.0 for r in rows)
    with (OUT/"quarterly_dfr.csv").open("w",newline="",encoding="utf-8") as file:
        writer=csv.DictWriter(file,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print("ECB_QUARTERS_JSON "+json.dumps(rows,separators=(",",":")),flush=True)
    print("ECB_AUDIT "+json.dumps({
        "events":len(events),"quarter_count":len(rows),"source_sha256":digest,
        "source":URL,"sample_start":rows[0],"sample_end":rows[-1],
    }),flush=True)
if __name__=="__main__":main()
