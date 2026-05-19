"""
Framework 3 v1.0 backtester — Equal-Weight Tiered System for VN equities.

Signal  : daily close > 3%, volume > 30% vs 20d avg, close > MA50.
          Multiple candidates on same day → sorted by daily return desc.
Entry   : signal-day ATC (close price). Size: 10% of initial portfolio per position.
Tiers   : T1 4 slots (always open)
          T2 3 slots (unlock: T1 full AND T1-avg-P&L > 1.5%)
          T3 3 slots (unlock: T2 full AND T2-avg-P&L > 1.5%)
Exit    : State A = hard stop at entry × 0.95  (counts as stop for Scale Down)
          State B = EMA50 trail after close > entry × 1.05  (NOT a stop)
          State C = sell ATO day 11 if no A or B by end of day 10  (NOT a stop)
          State B overrides C if +5% is reached on day 10.
Guards  : Scale Down  – 2+ State A stops in last 3 buys → block all new entries
          Black       – equity < rolling-20d-peak × 0.92 → block all new entries
"""

import pandas as pd
import numpy as np

LOOKBACK_START = "2022-01-01"
POS_SIZE       = 0.10   # 10 % of initial portfolio per position
STOP_PCT       = 0.05   # hard stop 5 % below entry
STATE_B_PCT    = 0.05   # +5 % close activates winner trail
HOLD_DAYS      = 10     # State C time stop
VOLUME_SURGE   = 1.30   # volume must exceed 130 % of 20d avg
PRICE_SURGE    = 0.03   # daily return must exceed 3 %
T1_SLOTS       = 4
T2_SLOTS       = 3
T3_SLOTS       = 3
UNLOCK_PCT     = 0.015  # tier avg P&L needed to open next tier
BLACK_RATIO    = 0.92   # equity below peak × this → Black active
SD_WINDOW      = 3      # Scale Down looks at last N buys
SD_TRIGGER     = 2      # stops needed to activate Scale Down

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
    SELECT md.TICKER, md.TRADE_DATE,
           md.PX_OPEN, md.PX_HIGH, md.PX_LOW, md.PX_LAST, md.VOLUME,
           mi.CLOSEINDEX as IDX_CLOSE
    FROM Market_Data md
    LEFT JOIN MarketIndex mi ON mi.TRADINGDATE = md.TRADE_DATE
                             AND mi.COMGROUPCODE = 'VNINDEX'
    WHERE md.TRADE_DATE >= '{LOOKBACK_START}'
      AND md.TICKER IN ('{tickers_str}')
      AND md.PX_LAST IS NOT NULL AND md.PX_LAST > 0 AND md.VOLUME > 0
    ORDER BY md.TICKER, md.TRADE_DATE
""")

df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"])
df = df.sort_values(["TICKER", "TRADE_DATE"]).reset_index(drop=True)

# ── Indicators (vectorised per ticker) ──────────────────────────────────────
g = df.groupby("TICKER", group_keys=False)
df["MA50"]     = g["PX_LAST"].transform(lambda x: x.rolling(50, min_periods=50).mean())
df["EMA50"]    = g["PX_LAST"].transform(lambda x: x.ewm(span=50, adjust=False).mean())
df["VOL_MA20"] = g["VOLUME"].transform(lambda x: x.rolling(20, min_periods=20).mean())
df["RET"]      = g["PX_LAST"].transform(lambda x: x.pct_change())

df["SIGNAL"] = (
    (df["RET"]     > PRICE_SURGE) &
    (df["VOLUME"]  > VOLUME_SURGE * df["VOL_MA20"]) &
    (df["PX_LAST"] > df["MA50"]) &
    df["MA50"].notna() & df["VOL_MA20"].notna()
)

# ── Pivot tables for fast date/ticker lookups ────────────────────────────────
trading_dates = sorted(df["TRADE_DATE"].unique())

close_piv  = df.pivot_table(index="TRADE_DATE", columns="TICKER", values="PX_LAST")
open_piv   = df.pivot_table(index="TRADE_DATE", columns="TICKER", values="PX_OPEN")
low_piv    = df.pivot_table(index="TRADE_DATE", columns="TICKER", values="PX_LOW")
ema50_piv  = df.pivot_table(index="TRADE_DATE", columns="TICKER", values="EMA50")
signal_piv = df.pivot_table(index="TRADE_DATE", columns="TICKER", values="SIGNAL").fillna(False)
ret_piv    = df.pivot_table(index="TRADE_DATE", columns="TICKER", values="RET")

# Candidate list per signal date: sorted by daily return desc (highest breakout first)
signals_by_date = {}
for d in trading_dates:
    if d not in signal_piv.index:
        signals_by_date[d] = []
        continue
    row   = signal_piv.loc[d]
    cands = row[row].index.tolist()
    if cands and d in ret_piv.index:
        rets  = ret_piv.loc[d, cands].dropna()
        cands = rets.sort_values(ascending=False).index.tolist()
    signals_by_date[d] = cands

vni_series = df.drop_duplicates("TRADE_DATE").set_index("TRADE_DATE")["IDX_CLOSE"].reindex(trading_dates)

# ── Helper functions ─────────────────────────────────────────────────────────
def tier_avg_pnl(positions, tier, close_dict):
    pnls = [
        close_dict[p["ticker"]] / p["entry_price"] - 1
        for p in positions
        if p["tier"] == tier
        and p["ticker"] in close_dict
        and p["entry_price"] > 0
    ]
    return float(np.mean(pnls)) if pnls else None

def slots_used(positions, queue_buys, tier):
    return (
        sum(1 for p in positions if p["tier"] == tier) +
        sum(1 for _, ti in queue_buys if ti == tier)
    )

# ── Portfolio simulation ─────────────────────────────────────────────────────
INITIAL    = 1.0
cash       = INITIAL
positions  = []   # open positions (list of dicts)
completed  = []   # closed positions
equity_hist = []
buy_log    = []   # last SD_WINDOW buys: {"date", "ticker", "is_stop"}
queue_buys = []   # (ticker, tier) to buy at next-day ATO

for t_idx, t in enumerate(trading_dates):
    close_d = (close_piv.loc[t] if t in close_piv.index else pd.Series(dtype=float)).dropna().to_dict()
    low_d   = (low_piv.loc[t]   if t in low_piv.index   else pd.Series(dtype=float)).dropna().to_dict()
    open_d  = (open_piv.loc[t]  if t in open_piv.index  else pd.Series(dtype=float)).dropna().to_dict()
    ema50_d = (ema50_piv.loc[t] if t in ema50_piv.index else pd.Series(dtype=float)).dropna().to_dict()

    # Phase 1 — Execute queued ATO exits at open
    still_open = []
    for p in positions:
        if p.get("queue_exit"):
            ep = open_d.get(p["ticker"], close_d.get(p["ticker"]))
            if ep:
                pnl = ep / p["entry_price"] - 1
                cash += POS_SIZE * (1 + pnl)
                completed.append({**p, "exit_price": ep, "exit_date": t, "pnl_pct": round(pnl * 100, 3)})
            else:
                p["queue_exit"] = False
                still_open.append(p)
        else:
            still_open.append(p)
    positions = still_open

    # Phase 2 — Execute queued ATO buys at open
    for ticker, tier in queue_buys:
        ep = open_d.get(ticker, close_d.get(ticker))
        if ep and ep > 0 and cash >= POS_SIZE:
            cash -= POS_SIZE
            positions.append({
                "ticker": ticker, "tier": tier,
                "entry_date": t, "entry_price": ep,
                "stop": ep * (1 - STOP_PCT),
                "days_held": 0, "state_b": False,
                "queue_exit": False, "exit_state": None,
            })
            buy_log.append({"date": t, "ticker": ticker, "is_stop": False})
    queue_buys = []

    # Phase 3 — State A: intraday stop check
    still_open = []
    for p in positions:
        lp = low_d.get(p["ticker"], close_d.get(p["ticker"]))
        if lp is not None and lp <= p["stop"]:
            pnl = p["stop"] / p["entry_price"] - 1
            cash += POS_SIZE * (1 + pnl)
            for bl in reversed(buy_log):  # mark the corresponding buy as a stop
                if bl["ticker"] == p["ticker"] and not bl["is_stop"]:
                    bl["is_stop"] = True
                    break
            completed.append({
                **p, "exit_price": p["stop"], "exit_date": t,
                "exit_state": "A", "pnl_pct": round(pnl * 100, 3),
            })
        else:
            still_open.append(p)
    positions = still_open

    # Phase 4 — Update positions at close
    for p in positions:
        cp = close_d.get(p["ticker"])
        if cp is None:
            continue
        if not p["state_b"] and cp > p["entry_price"] * (1 + STATE_B_PCT):
            p["state_b"] = True
        if p["state_b"] and not p["queue_exit"]:
            e50 = ema50_d.get(p["ticker"])
            if e50 and cp < e50:
                p["queue_exit"] = True
                p["exit_state"] = "B"
        p["days_held"] += 1
        if p["days_held"] >= HOLD_DAYS and not p["state_b"] and not p["queue_exit"]:
            p["queue_exit"] = True
            p["exit_state"] = "C"

    # Phase 5 — Mark-to-market equity
    pos_val = sum(
        POS_SIZE * (close_d.get(p["ticker"], p["entry_price"]) / p["entry_price"])
        for p in positions
    )
    equity = cash + pos_val
    equity_hist.append(equity)

    # Phase 6 — Scale Down: 2+ State A stops in last SD_WINDOW buys
    recent      = buy_log[-SD_WINDOW:]
    scale_down  = sum(1 for b in recent if b["is_stop"]) >= SD_TRIGGER

    # Phase 7 — Tier availability
    t1_open = sum(1 for p in positions if p["tier"] == 1)
    t2_open = sum(1 for p in positions if p["tier"] == 2)
    t1_avg  = tier_avg_pnl(positions, 1, close_d)
    t2_avg  = tier_avg_pnl(positions, 2, close_d)

    t2_available = (t1_open >= T1_SLOTS and t1_avg is not None and t1_avg > UNLOCK_PCT)
    t3_available = (t2_available and t2_open >= T2_SLOTS and t2_avg is not None and t2_avg > UNLOCK_PCT)

    # Phase 8 — Black circuit breaker
    peak_window = equity_hist[max(0, len(equity_hist) - 20):]
    black = (equity < max(peak_window) * BLACK_RATIO)

    # Phase 9 — Queue next-day buys from today's breakout signals
    if not scale_down and not black and t_idx + 1 < len(trading_dates):
        open_tickers   = {p["ticker"] for p in positions}
        queued_tickers: set = set()

        for ticker in signals_by_date.get(t, []):
            if ticker in open_tickers or ticker in queued_tickers:
                continue
            s1 = T1_SLOTS - slots_used(positions, queue_buys, 1)
            s2 = (T2_SLOTS - slots_used(positions, queue_buys, 2)) if t2_available else 0
            s3 = (T3_SLOTS - slots_used(positions, queue_buys, 3)) if t3_available else 0

            if s1 > 0:
                queue_buys.append((ticker, 1))
                queued_tickers.add(ticker)
            elif s2 > 0:
                queue_buys.append((ticker, 2))
                queued_tickers.add(ticker)
            elif s3 > 0:
                queue_buys.append((ticker, 3))
                queued_tickers.add(ticker)

# ── Results ──────────────────────────────────────────────────────────────────
vni_start = float(vni_series.dropna().iloc[0])
vnindex_cumret = [
    round((float(v) / vni_start - 1) * 100, 2) if pd.notna(v) else None
    for v in vni_series
]
model_cumret = [round((e / INITIAL - 1) * 100, 2) for e in equity_hist]

all_pnls = [c["pnl_pct"] for c in completed if "pnl_pct" in c]
exit_counts = {"A": 0, "B": 0, "C": 0}
for c in completed:
    if c.get("exit_state") in exit_counts:
        exit_counts[c["exit_state"]] += 1

winners = [p for p in all_pnls if p > 0]
losers  = [p for p in all_pnls if p <= 0]

peak, max_dd = INITIAL, 0.0
for e in equity_hist:
    if e > peak:
        peak = e
    dd = (peak - e) / peak * 100
    if dd > max_dd:
        max_dd = dd

n = max(len(completed), 1)
stats = {
    "total_trades":     len(all_pnls),
    "state_a_pct":      round(exit_counts["A"] / n * 100, 1),
    "state_b_pct":      round(exit_counts["B"] / n * 100, 1),
    "state_c_pct":      round(exit_counts["C"] / n * 100, 1),
    "hit_rate_pct":     round(len(winners) / len(all_pnls) * 100, 1) if all_pnls else 0,
    "avg_return_pct":   round(float(np.mean(all_pnls)), 2) if all_pnls else 0,
    "avg_win_pct":      round(float(np.mean(winners)), 2) if winners else 0,
    "avg_loss_pct":     round(float(np.mean(losers)), 2) if losers else 0,
    "max_drawdown_pct": round(max_dd, 2),
}

result = {
    "dates":          [str(d.date()) for d in trading_dates],
    "model_cumret":   model_cumret,
    "vnindex_cumret": vnindex_cumret,
    "stats":          stats,
}
