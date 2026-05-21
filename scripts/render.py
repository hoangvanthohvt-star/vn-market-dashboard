"""
Render docs/index.html from the daily JSON snapshot.

Inputs:
  data/latest.json
  scripts/template.html

Output:
  docs/index.html
  docs/data/latest.json
  docs/data/YYYY-MM-DD.json
"""

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

ROOT     = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS     = ROOT / "docs"
TEMPLATE = ROOT / "scripts" / "template.html"


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def fmt(x, digits=0):
    if x is None: return "—"
    try:    return f"{float(x):,.{digits}f}"
    except: return str(x)

def fmt_pct(x, digits=2, sign=False):
    if x is None: return "—"
    try:    return f"{float(x):+.{digits}f}%" if sign else f"{float(x):.{digits}f}%"
    except: return str(x)

def color(x):
    try:
        v = float(x)
        return "up" if v > 0 else ("down" if v < 0 else "")
    except: return ""

def pos_neg(x):
    try:
        v = float(x)
        return "pos" if v > 0 else ("neg" if v < 0 else "neu")
    except: return "neu"


# ---------------------------------------------------------------------------
# Market Overview — screened & sector rows (DC style)
# ---------------------------------------------------------------------------

_SECTOR_TICKERS = {
    "Banking":        ["ACB","BID","CTG","HDB","MBB","MSB","SHB","STB","TCB","TPB","VCB","VPB"],
    "Real Estate":    ["CEO","CII","DIG","DXG","HDC","KDH","NLG","NVL","PDR","TCH"],
    "Industrial Park":["KBC","IDC","BCM","VGC"],
    "Steel":          ["HPG","HSG","NKG","SMC","VGS"],
    "Retail":         ["DGW","FRT","MWG","PET","PNJ"],
    "Fertilizer":     ["BFC","CSV","DCM","DGC","DPM","LAS"],
    "Oil & Gas":      ["BSR","GAS","OIL","PLX","PVD","PVS","PVT"],
    "Construction":   ["CTD","FCN","HBC","HHV","LCG","VCG"],
    "Securities":     ["BSI","CTS","FTS","HCM","MBS","SHS","SSI","TCX","VCI","VCK","VDS","VIX","VND","VPX"],
    "Consumer":       ["MSN","QNS","SBT","VNM"],
    "VinGroup":       ["VIC","VHM","VRE","VPL"],
    "GEX Family":     ["EVF","GEE","GEL","GEX","VIX"],
    "Tech":           ["CMG","CTR","FOX","FPT","VGI","VTP"],
    "Transport":      ["GMD","HAH","PHP","VOS"],
    "Textile":        ["GIL","MSH","TCM","TNG","VGT"],
    "Rubber":         ["DPR","DRI","GVR","PHR","SIP"],
    "Fishery":        ["ANV","IDI","VHC"],
    "Electricity":    ["GEG","NT2","PC1","POW","PPC","REE","TV2"],
}
_TICKER_SECTOR = {t: s for s, tickers in _SECTOR_TICKERS.items() for t in tickers}

def render_screened_rows(rows):
    out = []
    for r in rows:
        chg  = r.get("PRICE_PCT_1D")
        cls  = "pos-t" if chg and float(chg) > 0 else ("neg-t" if chg and float(chg) < 0 else "")
        rs   = r.get("rs_strength_pct", 0)
        g20  = r.get("ema20_gap_pct")
        g50  = r.get("ema50_gap_pct")
        # EMA20 vs EMA50: derived from (1+g50/100)/(1+g20/100) - 1
        if g20 is not None and g50 is not None:
            ema_gap = ((1 + g50 / 100) / (1 + g20 / 100) - 1) * 100
        else:
            ema_gap = None
        sector = _TICKER_SECTOR.get(r["TICKER"], "")
        tvnd = r.get("turnover_bn_vnd")
        tvnd_str = f"{float(tvnd):.1f}" if tvnd is not None else "—"
        out.append(
            f"<tr>"
            f"<td class='fw ticker-link'>{r['TICKER']}</td>"
            f"<td class='fw'>{sector}</td>"
            f"<td class='tr'>{fmt(r['PX_LAST'])}</td>"
            f"<td class='tr {cls}'>{fmt_pct(chg, digits=1, sign=True)}</td>"
            f"<td class='tr pos-t'>{fmt_pct(g20, digits=1, sign=True)}</td>"
            f"<td class='tr pos-t'>{fmt_pct(ema_gap, digits=1, sign=True)}</td>"
            f"<td class='tr pos-t'>{fmt_pct(rs, digits=1, sign=True)}</td>"
            f"<td class='tr'>{tvnd_str}</td>"
            f"</tr>"
        )
    return "\n".join(out)


def render_sector_analysis_rows(rows):
    out = []
    for r in rows:
        s     = r.get("strength", 0)
        chg   = r.get("strength_10d_chg")
        brd   = r.get("breadth_pct")
        tickers = r.get("tickers", [])

        s_cls   = "pos-t" if s > 55 else ("warn-t" if s >= 45 else "neg-t")
        chg_cls = ("pos-t" if chg and chg > 0 else ("neg-t" if chg and chg < 0 else "")) if chg is not None else ""
        brd_cls = "pos-t" if brd and brd >= 60 else ("warn-t" if brd and brd >= 40 else "neg-t")

        chg_str = f"{chg:+.1f}" if chg is not None else "—"
        brd_str = f"{brd:.0f}%" if brd is not None else "—"
        ticker_str = " · ".join(tickers) if tickers else "—"

        out.append(
            f"<tr>"
            f"<td class='fw'>{r['sector']}</td>"
            f"<td class='tr {s_cls}'>{s:.1f}</td>"
            f"<td class='tr {chg_cls}'>{chg_str}</td>"
            f"<td class='tr {brd_cls}'>{brd_str}</td>"
            f"<td>{ticker_str}</td>"
            f"</tr>"
        )
    return "\n".join(out) if out else "<tr><td colspan='5' style='color:#999;text-align:center;'>No data</td></tr>"


def render_overview_cards(regime, screened, sector_analysis=None):
    # Card 1 — Market Indicators
    ind = regime.get("indicators", {}) if regime else {}
    def _ind_row(label, val, fmt=".1f", suffix=""):
        if val is None:
            return f"<div style='display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid #eee;font-size:12px;'><span style='color:#111;font-weight:600;'>{label}</span><span style='font-weight:700;'>—</span></div>"
        v = float(val)
        cls = "#00BF6F" if v > 60 else ("#FF671B" if v >= 45 else "#FF0037")
        return (
            f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"padding:3px 0;border-bottom:1px solid #eee;font-size:12px;'>"
            f"<span style='color:#111;font-weight:600;'>{label}</span>"
            f"<span style='font-weight:700;color:{cls};'>{v:{fmt}}{suffix}</span>"
            f"</div>"
        )
    ind_rows = "".join([
        _ind_row("RSI 21D",      ind.get("rsi21")),
        _ind_row("Breadth % &gt; MA50", ind.get("breadth_pct"), suffix="%"),
        _ind_row("NHNL RSI",     ind.get("nhnl_rsi")),
        _ind_row("MFI RSI",      ind.get("mfi_rsi")),
        _ind_row("A/D RSI",      ind.get("ad_rsi")),
    ])
    card1 = (
        f"<div class='ov-card'>"
        f"<div class='ov-label'>Market Indicators</div>"
        f"<div style='margin-top:8px;'>{ind_rows}</div>"
        f"</div>"
    )

    # Card 2 — Top 5 from sector_analysis (RSI14 strength)
    top5_src = sorted(sector_analysis or [], key=lambda x: x.get("strength", 0), reverse=True)[:5]
    rows2 = []
    for s in top5_src:
        strength = s.get("strength", 0)
        chg10 = s.get("strength_10d_chg")
        s_cls = "pos-t" if strength > 55 else ("warn-t" if strength >= 45 else "neg-t")
        chg10_color = "#00BF6F" if chg10 and chg10 > 0 else "#FF0037"
        chg10_str = f'<span style="font-size:10px;color:{chg10_color};">{chg10:+.1f} 10d</span>' if chg10 is not None else ""
        rows2.append(
            f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"padding:3px 0;border-bottom:1px solid #eee;font-size:12px;'>"
            f"<span style='font-weight:600;'>{s['sector']}</span>"
            f"<span><span class='{s_cls}' style='font-weight:700;margin-right:6px;'>RSI {strength:.1f}</span>{chg10_str}</span>"
            f"</div>"
        )
    _rows2_html = "".join(rows2) if rows2 else "<span style='color:#999'>—</span>"
    card2 = (
        f"<div class='ov-card'>"
        f"<div class='ov-label'>Top 5 Strongest Sectors · RSI14</div>"
        f"<div style='margin-top:8px;'>{_rows2_html}</div>"
        f"</div>"
    )

    # Card 3 — Top 5 RS stocks
    top5 = sorted(screened, key=lambda x: x.get("rs_strength_pct", 0), reverse=True)[:5]
    rows3 = []
    for r in top5:
        chg = r.get("PRICE_PCT_1D", 0) or 0
        rs = r.get("rs_strength_pct", 0)
        chg_cls = "#00BF6F" if chg > 0 else "#FF0037"
        rows3.append(
            f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"padding:3px 0;border-bottom:1px solid #eee;font-size:12px;'>"
            f"<span style='font-weight:700;color:#173F35;'>{r['TICKER']}</span>"
            f"<span>"
            f"<span style='color:#00BF6F;font-weight:700;margin-right:8px;'>RS {rs:+.1f}%</span>"
            f"<span style='color:{chg_cls};'>{chg:+.1f}%</span>"
            f"</span>"
            f"</div>"
        )
    card3 = (
        f"<div class='ov-card'>"
        f"<div class='ov-label'>Top 5 RS Stocks</div>"
        f"<div style='margin-top:8px;'>{''.join(rows3)}</div>"
        f"</div>"
    )

    return card1 + "\n" + card2 + "\n" + card3


# ---------------------------------------------------------------------------
# Regime — metric cards
# ---------------------------------------------------------------------------

def _mc_class(val, low_bad=False):
    """Return pos/neg/warn/neu card class based on value relative to 50."""
    try:
        v = float(val)
        if low_bad:
            if v > 60: return "pos"
            if v >= 45: return "warn"
            return "neg"
        else:
            if v > 60: return "pos"
            if v >= 45: return "warn"
            return "neg"
    except: return "neu"

def render_metric_cards(regime):
    if not regime: return ""
    ind = regime.get("indicators", {})
    cls = regime.get("classifications", {})
    div = regime.get("divergence", {})
    gap = div.get("gap", 0)

    # RSI21
    rsi_v   = ind.get("rsi21", 0)
    rsi_cls = "pos" if rsi_v > 60 else ("warn" if rsi_v >= 50 else "neg")
    # Breadth
    br_v   = ind.get("breadth_pct", 0)
    br_cls = "pos" if br_v > 60 else ("warn" if br_v >= 40 else "neg")
    # NHNL
    nh_v   = ind.get("nhnl_rsi", 0)
    nh_cls = "pos" if nh_v > 60 else ("warn" if nh_v >= 40 else "neg")
    # MFI
    mf_v   = ind.get("mfi_rsi", 0)
    mf_cls = "pos" if mf_v > 60 else ("warn" if mf_v >= 45 else "neg")
    # AD
    ad_v   = ind.get("ad_rsi", 0) or 0
    ad_cls = "pos" if ad_v > 60 else ("warn" if ad_v >= 45 else "neg")
    # Gap
    gap_cls = "neg" if gap > 12 else ("pos" if gap < -12 else "neu")
    gap_sub = "⚠ Bearish gap" if gap > 20 else ("Bearish gap" if gap > 12 else ("Bullish gap" if gap < -12 else "Aligned"))

    cards = [
        (rsi_cls, "RSI 21D", f"{rsi_v:.1f}", cls.get("trend", "—")),
        (br_cls,  "Breadth % &gt; MA50", f"{br_v:.1f}%", cls.get("breadth", "—")),
        (nh_cls,  "NHNL RSI", f"{nh_v:.1f}", cls.get("nhnl", "—")),
        (mf_cls,  "MFI RSI",  f"{mf_v:.1f}", cls.get("mfi",  "—")),
        (ad_cls,  "A/D RSI",  f"{ad_v:.1f}", cls.get("ad",   "—")),
        (gap_cls, "Gap Divergence", f"{gap:+.1f}", gap_sub),
        ("neu",   "Allocation", f"{regime.get('allocation', '—')}%", "recommended"),
    ]
    return "\n".join(
        f"<div class='mc {c}'><div class='mc-label'>{lbl}</div>"
        f"<div class='mc-value'>{val}</div><div class='mc-sub'>{sub}</div></div>"
        for c, lbl, val, sub in cards
    )


# ---------------------------------------------------------------------------
# Regime — executive summary warnings
# ---------------------------------------------------------------------------

def render_warnings(regime):
    if not regime: return ""
    ind  = regime.get("indicators", {})
    div  = regime.get("divergence", {})
    gap  = div.get("gap", 0)
    warnings = []

    if abs(gap) > 12:
        direction = "above" if gap > 0 else "below"
        warnings.append(
            f"<b>Gap Divergence {gap:+.1f}</b> — RSI 21D is {abs(gap):.1f} pts {direction} "
            f"the internal average ({div.get('internal_avg', '?')}). "
            f"{'Index strength driven by narrow leadership.' if gap > 0 else 'Internals leading price — potential bounce.'}"
        )

    br = ind.get("breadth_pct", 50)
    if br < 45:
        warnings.append(
            f"<b>Breadth only {br:.1f}%</b> — fewer than half of stocks above MA50 "
            f"despite the headline index level. Distribution risk elevated."
        )
    elif br > 72:
        warnings.append(
            f"<b>Breadth at {br:.1f}%</b> — very extended. Watch for breadth contraction as a leading warning."
        )

    nhnl = ind.get("nhnl_rsi", 50)
    if nhnl < 35:
        warnings.append(
            f"<b>NHNL RSI collapsed to {nhnl:.1f}</b> — new highs drying up rapidly. "
            f"Momentum exhaustion beneath the surface."
        )
    elif nhnl > 72:
        warnings.append(
            f"<b>NHNL RSI at {nhnl:.1f}</b> — very strong but watch for reversal if it starts declining."
        )

    if div.get("severity") in ("Severe", "Moderate"):
        warnings.append(
            f"<b>Divergence severity: {div['severity']}</b> — "
            f"{'high reversal risk, consider reducing exposure.' if div.get('type') == 'bearish' else 'potential bottom forming, watch for confirmation.'}"
        )

    if not warnings:
        return ""

    items = "".join(f"<li>{w}</li>" for w in warnings)
    return f'<div class="warn-box"><b>⚠ KEY WARNINGS:</b><ul>{items}</ul></div>'


# ---------------------------------------------------------------------------
# Regime — divergence checklist
# ---------------------------------------------------------------------------

def _dir_row(label, chg):
    if chg is None:
        return f"<div class='div-row'><span class='ind'>{label}</span><span class='val flat'>—</span></div>"
    sign  = "▲" if chg > 0 else ("▼" if chg < 0 else "→")
    cls   = "up" if chg > 0 else ("down" if chg < 0 else "flat")
    return f"<div class='div-row'><span class='ind'>{label}</span><span class='val {cls}'>{chg:+.1f} {sign}</span></div>"


def render_div_direction_rows(detail_n):
    if not detail_n: return ""
    rows = [
        _dir_row("RSI 21D",  detail_n.get("rsi21")),
        _dir_row("Breadth",  detail_n.get("breadth")),
        _dir_row("NHNL RSI", detail_n.get("nhnl")),
        _dir_row("MFI RSI",  detail_n.get("mfi")),
        _dir_row("A/D RSI",  detail_n.get("ad")),
        f"<div class='div-row'><span class='ind'>Opposite count</span>"
        f"<span class='val bold'>{detail_n.get('opposite_count',0)} of {detail_n.get('total_internals',4)}</span></div>",
    ]
    return "\n".join(rows)


def render_gap_rows(regime):
    if not regime: return ""
    ind = regime.get("indicators", {})
    div = regime.get("divergence", {})
    gap = div.get("gap", 0)
    avg = div.get("internal_avg", 0)
    gap_cls = "down" if gap > 12 else ("up" if gap < -12 else "flat")

    rows = [
        f"<div class='div-row'><span class='ind'>RSI 21D</span><span class='val bold'>{ind.get('rsi21', '?'):.1f}</span></div>",
        f"<div class='div-row'><span class='ind'>Breadth (raw %)</span><span class='val'>{ind.get('breadth_pct', '?'):.1f}</span></div>",
        f"<div class='div-row'><span class='ind'>NHNL RSI</span><span class='val'>{ind.get('nhnl_rsi', '?'):.1f}</span></div>",
        f"<div class='div-row'><span class='ind'>MFI RSI</span><span class='val'>{ind.get('mfi_rsi', '?'):.1f}</span></div>",
        f"<div class='div-row'><span class='ind'>A/D RSI</span><span class='val'>{(ind.get('ad_rsi') or 0):.1f}</span></div>",
        f"<div class='div-row'><span class='ind'>Internal Average</span><span class='val bold'>{avg:.1f}</span></div>",
        f"<div class='div-row' style='border-top:1px solid #ddd;padding-top:6px;margin-top:4px;'>"
        f"<span class='ind fw'>GAP = RSI − Avg</span>"
        f"<span class='val {gap_cls} fw'>{gap:+.1f}</span></div>",
    ]
    return "\n".join(rows)


def div_verdict(diverged, opposite, total, timeframe):
    if diverged:
        return "divergent", f"⚠ DIVERGENCE ({opposite}/{total} opposite)"
    return "aligned", f"✓ NO DIVERGENCE ({opposite}/{total} opposite)"


def gap_verdict(gap):
    a = abs(gap)
    if gap > 20:   return "divergent", "⚠ SEVERE BEARISH GAP (>+20)"
    if gap > 12:   return "warning",   "⚠ BEARISH GAP (+12 to +20)"
    if gap < -20:  return "divergent", "⚠ SEVERE BULLISH GAP (<−20)"
    if gap < -12:  return "warning",   "⚠ BULLISH GAP (−12 to −20)"
    return "aligned", "✓ ALIGNED (within ±12)"


# ---------------------------------------------------------------------------
# Regime — scenario cards (DC style, s1/s2/s3)
# ---------------------------------------------------------------------------

def render_bear_score_table(regime):
    bd = regime.get("bear_detail")
    if not bd:
        return ""
    score = bd["score"]
    tier  = bd["tier"]
    tier_color = {"Clean": "#00BF6F", "Caution": "#C08F4F", "Warning": "#FF671B", "High Risk": "#FF0037"}.get(tier, "#97999B")
    bar_w = min(100, score)

    rows_html = ""
    for c in bd["components"]:
        pts = c["pts"]
        if pts > 0:
            pts_color = "#FF671B"
            pts_str   = f"+{pts}"
        elif pts < 0:
            pts_color = "#00BF6F"
            pts_str   = str(pts)
        else:
            pts_color = "#97999B"
            pts_str   = "0"
        val_bold = pts != 0
        rows_html += f"""<tr>
  <td style="padding:8px 12px;font-weight:600;color:#101820;white-space:nowrap;">{c['label']}</td>
  <td style="padding:8px 12px;font-weight:{'800' if val_bold else '500'};color:{'#101820' if val_bold else '#97999B'};white-space:nowrap;">{c['value']}</td>
  <td style="padding:8px 12px;color:#555;font-size:12px;line-height:1.4;">{c['note']}</td>
  <td style="padding:8px 12px;font-weight:800;color:{pts_color};text-align:right;white-space:nowrap;">{pts_str} pts</td>
</tr>"""

    return f"""<div style="background:#f9f9f9;border:1px solid #eee;border-radius:12px;padding:18px 20px;margin-bottom:18px;">
  <div style="display:flex;align-items:center;gap:16px;margin-bottom:14px;flex-wrap:wrap;">
    <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.6px;color:#97999B;">Bear Score</div>
    <div style="font-size:28px;font-weight:800;color:{tier_color};line-height:1;">{score}<span style="font-size:14px;font-weight:600;color:#97999B;"> / 100</span></div>
    <div style="background:{tier_color};color:#fff;font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px;letter-spacing:0.4px;">{tier.upper()}</div>
    <div style="flex:1;min-width:120px;background:#e5e5e5;border-radius:4px;height:6px;">
      <div style="width:{bar_w}%;background:{tier_color};height:6px;border-radius:4px;"></div>
    </div>
  </div>
  <table style="width:100%;border-collapse:collapse;font-family:Manrope,sans-serif;font-size:13px;">
    <thead>
      <tr style="border-bottom:1px solid #e0e0e0;">
        <th style="padding:6px 12px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.4px;color:#97999B;">Component</th>
        <th style="padding:6px 12px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.4px;color:#97999B;">Value</th>
        <th style="padding:6px 12px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.4px;color:#97999B;">Reading</th>
        <th style="padding:6px 12px;text-align:right;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.4px;color:#97999B;">Score</th>
      </tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>
</div>"""


def render_scenario_cards(scenarios):
    out = []
    for i, s in enumerate(scenarios[:3]):
        cls    = f"s{i+1}"
        prob   = s.get("probability", 0)
        alloc  = s.get("allocation", "—")
        out.append(
            f"<div class='scenario {cls}'>"
            f"<h3>{s.get('name','Scenario')}</h3>"
            f"<div class='prob'>{prob}%</div>"
            f"<div class='prob-bar'><div class='prob-fill' style='width:{prob}%'></div></div>"
            f"<div class='sc-detail'>{s.get('logic','')}</div>"
            f"<div class='sc-detail'><b>✅ Confirm:</b> {s.get('confirmation','—')}</div>"
            f"<div class='sc-detail'><b>❌ Invalidate:</b> {s.get('invalidation','—')}</div>"
            f"<span class='sc-alloc'>Allocation: {alloc}%</span>"
            f"</div>"
        )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Regime — phase table rows
# ---------------------------------------------------------------------------

def render_phase_rows(phases):
    out = []
    for i, p in enumerate(phases, 1):
        ret = p.get("return_pct", 0)
        cls = "pos-t" if ret > 0 else ("neg-t" if ret < 0 else "")
        out.append(
            f"<tr>"
            f"<td class='fw'>{i}</td>"
            f"<td>{p.get('start','?')} → {p.get('end','?')}</td>"
            f"<td>{p.get('regime','—')}</td>"
            f"<td class='tr'>{fmt(p.get('vni_end'), 1)}</td>"
            f"<td class='tr {cls}'>{fmt_pct(ret, 1, sign=True)}</td>"
            f"<td style='font-size:11px;color:#666;'>{p.get('divergence','—')}</td>"
            f"</tr>"
        )
    return "\n".join(out) if out else "<tr><td colspan='6' style='color:#999;text-align:center;'>No phase data</td></tr>"


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def main():
    snapshot = json.loads((DATA_DIR / "latest.json").read_text())
    tmpl     = TEMPLATE.read_text()

    vni       = snapshot["vnindex"]
    universe  = snapshot["universe"]
    regime    = snapshot.get("regime", {})

    # Divergence detail
    div    = regime.get("divergence", {})
    detail = div.get("detail", {})
    d5     = detail.get("5d", {})
    d10    = detail.get("10d", {})
    gap    = div.get("gap", 0)

    # Verdict helpers
    v5_cls,  v5_txt  = div_verdict(d5.get("diverged", False),  d5.get("opposite_count", 0),  d5.get("total_internals", 4),  "5d")
    v10_cls, v10_txt = div_verdict(d10.get("diverged", False), d10.get("opposite_count", 0), d10.get("total_internals", 4), "10d")
    vg_cls,  vg_txt  = gap_verdict(gap)

    # Exec div class
    div_flag = regime.get("divergence_flag", "ALIGNED")
    exec_div_cls = "danger" if "Bearish" in div_flag else ("ok" if "Bullish" in div_flag else "")

    # Gap exec class
    gap_exec_cls = "danger" if gap > 12 else ("ok" if gap < -12 else "")

    # Severity class
    sev = div.get("severity", "None")
    sev_cls = "danger" if sev in ("Severe", "Moderate") else ("warn" if sev in ("Mild", "Early Warning") else "ok")

    # Chart JSON from regime history
    hist = regime.get("history", {})
    chart_json = json.dumps(hist)

    replacements = {
        "{{latest_date}}":     snapshot["latest_date"],
        "{{generated_at}}":    (datetime.utcnow() + timedelta(hours=7)).strftime("%Y %b %d - %H:%M"),
        # VNIndex header
        "{{vni_close}}":       fmt(vni["close"], 2),
        "{{vni_change}}":      fmt(vni["change"], 2),
        "{{vni_change_pct}}":  fmt_pct(vni["change_pct"], 2, sign=True),
        "{{vni_color}}":       color(vni["change"]),
        # Overview cards
        "{{overview_cards}}": render_overview_cards(regime, snapshot.get("screened", []), snapshot.get("sector_analysis", [])),
        # Exec summary
        "{{regime_name}}":          regime.get("regime_name", "—"),
        "{{regime_div_flag}}":       div_flag,
        "{{regime_exec_div_class}}": exec_div_cls,
        "{{regime_dir5d}}":          "Yes" if div.get("dir_5d") else "No",
        "{{regime_dir10d}}":         "Yes" if div.get("dir_10d") else "No",
        "{{regime_gap}}":            f"{gap:+.1f}",
        "{{regime_gap_exec_class}}": gap_exec_cls,
        "{{regime_internal_avg}}":   fmt(div.get("internal_avg"), 1),
        "{{regime_div_severity}}":   sev,
        "{{regime_sev_class}}":      sev_cls,
        "{{regime_allocation}}":     str(regime.get("allocation", "—")),
        "{{exec_warnings}}":         render_warnings(regime),
        "{{bear_score_table}}":      render_bear_score_table(regime),
        # Metric cards
        "{{regime_metric_cards}}":   render_metric_cards(regime),
        # Charts
        "{{chart_json}}":            chart_json,
        "{{full_chart_json}}":       json.dumps(regime.get("full_history", hist)),
        "{{nhnl_chart_json}}":       json.dumps(snapshot.get("nhnl_chart", {})),
        "{{breadth_chart_json}}":    json.dumps(snapshot.get("breadth_chart", {})),
        "{{mfi_chart_json}}":        json.dumps(snapshot.get("mfi_chart", {})),
        "{{ad_chart_json}}":         json.dumps(snapshot.get("ad_chart", {})),
        "{{gap_chart_json}}":        json.dumps(snapshot.get("gap_chart", {})),
        # Divergence checklist
        "{{regime_div5d_rows}}":         render_div_direction_rows(d5),
        "{{regime_div5d_verdict_class}}": v5_cls,
        "{{regime_div5d_verdict_text}}":  v5_txt,
        "{{regime_div10d_rows}}":         render_div_direction_rows(d10),
        "{{regime_div10d_verdict_class}}": v10_cls,
        "{{regime_div10d_verdict_text}}":  v10_txt,
        "{{regime_gap_rows}}":            render_gap_rows(regime),
        "{{regime_gap_verdict_class}}":   vg_cls,
        "{{regime_gap_verdict_text}}":    vg_txt,
        # Scenarios & phases
        "{{regime_scenario_cards}}": render_scenario_cards(regime.get("scenarios", [])),
        "{{regime_phase_rows}}":     render_phase_rows(regime.get("phases", [])),
        # Tables
        "{{screened_rows}}":        render_screened_rows(snapshot.get("screened", [])),
        "{{sector_analysis_rows}}": render_sector_analysis_rows(snapshot.get("sector_analysis", [])),
    }

    html = tmpl
    for k, v in replacements.items():
        html = html.replace(k, str(v))

    DOCS.mkdir(exist_ok=True)
    (DOCS / "data").mkdir(exist_ok=True)
    (DOCS / "index.html").write_text(html)
    shutil.copy(DATA_DIR / "latest.json", DOCS / "data" / "latest.json")
    shutil.copy(DATA_DIR / "latest.json", DOCS / "data" / f"{snapshot['latest_date']}.json")
    print(f"Rendered docs/index.html for {snapshot['latest_date']}")


if __name__ == "__main__":
    main()
