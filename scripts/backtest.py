"""
Breakout model backtest for daily VN market dashboard.
Signal: daily close > 3%, volume > 30% vs 20d avg, price > MA50.
Universe: 111 sector watchlist tickers. Max 10 positions (most recent first).
Hold: 20 trading days. Portfolio: equal-weight mark-to-market.
"""

import pandas as pd
import numpy as np

LOOKBACK_START   = "2022-01-01"   # 3 years; 111 tickers × ~750d ≈ 83k rows
HOLD_DAYS        = 20
MAX_POSITIONS    = 10
VOLUME_SURGE     = 1.30
PRICE_SURGE      = 0.03

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
    SELECT md.TICKER, md.TRADE_DATE, md.PX_LAST, md.VOLUME,
           mi.CLOSEINDEX as IDX_CLOSE
    FROM Market_Data md
    LEFT JOIN MarketIndex mi ON mi.TRADINGDATE = md.TRADE_DATE
                             AND mi.COMGROUPCODE = 'VNINDEX'
    WHERE md.TRADE_DATE >= '{LOOKBACK_START}'
      AND md.TICKER IN ('{tickers_str}')
      AND md.PX_LAST IS NOT NULL AND md.PX_LAST > 0 AND md.VOLUME > 0
""")

df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"])
df = df.sort_values(["TICKER", "TRADE_DATE"])

g = df.groupby("TICKER", group_keys=False)
df["MA50"]     = g["PX_LAST"].transform(lambda x: x.rolling(50).mean())
df["VOL_MA20"] = g["VOLUME"].transform(lambda x: x.rolling(20).mean())
df["RET"]      = g["PX_LAST"].transform(lambda x: x.pct_change())

df["SIGNAL"] = (
    (df["RET"]     > PRICE_SURGE)  &
    (df["VOLUME"]  > VOLUME_SURGE * df["VOL_MA20"]) &
    (df["PX_LAST"] > df["MA50"])
)

price_piv  = df.pivot_table(index="TRADE_DATE", columns="TICKER", values="PX_LAST")
signal_piv = df.pivot_table(index="TRADE_DATE", columns="TICKER", values="SIGNAL").fillna(False)
trading_dates = sorted(price_piv.index)
td_index = {d: i for i, d in enumerate(trading_dates)}

# Pre-build signal list per date for fast lookup
signals_by_date = {}
for d in trading_dates:
    if d in signal_piv.index:
        row = signal_piv.loc[d]
        signals_by_date[d] = row[row].index.tolist()
    else:
        signals_by_date[d] = []

# Daily portfolio: up to MAX_POSITIONS most-recent active signals
model_cumret = []
for t_idx, t in enumerate(trading_dates):
    start_idx = max(0, t_idx - HOLD_DAYS + 1)
    # Collect candidates newest-first
    candidates = []
    for entry_date in reversed(trading_dates[start_idx : t_idx + 1]):
        for tk in signals_by_date.get(entry_date, []):
            candidates.append((entry_date, tk))
            if len(candidates) >= MAX_POSITIONS:
                break
        if len(candidates) >= MAX_POSITIONS:
            break

    pos_returns = []
    for entry_date, tk in candidates:
        if tk not in price_piv.columns:
            continue
        ep = price_piv.at[entry_date, tk]
        cp = price_piv.at[t, tk]
        if pd.notna(ep) and pd.notna(cp) and ep > 0:
            pos_returns.append((cp / ep - 1) * 100)

    model_cumret.append(round(float(np.mean(pos_returns)), 2) if pos_returns else None)

# VNIndex cumulative return rebased to 0
vni_series = df.drop_duplicates("TRADE_DATE").set_index("TRADE_DATE")["IDX_CLOSE"].reindex(trading_dates)
vni_start = float(vni_series.dropna().iloc[0])
vnindex_cumret = [
    round((float(v) / vni_start - 1) * 100, 2) if pd.notna(v) else None
    for v in vni_series
]

# Stats: all completed 20d trades
all_returns = []
for d in trading_dates:
    d_idx = td_index[d]
    exit_idx = d_idx + HOLD_DAYS
    if exit_idx >= len(trading_dates):
        continue
    exit_date = trading_dates[exit_idx]
    for tk in signals_by_date.get(d, []):
        if tk not in price_piv.columns:
            continue
        ep = price_piv.at[d, tk]
        xp = price_piv.at[exit_date, tk]
        if pd.notna(ep) and pd.notna(xp) and ep > 0:
            all_returns.append((xp / ep - 1) * 100)

winners = [r for r in all_returns if r > 0]
losers  = [r for r in all_returns if r <= 0]
stats = {
    "total_signals":  len(all_returns),
    "hit_rate_pct":   round(len(winners) / len(all_returns) * 100, 1) if all_returns else 0,
    "avg_gain_pct":   round(float(np.mean(winners)), 2) if winners else 0,
    "avg_loss_pct":   round(float(np.mean(losers)),  2) if losers  else 0,
    "avg_return_pct": round(float(np.mean(all_returns)), 2) if all_returns else 0,
}

result = {
    "dates":          [str(d.date()) for d in trading_dates],
    "model_cumret":   model_cumret,
    "vnindex_cumret": vnindex_cumret,
    "stats":          stats,
}
