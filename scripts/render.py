"""
Render docs/index.html from the daily JSON snapshot.

Inputs:
  data/latest.json   (full snapshot saved by the scheduled task)
  scripts/template.html

Output:
  docs/index.html
  docs/data/latest.json     (copy for client access)
  docs/data/YYYY-MM-DD.json (archive)
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS = ROOT / "docs"
TEMPLATE = ROOT / "scripts" / "template.html"


def fmt_num(x, digits=0):
    if x is None:
        return "—"
    try:
        return f"{float(x):,.{digits}f}"
    except (TypeError, ValueError):
        return str(x)


def fmt_pct(x, digits=2):
    if x is None:
        return "—"
    try:
        return f"{float(x):+.{digits}f}%"
    except (TypeError, ValueError):
        return str(x)


def color_class(x):
    if x is None:
        return ""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return ""
    if v > 0:
        return "up"
    if v < 0:
        return "down"
    return ""


def render_screened_rows(rows):
    html = []
    for r in rows:
        chg = r.get("PRICE_PCT_1D")
        html.append(
            f"<tr>"
            f"<td class='ticker'>{r['TICKER']}</td>"
            f"<td class='num'>{fmt_num(r['PX_LAST'])}</td>"
            f"<td class='num {color_class(chg)}'>{fmt_pct(chg)}</td>"
            f"<td class='num'>{fmt_num(r['EMA20'])}</td>"
            f"<td class='num'>{fmt_num(r['EMA50'])}</td>"
            f"<td class='num up'>{fmt_pct(r['rs_strength_pct'])}</td>"
            f"<td class='num'>{fmt_pct(r['ema20_gap_pct'])}</td>"
            f"<td class='num'>{fmt_num(r['turnover_bn_vnd'], 1)}</td>"
            f"</tr>"
        )
    return "\n".join(html)


def render_sector_rows(rows):
    html = []
    for r in rows:
        mfi = r.get("mfi")
        cls = "up" if mfi and mfi > 50 else ("down" if mfi and mfi < 50 else "")
        html.append(
            f"<tr>"
            f"<td>{r['sector']}</td>"
            f"<td class='num {cls}'>{fmt_num(mfi, 1)}</td>"
            f"<td class='num'>{fmt_num(r.get('mfi_change'), 1)}</td>"
            f"</tr>"
        )
    return "\n".join(html)


def main():
    snapshot = json.loads((DATA_DIR / "latest.json").read_text())
    tmpl = TEMPLATE.read_text()

    vni = snapshot["vnindex"]
    universe = snapshot["universe"]
    breadth = snapshot.get("breadth", {})
    sectors = snapshot.get("sectors", [])
    sentiment = snapshot.get("sentiment", {})

    html = tmpl
    replacements = {
        "{{latest_date}}": snapshot["latest_date"],
        "{{generated_at}}": datetime.now().strftime("%Y-%m-%d %H:%M ICT"),
        "{{vni_close}}": fmt_num(vni["close"], 2),
        "{{vni_change}}": fmt_num(vni["change"], 2),
        "{{vni_change_pct}}": fmt_pct(vni["change_pct"]),
        "{{vni_color}}": color_class(vni["change"]),
        "{{universe_total}}": fmt_num(universe["total_tickers"]),
        "{{passed_count}}": fmt_num(universe["liquid_passed"]),
        "{{ma20_pct}}": fmt_pct(breadth.get("ma20_pct"), 1),
        "{{ma50_pct}}": fmt_pct(breadth.get("ma50_pct"), 1),
        "{{ma100_pct}}": fmt_pct(breadth.get("ma100_pct"), 1),
        "{{sentiment_summary}}": sentiment.get("summary", "—"),
        "{{sentiment_label}}": sentiment.get("label", "—"),
        "{{sentiment_class}}": sentiment.get("label", "").lower(),
        "{{screened_rows}}": render_screened_rows(snapshot.get("screened", [])),
        "{{sector_rows}}": render_sector_rows(sectors),
    }
    for k, v in replacements.items():
        html = html.replace(k, str(v))

    DOCS.mkdir(exist_ok=True)
    (DOCS / "data").mkdir(exist_ok=True)
    (DOCS / "index.html").write_text(html)

    # Copy snapshot for client access + archive
    shutil.copy(DATA_DIR / "latest.json", DOCS / "data" / "latest.json")
    archive = DOCS / "data" / f"{snapshot['latest_date']}.json"
    shutil.copy(DATA_DIR / "latest.json", archive)

    print(f"Rendered docs/index.html for {snapshot['latest_date']}")


if __name__ == "__main__":
    main()
