"""Small source-data tests for ABN AMRO quarterly mode (stdlib + pandas)."""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
g = pd.read_csv(ROOT / "data" / "abn_quarterly.csv", parse_dates=["date"])
s = pd.read_csv(ROOT / "data" / "abn_segments_quarterly.csv", parse_dates=["date"])
assert len(g) == 10
assert g["date"].max() == pd.Timestamp("2026-06-30")
assert g["loans_m"].notna().sum() == 7
assert s["date"].nunique() == 7
for field in ["loans_m", "deposits_m", "rwa_m"]:
    actual = g.set_index("date")[field]
    parts = s.groupby("date")[field].sum()
    assert ((parts - actual.loc[parts.index]).abs() < 0.01).all(), field
latest = g.iloc[-1]
assert abs(latest["net_profit_m"] - 780.531615084) < 0.00001
assert abs(latest["cet1_ratio_pct"] - 15.859229928) < 0.00001
assert pd.isna(g.iloc[0]["loans_m"])
print("Quarterly source-data reconciliation passed.")
