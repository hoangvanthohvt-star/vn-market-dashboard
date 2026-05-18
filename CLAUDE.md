# VN Market Dashboard — Daily Update Instructions

## What this repo is
A static daily dashboard for Vietnamese stock market analysis, hosted on GitHub Pages.
Updated every morning at 06:30 ICT by a scheduled Claude Code session.

## How to run the daily update

When asked to run the daily update, do the following steps in order:

### Step 1 — Stock screening
Run `scripts/screening.py` via the `execute_python` MCP tool.
Copy the code from `scripts/screening.py` exactly and execute it.
Capture: `latest_date`, `vnindex`, `universe`, `screen_rules`, `screened`.

### Step 2 — Market breadth
Call `supabase_market_breadth` with `days=90`.
From the result, use `ma20_pct`, `ma50_pct`, `ma100_pct` from the latest row.
Also keep the full `rows` array for the breadth chart (use dates + ma50_pct + vnindex).

### Step 3 — Regime indicators
Compute from MSSQL via `execute_python`:
- VNIndex RSI21 and RSI70 from `MarketIndex` (COMGROUPCODE='VNINDEX'), going back to 2025-07-01
- NHNL RSI21: from `Market_Data` (PX_HIGH, PX_LOW), compute 52-week rolling high/low, daily new highs minus new lows, then RSI21 of that series
- MFI RSI21: typical price × volume money flow, RSI21 of the positive/total ratio
- A/D RSI21: advance-decline line cumsum, RSI21 of that series

Build a text string with one row per trading day (last 60 days where all sources overlap):
```
YYYY-MM-DD VNINDEX RSI21 RSI70 BREADTH% NHNL_RSI MFI_RSI AD_RSI
```
Example: `2026-05-15 1921.60 64.62 57.14 42.2% 47.98 49.66 30.79`

Pipe this text into `scripts/regime.py` via `subprocess.run` to get the regime JSON.

### Step 4 — Sector RSI14 analysis
Run via `execute_python`: for each sector in `render.py`'s `_SECTOR_TICKERS`, compute RSI14
of daily `PX_LAST` from `Market_Data` since 2025-10-01. For each sector output:
`sector`, `strength` (mean RSI14), `strength_10d_chg`, `breadth_pct` (% tickers RSI14 > 50), `tickers` (top 3).

### Step 5 — NHNL chart data
Keep the existing `data/latest.json` nhnl_chart and breadth_chart as-is unless the
latest_date has advanced, in which case append the new data point.

### Step 6 — Assemble data/latest.json
Combine all of the above into `data/latest.json` with this structure:
```
latest_date, vnindex, universe, screen_rules, breadth, sector_analysis, screened, regime, nhnl_chart, breadth_chart
```
Compute `vnindex.change_pct` from the last two VNIndex closes if the raw value is 0 or missing.

### Step 7 — Render
Run: `python3 scripts/render.py`
This writes `docs/index.html`, `docs/data/latest.json`, and `docs/data/YYYY-MM-DD.json`.

### Step 8 — Commit and push
```
git add data/latest.json docs/
git commit -m "Daily update YYYY-MM-DD"
git push -u origin <current-branch>
```

## Branch
Always push to whatever branch is currently checked out. Do not switch branches.

## Notes
- The Mac version feeds regime indicators from a Google Doc. This cloud version computes them directly from MSSQL — values will be slightly different but the regime classification will be consistent.
- If the database has no new data since the last run (e.g. weekend), still re-run and push — it refreshes the "generated at" timestamp on the site.
- Do not change any script files unless explicitly asked.
