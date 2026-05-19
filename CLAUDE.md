# VN Market Dashboard — Daily Update Instructions

## What this repo is
A static daily dashboard for Vietnamese stock market analysis, hosted on GitHub Pages.
Updated every morning at 06:30 ICT by a scheduled Claude Code session.

## Session start — auto-run
**When a new Claude Code session starts in this project directory, immediately run the
daily update (Steps 1–8 below) without waiting for user input.**
This applies both to cloud-scheduled sessions and to manual sessions opened on the local
Windows laptop. Do not greet the user first — just start the update.

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
Fetch the Google Doc as plain text using this export URL:
```
https://docs.google.com/document/d/1-ENaTgXaMnxa5h8e2Q0OAalUSbgEagosG5ZyyuTuEZM/export?format=txt
```
Use `urllib.request.urlopen` or `requests.get` to fetch the text, then pipe it into
`scripts/regime.py` via `subprocess.run` to get the regime JSON.

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
- If the database has no new data since the last run (e.g. weekend), still re-run and push — it refreshes the "generated at" timestamp on the site.
- Do not change any script files unless explicitly asked.
