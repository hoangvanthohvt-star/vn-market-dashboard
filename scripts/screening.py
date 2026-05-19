"""
Screening payload for daily VN market dashboard.

Screen rule:
    price > EMA20 > EMA50  AND  RS(stock vs VNINDEX) > MA50(RS)
    + liquidity filter: 20d avg turnover > 15bn VND
    Universe: sector watchlist (same tickers as _SECTOR_TICKERS in render.py)
    RS benchmark: VNINDEX
"""

import pandas as pd
import numpy as np

LOOKBACK_START = "2026-01-05"
LIQUIDITY_MIN_VND = 15_000_000_000  # 15 bn VND
TOP_N = 40

UNIVERSE = [
    "ACB","ANV","BCM","BFC","BID","BSI","BSR","CEO","CII","CMG",
    "CSV","CTD","CTG","CTR","CTS","DCM","DGC","DGW","DIG","DPM",
    "DPR","DRI","DXG","EVF","FCN","FOX","FPT","FRT","FTS","GAS",
    "GEE","GEG","GEL","GEX","GIL","GMD","GVR","HAH","HBC","HCM",
    "HDB","HDC","HHV","HPG","HSG","IDC","IDI","KBC","KDH","LAS",
    "LCG","MBB","MBS","MSB","MSH","MSN","MWG","NKG","NLG","NT2",
    "NVL","OIL","PC1","PDR","PET","PHP","PHR","PLX","PNJ","POW",
    "PPC","PVD","PVS","PVT","QNS","REE","SBT","SHB","SHS","SIP",
    "SMC","SSI","STB","TCB","TCH","TCM","TCX","TPB","TV2","VCB",
    "VCG","VCK","VCI","VDS","VGC","VGI","VGS","VGT","VHC","VHM",
    "VIC","VIX","VND","VNM","VOS","VPB","VPL","VPX","VRE","VTP",
]

tickers_str = "','".join(UNIVERSE)

df = sql_query(f"""
    SELECT md.TICKER, md.TRADE_DATE, md.PX_LAST, md.VOLUME, md.MKT_CAP,
           sm.VNI,
           mi.CLOSEINDEX as IDX_CLOSE, mi.INDEXCHANGE, mi.PERCENTINDEXCHANGE
    FROM Market_Data md
    LEFT JOIN Sector_Map sm  ON sm.Ticker = md.TICKER
    LEFT JOIN MarketIndex mi ON mi.TRADINGDATE = md.TRADE_DATE AND mi.COMGROUPCODE = 'VNINDEX'
    WHERE md.TRADE_DATE >= '{LOOKBACK_START}'
      AND md.TICKER IN ('{tickers_str}')
      AND md.PX_LAST IS NOT NULL AND md.PX_LAST > 0 AND md.VOLUME > 0
""")

df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"])
df["VNI"] = df["VNI"].fillna("").str.strip()
df = df.sort_values(["TICKER", "TRADE_DATE"])
df["TURNOVER"] = df["PX_LAST"] * df["VOLUME"]

g = df.groupby("TICKER", group_keys=False)
df["TURNOVER_MA20"] = g["TURNOVER"].transform(lambda x: x.rolling(20).mean())
df["EMA20"] = g["PX_LAST"].transform(lambda x: x.ewm(span=20, adjust=False).mean())
df["EMA50"] = g["PX_LAST"].transform(lambda x: x.ewm(span=50, adjust=False).mean())
df["RS"]     = df["PX_LAST"] / df["IDX_CLOSE"]
df["RS_MA50"] = df.groupby("TICKER", group_keys=False)["RS"].transform(
    lambda x: x.rolling(50).mean()
)
df["PRICE_PCT_1D"] = g["PX_LAST"].transform(lambda x: x.pct_change() * 100)

latest = df["TRADE_DATE"].max()
last   = df[df["TRADE_DATE"] == latest].copy()
last   = last.sort_values("VNI", ascending=False).drop_duplicates(subset="TICKER")

mask = (
    (last["PX_LAST"] > last["EMA20"])
    & (last["EMA20"] > last["EMA50"])
    & (last["RS"]    > last["RS_MA50"])
    & (last["TURNOVER_MA20"] > LIQUIDITY_MIN_VND)
)
passed = last[mask].copy()
passed["rs_strength_pct"] = (passed["RS"] / passed["RS_MA50"] - 1) * 100
passed["ema20_gap_pct"]   = (passed["PX_LAST"] / passed["EMA20"] - 1) * 100
passed["ema50_gap_pct"]   = (passed["PX_LAST"] / passed["EMA50"] - 1) * 100
passed["turnover_bn_vnd"] = passed["TURNOVER_MA20"] / 1e9
passed = passed.sort_values("rs_strength_pct", ascending=False)

idx_latest = df[df["TRADE_DATE"] == latest][["IDX_CLOSE","INDEXCHANGE","PERCENTINDEXCHANGE"]].dropna(subset=["IDX_CLOSE"]).iloc[0]
idx_prev   = df[df["TRADE_DATE"] == sorted(df["TRADE_DATE"].unique())[-2]][["IDX_CLOSE"]].iloc[0]

screened = passed.head(TOP_N)[
    ["TICKER", "VNI", "PX_LAST", "PRICE_PCT_1D",
     "EMA20", "EMA50", "ema20_gap_pct", "ema50_gap_pct",
     "rs_strength_pct", "turnover_bn_vnd", "MKT_CAP"]
].round(2).to_dict("records")

result = {
    "latest_date": str(latest.date()),
    "vnindex": {
        "close":      round(float(idx_latest["IDX_CLOSE"]), 2),
        "change":     round(float(idx_latest["INDEXCHANGE"]) if pd.notna(idx_latest["INDEXCHANGE"]) else float(idx_latest["IDX_CLOSE"] - idx_prev["IDX_CLOSE"]), 2),
        "change_pct": round(float(idx_latest["PERCENTINDEXCHANGE"]) if pd.notna(idx_latest["PERCENTINDEXCHANGE"]) else float((idx_latest["IDX_CLOSE"] / idx_prev["IDX_CLOSE"] - 1) * 100), 2),
    },
    "universe": {
        "total_tickers": int(df["TICKER"].nunique()),
        "liquid_passed": int(len(passed)),
    },
    "screen_rules": {
        "price_gt_ema20": True,
        "ema20_gt_ema50": True,
        "rs_gt_rs_ma50":  True,
        "min_turnover_vnd": LIQUIDITY_MIN_VND,
    },
    "screened": screened,
}
