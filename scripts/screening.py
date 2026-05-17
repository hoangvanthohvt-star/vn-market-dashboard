"""
Screening payload for daily VN market dashboard.

This file is sent verbatim to the MCP `execute_python` tool, which runs it
against MSSQL/MongoDB and returns the `result` dict as JSON.

Screen rule (user-defined):
    price > EMA20 > EMA50  AND  RS(stock vs VNINDEX) > MA50(RS)
    + liquidity filter: 20d avg turnover > 1bn VND

Output also includes market-overview context (VNINDEX level, breadth, sectors).
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

LOOKBACK_START = "2025-10-01"
LIQUIDITY_MIN_VND = 1_000_000_000
TOP_N = 40

idx = sql_query(
    f"SELECT TRADINGDATE, CLOSEINDEX, INDEXCHANGE, PERCENTINDEXCHANGE "
    f"FROM MarketIndex WHERE COMGROUPCODE='VNINDEX' AND TRADINGDATE >= '{LOOKBACK_START}'"
)

df = sql_query(f"""
    SELECT TICKER, TRADE_DATE, PX_LAST, VOLUME, MKT_CAP
    FROM Market_Data
    WHERE TRADE_DATE >= '{LOOKBACK_START}'
      AND PX_LAST IS NOT NULL AND PX_LAST > 0 AND VOLUME > 0
""")

idx = idx.rename(columns={"TRADINGDATE": "TRADE_DATE", "CLOSEINDEX": "IDX_CLOSE"})
idx["TRADE_DATE"] = pd.to_datetime(idx["TRADE_DATE"]).dt.normalize()
df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"])

df = df.sort_values(["TICKER", "TRADE_DATE"])
df["TURNOVER"] = df["PX_LAST"] * df["VOLUME"]

g = df.groupby("TICKER", group_keys=False)
df["TURNOVER_MA20"] = g["TURNOVER"].transform(lambda x: x.rolling(20).mean())
df["EMA20"] = g["PX_LAST"].transform(lambda x: x.ewm(span=20, adjust=False).mean())
df["EMA50"] = g["PX_LAST"].transform(lambda x: x.ewm(span=50, adjust=False).mean())

df = df.merge(idx[["TRADE_DATE", "IDX_CLOSE"]], on="TRADE_DATE", how="left")
df["RS"] = df["PX_LAST"] / df["IDX_CLOSE"]
df = df.sort_values(["TICKER", "TRADE_DATE"])
df["RS_MA50"] = df.groupby("TICKER", group_keys=False)["RS"].transform(
    lambda x: x.rolling(50).mean()
)
df["PRICE_PCT_1D"] = g["PX_LAST"].transform(lambda x: x.pct_change() * 100)

latest = df["TRADE_DATE"].max()
last = df[df["TRADE_DATE"] == latest].copy()

mask = (
    (last["PX_LAST"] > last["EMA20"])
    & (last["EMA20"] > last["EMA50"])
    & (last["RS"] > last["RS_MA50"])
    & (last["TURNOVER_MA20"] > LIQUIDITY_MIN_VND)
)
passed = last[mask].copy()
passed["rs_strength_pct"] = (passed["RS"] / passed["RS_MA50"] - 1) * 100
passed["ema20_gap_pct"] = (passed["PX_LAST"] / passed["EMA20"] - 1) * 100
passed["ema50_gap_pct"] = (passed["PX_LAST"] / passed["EMA50"] - 1) * 100
passed["turnover_bn_vnd"] = passed["TURNOVER_MA20"] / 1e9
passed = passed.sort_values("rs_strength_pct", ascending=False)

vni_latest = idx.sort_values("TRADE_DATE").iloc[-1]
vni_prev = idx.sort_values("TRADE_DATE").iloc[-2]

screened = passed.head(TOP_N)[
    [
        "TICKER",
        "PX_LAST",
        "PRICE_PCT_1D",
        "EMA20",
        "EMA50",
        "ema20_gap_pct",
        "ema50_gap_pct",
        "rs_strength_pct",
        "turnover_bn_vnd",
        "MKT_CAP",
    ]
].round(2).to_dict("records")

result = {
    "latest_date": str(latest.date()),
    "vnindex": {
        "close": round(float(vni_latest["IDX_CLOSE"]), 2),
        "change": round(float(vni_latest["INDEXCHANGE"]) if pd.notna(vni_latest["INDEXCHANGE"]) else float(vni_latest["IDX_CLOSE"] - vni_prev["IDX_CLOSE"]), 2),
        "change_pct": round(float(vni_latest["PERCENTINDEXCHANGE"]) if pd.notna(vni_latest["PERCENTINDEXCHANGE"]) else float((vni_latest["IDX_CLOSE"] / vni_prev["IDX_CLOSE"] - 1) * 100), 2),
    },
    "universe": {
        "total_tickers": int(df["TICKER"].nunique()),
        "liquid_passed": int(len(passed)),
    },
    "screen_rules": {
        "price_gt_ema20": True,
        "ema20_gt_ema50": True,
        "rs_gt_rs_ma50": True,
        "min_turnover_vnd": LIQUIDITY_MIN_VND,
    },
    "screened": screened,
}
