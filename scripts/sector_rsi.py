"""
Sector RSI14 analysis for daily VN market dashboard.

For each sector in _SECTOR_TICKERS, compute RSI14 of daily PX_LAST.
Output per sector: sector, strength (mean RSI14), strength_10d_chg,
breadth_pct (% tickers with RSI14 > 50), tickers (all, sorted by RSI14 desc).
"""

import pandas as pd
import numpy as np

LOOKBACK_START = "2025-10-01"

_SECTOR_TICKERS = {
    "Banking":        ["ACB","BID","CTG","HDB","MBB","MSB","SHB","STB","TCB","TPB","VCB","VPB"],
    "Real Estate":    ["CEO","CII","DIG","DXG","HDC","KDH","NLG","NVL","PDR","TCH"],
    "Industrial Park":["KBC","IDC","BCM","VGC"],
    "Steel":          ["HPG","HSG","NKG","SMC","VGS"],
    "Retail":         ["DGW","FRT","MWG","PET","PNJ"],
    "Fertilizer":     ["BFC","CSV","DCM","DGC","DPM","LAS"],
    "Oil & Gas":      ["BSR","GAS","OIL","PLX","PVD","PVS","PVT"],
    "Construction":   ["CTD","FCN","HBC","HHV","LCG","VCG"],
    "Securities":     ["BSI","CTS","FTS","HCM","MBS","SHS","SSI","TCX","VCI","VCK","VDS","VIX","VND","VPX"],
    "Consumer":       ["MSN","QNS","SBT","VNM"],
    "VinGroup":       ["VIC","VHM","VRE","VPL"],
    "GEX Family":     ["EVF","GEE","GEL","GEX","VIX"],
    "Tech":           ["CMG","CTR","FOX","FPT","VGI","VTP"],
    "Transport":      ["GMD","HAH","PHP","VOS"],
    "Textile":        ["GIL","MSH","TCM","TNG","VGT"],
    "Rubber":         ["DPR","DRI","GVR","PHR","SIP"],
    "Fishery":        ["ANV","IDI","VHC"],
    "Electricity":    ["GEG","NT2","PC1","POW","PPC","REE","TV2"],
}

all_tickers = list(set(t for tickers in _SECTOR_TICKERS.values() for t in tickers))
tickers_str = "','".join(all_tickers)

df = sql_query(f"""
    SELECT TICKER, TRADE_DATE, PX_LAST
    FROM Market_Data
    WHERE TRADE_DATE >= '{LOOKBACK_START}'
      AND TICKER IN ('{tickers_str}')
      AND PX_LAST IS NOT NULL AND PX_LAST > 0
""")

df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"])
df = df.sort_values(["TICKER", "TRADE_DATE"])

def rsi14(series):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

df["RSI14"] = df.groupby("TICKER")["PX_LAST"].transform(rsi14)

latest_date = df["TRADE_DATE"].max()
all_dates   = sorted(df["TRADE_DATE"].unique())
date_10d_ago = all_dates[-11] if len(all_dates) >= 11 else all_dates[0]

latest_df = df[df["TRADE_DATE"] == latest_date].copy()
df_10d    = df[df["TRADE_DATE"] == date_10d_ago].copy()

sector_analysis = []
for sector, tickers in _SECTOR_TICKERS.items():
    rows = latest_df[latest_df["TICKER"].isin(tickers)]
    if rows.empty:
        continue
    strength    = rows["RSI14"].mean()
    breadth_pct = (rows["RSI14"] > 50).mean() * 100
    all_t       = rows.sort_values("RSI14", ascending=False)["TICKER"].tolist()

    rows_10d = df_10d[df_10d["TICKER"].isin(tickers)]
    strength_10d_chg = round(strength - rows_10d["RSI14"].mean(), 1) if not rows_10d.empty else None

    sector_analysis.append({
        "sector":           sector,
        "strength":         round(strength, 1),
        "strength_10d_chg": strength_10d_chg,
        "breadth_pct":      round(breadth_pct, 0),
        "tickers":          all_t,
    })

result = sorted(sector_analysis, key=lambda x: x["strength"], reverse=True)
