"""
VNIndex snapshot for daily VN market dashboard.
Returns latest_date and VNIndex close/change only.
"""

import pandas as pd
import numpy as np

LOOKBACK_START = "2026-04-01"

df_idx = sql_query(f"""
    SELECT TRADINGDATE as TRADE_DATE, CLOSEINDEX as IDX_CLOSE,
           INDEXCHANGE, PERCENTINDEXCHANGE
    FROM MarketIndex
    WHERE TRADINGDATE >= '{LOOKBACK_START}' AND COMGROUPCODE = 'VNINDEX'
""")

df_idx["TRADE_DATE"] = pd.to_datetime(df_idx["TRADE_DATE"])
df_idx = df_idx.sort_values("TRADE_DATE")

latest = df_idx["TRADE_DATE"].max()
row    = df_idx[df_idx["TRADE_DATE"] == latest].iloc[0]
prev   = df_idx[df_idx["TRADE_DATE"] < latest].iloc[-1]

result = {
    "latest_date": str(latest.date()),
    "vnindex": {
        "close":      round(float(row["IDX_CLOSE"]), 2),
        "change":     round(float(row["INDEXCHANGE"]) if pd.notna(row["INDEXCHANGE"]) else float(row["IDX_CLOSE"] - prev["IDX_CLOSE"]), 2),
        "change_pct": round(float(row["PERCENTINDEXCHANGE"]) if pd.notna(row["PERCENTINDEXCHANGE"]) else float((row["IDX_CLOSE"] / prev["IDX_CLOSE"] - 1) * 100), 2),
    },
}
