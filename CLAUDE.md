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
Universe is the sector watchlist (~111 tickers) — single query, no timeout risk.

### Step 1b — Breakout backtest
Run `scripts/backtest.py` via the `execute_python` MCP tool.
Copy the code from `scripts/backtest.py` exactly and execute it.
Capture: `dates`, `model_cumret`, `vnindex_cumret`, `stats`.
Signal: close >3%, volume >30% vs 20d avg, price >MA50. Hold 20d, max 10 positions.

### Step 2 — Market breadth
~~Removed~~ — breadth data now comes entirely from the Google Doc via the regime step.
Skip this step; do not call `supabase_market_breadth`.

### Step 3 — Regime indicators
Fetch the Google Doc as plain text using this export URL:
```
https://docs.google.com/document/d/1-ENaTgXaMnxa5h8e2Q0OAalUSbgEagosG5ZyyuTuEZM/export?format=txt
```
Use `urllib.request.urlopen` or `requests.get` to fetch the text, then pipe it into
`scripts/regime.py` via `subprocess.run` to get the regime JSON.

### Step 4 — Sector RSI14 analysis
Run `scripts/sector_rsi.py` via the `execute_python` MCP tool.
Copy the code from `scripts/sector_rsi.py` exactly and execute it.
Capture: `sector_analysis` (list sorted by strength desc).
Each entry has: `sector`, `strength` (mean RSI14), `strength_10d_chg`,
`breadth_pct` (% tickers RSI14 > 50), `tickers` (all tickers, sorted by RSI14 desc).

### Step 5 — Chart data (NHNL and Breadth)
Both `nhnl_chart` and `breadth_chart` come directly from the regime output — no separate calculation needed.
The Google Doc is the source of truth for both. Just assign:
```python
nhnl_chart    = regime["nhnl_history"]    # keys: dates, nhnl, vnindex
breadth_chart = regime["breadth_history"] # keys: dates, breadth_pct, vnindex
```

### Step 6 — Assemble data/latest.json
Combine all of the above into `data/latest.json` with this structure:
```
latest_date, vnindex, universe, screen_rules, sector_analysis, screened, regime, nhnl_chart, breadth_chart, backtest
```

### Step 7 — Render
Run: `python3 scripts/render.py`
This writes `docs/index.html`, `docs/data/latest.json`, and `docs/data/YYYY-MM-DD.json`.

### Step 8 — Commit and push
```
git add data/latest.json docs/
git commit -m "Daily update YYYY-MM-DD"
git push origin HEAD:main
```

## Branch
Always push to `main` using `git push origin HEAD:main`. GitHub Pages serves from `main` — pushing to any other branch will not update the live site.

## Notes
- If the database has no new data since the last run (e.g. weekend), still re-run and push — it refreshes the "generated at" timestamp on the site.
- Do not change any script files unless explicitly asked.
