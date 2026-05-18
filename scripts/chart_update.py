"""
Incremental update for NHNL + breadth charts.

Designed to be inlined into execute_python (uses bare sql_query()).
Caller sets two globals before execution:
  NHNL_LAST_DATE    str "YYYY-MM-DD" — last date in existing nhnl_chart, or None
  BREADTH_LAST_DATE str "YYYY-MM-DD" — last date in existing breadth_chart, or None

If both are None, falls back to a full rebuild from 2023-01-01.
Otherwise fetches only WARMUP_DAYS calendar days before the earlier last_date
(enough for 20-day rolling high/low + 15-day NHNL sum + 50-day MA50).

Returns:
  nhnl_tail    {dates, nhnl_15d, vnindex} — dates strictly > NHNL_LAST_DATE
  breadth_tail {dates, breadth_pct, vnindex} — dates strictly > BREADTH_LAST_DATE
  is_full_rebuild, fetch_start, fetch_chunks
"""

import pandas as pd

FULL_REBUILD_START = "2023-01-01"
WARMUP_DAYS = 120  # ~80 trading days — covers 50d MA + 20d HL + 15d sum


def _to_ts(s):
    if not s:
        return None
    return pd.Timestamp(s).normalize()


nhnl_last    = _to_ts(NHNL_LAST_DATE)
breadth_last = _to_ts(BREADTH_LAST_DATE)

if nhnl_last is None and breadth_last is None:
    fetch_start = FULL_REBUILD_START
else:
    bound = min(d for d in [nhnl_last, breadth_last] if d is not None)
    fetch_start = (bound - pd.Timedelta(days=WARMUP_DAYS)).strftime("%Y-%m-%d")

start_ts = pd.Timestamp(fetch_start)
today    = pd.Timestamp.today().normalize()

boundaries = []
y, m = start_ts.year, start_ts.month
while True:
    boundaries.append(f"{y:04d}-{m:02d}-01")
    if pd.Timestamp(f"{y:04d}-{m:02d}-01") > today:
        break
    m += 1
    if m > 12:
        m = 1; y += 1


def _retry_sql(q, want_cols, attempts=5):
    """sql_query with retries — MS SQL bridge occasionally returns empty columns."""
    last = None
    for _ in range(attempts):
        last = sql_query(q)
        if all(c in last.columns for c in want_cols):
            return last
    assert all(c in last.columns for c in want_cols), \
        f"SQL empty after {attempts} attempts: cols={list(last.columns)}"
    return last


# MarketIndex first (single-line query — multi-line f""" """ has been flaky)
idx_df = _retry_sql(
    f"SELECT TRADINGDATE, CLOSEINDEX FROM MarketIndex WHERE COMGROUPCODE='VNINDEX' AND TRADINGDATE >= '{fetch_start}'",
    ["TRADINGDATE", "CLOSEINDEX"],
)
idx_df["TRADE_DATE"] = pd.to_datetime(idx_df["TRADINGDATE"], utc=True).dt.tz_convert(None).dt.normalize()

parts = []
for a, b in zip(boundaries[:-1], boundaries[1:]):
    q = (
        f"SELECT md.TICKER, md.TRADE_DATE, md.PX_LAST "
        f"FROM Market_Data md INNER JOIN Sector_Map sm ON md.TICKER = sm.Ticker "
        f"WHERE sm.VNI = 'Y' "
        f"AND md.TRADE_DATE >= '{a}' AND md.TRADE_DATE < '{b}' "
        f"AND md.PX_LAST IS NOT NULL AND md.PX_LAST > 0"
    )
    p = _retry_sql(q, ["TICKER", "TRADE_DATE", "PX_LAST"])
    if len(p) > 0:
        parts.append(p)
assert parts, "no Market_Data returned"

df = pd.concat(parts, ignore_index=True)
df["TRADE_DATE"] = pd.to_datetime(df["TRADE_DATE"], utc=True).dt.tz_convert(None).dt.normalize()
df = df.sort_values(["TICKER", "TRADE_DATE"])

g = df.groupby("TICKER", group_keys=False)
df["HIGH20"] = g["PX_LAST"].transform(lambda x: x.rolling(20, min_periods=20).max())
df["LOW20"]  = g["PX_LAST"].transform(lambda x: x.rolling(20, min_periods=20).min())
df["IS_NH"]  = ((df["PX_LAST"] == df["HIGH20"]) & df["HIGH20"].notna()).astype(int)
df["IS_NL"]  = ((df["PX_LAST"] == df["LOW20"])  & df["LOW20"].notna()).astype(int)
df["MA50"]   = g["PX_LAST"].transform(lambda x: x.rolling(50, min_periods=50).mean())
df["ABOVE"]  = (df["PX_LAST"] > df["MA50"]).astype(float)
df.loc[df["MA50"].isna(), "ABOVE"] = float("nan")

nhnl_daily = (df.groupby("TRADE_DATE")
                .agg(NH=("IS_NH", "sum"), NL=("IS_NL", "sum"))
                .reset_index().sort_values("TRADE_DATE"))
nhnl_daily["NHNL_D"]   = nhnl_daily["NH"] - nhnl_daily["NL"]
nhnl_daily["NHNL_15D"] = nhnl_daily["NHNL_D"].rolling(15).sum()
nhnl_daily = nhnl_daily.dropna(subset=["NHNL_15D"])

valid = df.dropna(subset=["MA50"])
breadth_daily = (valid.groupby("TRADE_DATE")
                      .agg(ABOVE_SUM=("ABOVE", "sum"), TOTAL=("ABOVE", "count"))
                      .reset_index().sort_values("TRADE_DATE"))
breadth_daily["BREADTH_PCT"] = (breadth_daily["ABOVE_SUM"] / breadth_daily["TOTAL"] * 100).round(1)

nhnl_tail    = nhnl_daily    if nhnl_last    is None else nhnl_daily   [nhnl_daily   ["TRADE_DATE"] > nhnl_last]
breadth_tail = breadth_daily if breadth_last is None else breadth_daily[breadth_daily["TRADE_DATE"] > breadth_last]

nhnl_tail    = nhnl_tail   .merge(idx_df[["TRADE_DATE", "CLOSEINDEX"]], on="TRADE_DATE", how="inner").sort_values("TRADE_DATE")
breadth_tail = breadth_tail.merge(idx_df[["TRADE_DATE", "CLOSEINDEX"]], on="TRADE_DATE", how="inner").sort_values("TRADE_DATE")

result = {
    "nhnl_tail": {
        "dates":    nhnl_tail["TRADE_DATE"].dt.strftime("%Y-%m-%d").tolist(),
        "nhnl_15d": nhnl_tail["NHNL_15D"].round(0).astype(int).tolist(),
        "vnindex":  nhnl_tail["CLOSEINDEX"].round(2).tolist(),
    },
    "breadth_tail": {
        "dates":       breadth_tail["TRADE_DATE"].dt.strftime("%Y-%m-%d").tolist(),
        "breadth_pct": breadth_tail["BREADTH_PCT"].tolist(),
        "vnindex":     breadth_tail["CLOSEINDEX"].round(2).tolist(),
    },
    "is_full_rebuild": nhnl_last is None and breadth_last is None,
    "fetch_start":     fetch_start,
    "fetch_chunks":    len(boundaries) - 1,
}
