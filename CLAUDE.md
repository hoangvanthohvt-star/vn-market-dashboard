# VN Market Dashboard — Daily Update Instructions

## What this repo is
A static daily dashboard for Vietnamese stock market analysis, hosted on GitHub Pages.
Updated every morning at 06:30 ICT by a scheduled Claude Code session.

## How to run the daily update

When asked to run the daily update, follow the steps below.

### Step 1 — 6-Month Interbank Rate (database → /tmp/interbank_6m.json)

Use `mcp__DCG__mssql_read_data` to query:
```sql
SELECT CONVERT(varchar(10), Date, 120) as date, Value as value
FROM macro_data_consolidated
WHERE Ticker = 'VNIVND6MD='
ORDER BY Date
```

Save the `data` array from the result to `/tmp/interbank_6m.json` using the Bash tool:
```bash
python3 -c "
import json
records = <paste data array here>
open('/tmp/interbank_6m.json','w').write(json.dumps(records))
print('Saved', len(records), 'records')
"
```

### Step 2 — Regime indicators (Google Drive → regime.py)

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
python3 scripts/regime.py /tmp/regime_doc.txt /tmp/interbank_6m.json
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

### Step 3 — Assemble data/latest.json
All data comes from the regime output. Build the snapshot:
```python
snap = {
    "latest_date":  regime["date"],
    "vnindex":      {"close": regime["vnindex"], "change": 0, "change_pct": 0},
    "regime":       regime,
    "nhnl_chart":   regime["nhnl_history"],
    "breadth_chart":regime["breadth_history"],
    "mfi_chart":    regime["mfi_history"],
    "ad_chart":     regime["ad_history"],
    "gap_chart":    regime["gap_history"],
    "ma200_chart":  regime["ma200_history"],
    "rs_chart":        regime["rs_history"],
    "interbank_chart": regime["interbank_history"],
}
```

### Step 4 — Render
Run: `python3 scripts/render.py`
This writes `docs/index.html`, `docs/data/latest.json`, and `docs/data/YYYY-MM-DD.json`.

### Step 5 — Commit and push
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
3. NHNL chart (bar, 1Y/2Y/3Y, default 1Y)
4. Breadth chart (1Y/2Y/3Y, default 3Y)
5. Executive Summary + Metric cards (second copy)
6. Divergence Checklist
7. Scenarios (bear score table + 3 scenario cards)
8. Price & Indicator Chart (1Y/2Y/3Y, default 3Y, full_history)
9. MFI chart (1Y/2Y/3Y, default 3Y)
10. RSI Gap chart — RSI21 − NHNL RSI vs VNIndex (1Y/2Y/3Y, default 3Y, danger zones >+30 and <−20)
11. A/D Line chart (1Y/2Y/3Y, default 3Y)
12. Footer

## Scenario framework (regime.py)
Bear score (0–100) drives scenario probabilities for uptrend regimes:
- **0–19 Clean**: Uptrend 65% / Pullback 25% / Breakdown 10%
- **20–39 Caution**: Uptrend 50% / Pullback 35% / Breakdown 15%
- **40–59 Warning**: Distribution 55% / Bull resolve 30% / Chop 15%
- **60+ High Risk**: Distribution 70% / Bull resolve 20% / Chop 10%

Bear score components: Gap (+0/15/25/35) + Dir10d (+25) + Dir5d (+15) + Breadth (+0/10/20) + RSI>70 (+10).
Recommended allocation = probability-weighted average of scenario allocations.
