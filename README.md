# VN Market Daily

A free, static daily dashboard for Vietnamese stock market analysis, hosted on
GitHub Pages and refreshed every morning at 06:30 ICT by a Claude Code
scheduled task.

## Screen

Stocks must satisfy on the latest trading day:

- `price > EMA20 > EMA50`
- `RS line (close / VN-Index) > MA50(RS line)`
- 20-day average turnover `> 1bn VND`

## Layout

```
scripts/
  screening.py     # Payload sent to MCP execute_python (runs against MSSQL)
  render.py        # Renders docs/index.html from data/latest.json
  template.html    # Static HTML template with {{placeholders}}
data/
  latest.json      # Most recent snapshot (committed each morning)
docs/              # Served by GitHub Pages
  index.html
  data/
    latest.json
    YYYY-MM-DD.json  # Daily archive
```

## How the daily run works

A scheduled Claude Code task fires at 06:30 ICT and:

1. Runs `scripts/screening.py` via the MCP `execute_python` tool → screen JSON.
2. Pulls market overview (breadth, sector MFI, Zalo sentiment) via MCP tools.
3. Merges into `data/latest.json`.
4. Runs `python3 scripts/render.py` to rebuild `docs/index.html`.
5. `git add docs/ data/ && git commit && git push` → GitHub Pages refreshes.

Edit `scripts/screening.py` to change the rules — no other changes needed.

## Local preview

```bash
python3 scripts/render.py
open docs/index.html
```
