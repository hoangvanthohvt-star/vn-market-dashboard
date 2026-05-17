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


def render_scenario_cards(scenarios):
    html = []
    for s in scenarios:
        html.append(
            f"<div class='scenario-card'>"
            f"<div class='scenario-prob'>{s['probability']}%</div>"
            f"<div class='scenario-name'>{s['name']}</div>"
            f"<div class='scenario-row'>✓ <span>{s.get('confirmation','—')}</span></div>"
            f"<div class='scenario-row'>✗ <span>{s.get('invalidation','—')}</span></div>"
            f"<div class='scenario-row'>Alloc <span>{s.get('allocation','—')}%</span></div>"
            f"</div>"
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
    regime = snapshot.get("regime", {})

    # Regime helpers
    div = regime.get("divergence", {})
    div_flag = regime.get("divergence_flag", "—")
    div_class = "aligned"
    if "Bearish" in div_flag:  div_class = "bearish"
    elif "Bullish" in div_flag: div_class = "bullish"
    gap = div.get("gap", 0)
    gap_class = "gap-bearish" if gap > 12 else ("gap-bullish" if gap < -12 else "")
    ind = regime.get("indicators", {})
    cls = regime.get("classifications", {})

    html = tmpl
    replacements = {
        "{{latest_date}}":     snapshot["latest_date"],
        "{{generated_at}}":    datetime.now().strftime("%Y-%m-%d %H:%M ICT"),
        "{{vni_close}}":       fmt_num(vni["close"], 2),
        "{{vni_change}}":      fmt_num(vni["change"], 2),
        "{{vni_change_pct}}":  fmt_pct(vni["change_pct"]),
        "{{vni_color}}":       color_class(vni["change"]),
        "{{universe_total}}":  fmt_num(universe["total_tickers"]),
        "{{passed_count}}":    fmt_num(universe["liquid_passed"]),
        "{{ma20_pct}}":        fmt_pct(breadth.get("ma20_pct"), 1),
        "{{ma50_pct}}":        fmt_pct(breadth.get("ma50_pct"), 1),
        "{{ma100_pct}}":       fmt_pct(breadth.get("ma100_pct"), 1),
        "{{sentiment_summary}}": sentiment.get("summary", "—"),
        "{{sentiment_label}}": sentiment.get("label", "—"),
        "{{sentiment_class}}": sentiment.get("label", "").lower(),
        "{{screened_rows}}":   render_screened_rows(snapshot.get("screened", [])),
        "{{sector_rows}}":     render_sector_rows(sectors),
        # Regime
        "{{regime_name}}":          regime.get("regime_name", "—"),
        "{{regime_div_flag}}":       div_flag,
        "{{regime_div_class}}":      div_class,
        "{{regime_rsi21}}":          fmt_num(ind.get("rsi21"), 1),
        "{{regime_trend}}":          cls.get("trend", "—"),
        "{{regime_breadth}}":        fmt_num(ind.get("breadth_pct"), 1) + "%",
        "{{regime_breadth_label}}":  cls.get("breadth", "—"),
        "{{regime_nhnl}}":           fmt_num(ind.get("nhnl_rsi"), 1),
        "{{regime_nhnl_label}}":     cls.get("nhnl", "—"),
        "{{regime_mfi}}":            fmt_num(ind.get("mfi_rsi"), 1),
        "{{regime_mfi_label}}":      cls.get("mfi", "—"),
        "{{regime_ad}}":             fmt_num(ind.get("ad_rsi"), 1),
        "{{regime_ad_label}}":       cls.get("ad", "—"),
        "{{regime_gap}}":            f"{gap:+.1f}" if isinstance(gap, (int, float)) else "—",
        "{{regime_gap_class}}":      gap_class,
        "{{regime_internal_avg}}":   fmt_num(div.get("internal_avg"), 1),
        "{{regime_div_severity}}":   div.get("severity", "—"),
        "{{regime_allocation}}":     str(regime.get("allocation", "—")),
        "{{regime_dir5d}}":          "Y" if div.get("dir_5d") else "N",
        "{{regime_dir10d}}":         "Y" if div.get("dir_10d") else "N",
        "{{regime_scenario_cards}}": render_scenario_cards(regime.get("scenarios", [])),
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
