# VN Market Dashboard — Daily Update Instructions

## What this repo is
A static daily dashboard for Vietnamese stock market analysis, hosted on GitHub Pages.
Updated every morning at 06:30 ICT by a scheduled Claude Code session.

## How to run the daily update

When asked to run the daily update, do the following steps in order.
**Steps 1, 3, and 4 are independent — run them in parallel in a single message for speed.**

### Step 1 — Stock screening
Run `scripts/screening.py` via the `execute_python` MCP tool.
Copy the code from `scripts/screening.py` exactly and execute it.
Capture: `latest_date`, `vnindex`, `universe`, `screen_rules`, `screened`.
Universe is the sector watchlist (~111 tickers) — single query, no timeout risk.

### Step 2 — Market breadth
~~Removed~~ — breadth data now comes entirely from the Google Doc via the regime step.
Skip this step; do not call `supabase_market_breadth`.

### Step 3 — Regime indicators

**Do NOT use urllib, requests, subprocess, or WebFetch — all are blocked in this environment.**

Use the Google Drive MCP tool to download the doc:
- Tool: `mcp__d5e363e8-c1a9-42ab-8518-42516e57b5ba__download_file_content`
- fileId: `1-ENaTgXaMnxa5h8e2Q0OAalUSbgEagosG5ZyyuTuEZM`
- exportMimeType: `text/plain`

The tool returns a large JSON result that gets saved to a file path shown in the response.
Decode it and save to `/tmp/regime_doc.txt` using the Bash tool:
```bash
cat <path-to-tool-result-file> | python3 -c "
import sys, json, base64
data = json.load(sys.stdin)
content = base64.b64decode(data['content']).decode('utf-8')
open('/tmp/regime_doc.txt', 'w').write(content)
print('Saved', len(content), 'chars')
"
```

Then run regime.py via the Bash tool (NOT execute_python):
```bash
python3 scripts/regime.py /tmp/regime_doc.txt
```

Capture the JSON output as `regime`.

Key keys in `regime` output:
- `history` — last 30 days (dates, vnindex, rsi21, breadth, nhnl, mfi, ad)
- `full_history` — all available history (~3 years), same keys, used for main chart
- `nhnl_history`, `breadth_history`, `mfi_history`, `ad_history`, `gap_history` — full history for individual charts
- `indicators` — latest values (rsi21, breadth_pct, nhnl_rsi, mfi_rsi, ad_rsi, etc.)
- `divergence` — direction 5d/10d flags, gap, severity, detail
- `bear_detail` — bear score (0–100), tier (Clean/Caution/Warning/High Risk), component breakdown
- `scenarios` — 3 probability-weighted scenarios with allocations (driven by bear_score for uptrends)
- `allocation` — probability-weighted recommended allocation %
- `regime_name`, `divergence_flag`, `severity`

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
mfi_chart     = regime["mfi_history"]     # keys: dates, mfi_abs, vnindex
ad_chart      = regime["ad_history"]      # keys: dates, ad_abs, vnindex
gap_chart     = regime["gap_history"]     # keys: dates, gap, vnindex
```

### Step 6 — Assemble data/latest.json
Combine all of the above into `data/latest.json` with this structure:
```python
snap = {
    "latest_date":     screening["latest_date"],
    "vnindex":         screening["vnindex"],
    "universe":        screening["universe"],
    "screen_rules":    screening["screen_rules"],
    "screened":        screening["screened"],
    "sector_analysis": sector_analysis,
    "regime":          regime,           # full regime object (includes bear_detail, scenarios, full_history, etc.)
    "nhnl_chart":      regime["nhnl_history"],
    "breadth_chart":   regime["breadth_history"],
    "mfi_chart":       regime["mfi_history"],
    "ad_chart":        regime["ad_history"],
    "gap_chart":       regime["gap_history"],
}
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
- The timestamp shown on the site is GMT+7 (Vietnam time), computed as `datetime.utcnow() + timedelta(hours=7)` in render.py.

## Dashboard layout (top → bottom)
1. Header (Market Regime title + timestamp)
2. Metric cards (RSI / Breadth / NHNL / MFI / A/D / Gap / Allocation) — duplicated at top and before Divergence Checklist
3. Market Overview cards (sector + RS stocks)
4. Price & Indicator Chart (1Y/2Y/3Y, default 3Y, full_history)
5. NHNL chart (bar, 1Y/2Y/3Y, default 1Y)
6. Breadth chart (1Y/2Y/3Y, default 3Y)
7. Executive Summary + Metric cards (second copy)
8. Divergence Checklist
9. Scenarios (bear score table + 3 scenario cards)
10. MFI chart (1Y/2Y/3Y, default 3Y)
11. RSI Gap chart — RSI21 − NHNL RSI vs VNIndex (1Y/2Y/3Y, default 3Y, danger zones >+30 and <−20)
12. A/D Line chart (1Y/2Y/3Y, default 3Y)
13. Footer

## Scenario framework (regime.py)
Bear score (0–100) drives scenario probabilities for uptrend regimes:
- **0–19 Clean**: Uptrend 65% / Pullback 25% / Breakdown 10%
- **20–39 Caution**: Uptrend 50% / Pullback 35% / Breakdown 15%
- **40–59 Warning**: Distribution 55% / Bull resolve 30% / Chop 15%
- **60+ High Risk**: Distribution 70% / Bull resolve 20% / Chop 10%

Bear score components: Gap (+0/15/25/35) + Dir10d (+25) + Dir5d (+15) + Breadth (+0/10/20) + RSI>70 (+10).
Recommended allocation = probability-weighted average of scenario allocations.
