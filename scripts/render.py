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
# Seasonality — 2026 YTD cumulative return from full_history
# ---------------------------------------------------------------------------

def render_seasonality_2026(regime):
    full = regime.get("full_history", {})
    dates   = full.get("dates", [])
    vnindex = full.get("vnindex", [])
    pairs = [(d, v) for d, v in zip(dates, vnindex)
             if d and d >= "2026-01-01" and v is not None]
    if len(pairs) < 2:
        return json.dumps({"dates": [], "cum_returns": []})
    base  = pairs[0][1]           # Jan 5 = base day, not plotted
    pairs = pairs[1:]             # start from Jan 6 (tdoy 2)
    return json.dumps({
        "dates":       [p[0] for p in pairs],
        "cum_returns": [round((p[1] / base - 1) * 100, 4) for p in pairs],
    })


# ---------------------------------------------------------------------------
# Composite Man Masterplan narrative
# ---------------------------------------------------------------------------

def _chg(arr, n):
    """arr[-1] - arr[-(n+1)], or None if insufficient data."""
    if len(arr) > n and arr[-1] is not None and arr[-(n+1)] is not None:
        return arr[-1] - arr[-(n+1)]
    return None


def render_composite_man(regime):
    if not regime:
        return "<p style='color:#97999B;font-style:italic;'>No regime data available.</p>"

    ind    = regime.get("indicators", {})
    rsi    = ind.get("rsi21", 50)
    breadth = ind.get("breadth_pct", 50)
    nhnl   = ind.get("nhnl_rsi", 50)
    price  = regime.get("vnindex", 0)
    div    = regime.get("divergence", {})
    gap    = div.get("gap", 0)
    bear_d = regime.get("bear_detail", {})
    bear_score = bear_d.get("score", 0) if bear_d else 0

    # Recent changes data
    hist       = regime.get("history", {})
    h_vni      = hist.get("vnindex", [])
    h_breadth  = hist.get("breadth", [])
    nhnl_abs   = regime.get("nhnl_history", {}).get("nhnl", [])

    vni_now      = h_vni[-1]     if h_vni     else None
    br_now       = h_breadth[-1] if h_breadth else None
    nhnl_abs_now = nhnl_abs[-1]  if nhnl_abs  else None

    vni_1d,  vni_5d,  vni_10d  = _chg(h_vni, 1),     _chg(h_vni, 5),     _chg(h_vni, 10)
    br_1d,   br_5d,   br_10d   = _chg(h_breadth, 1), _chg(h_breadth, 5), _chg(h_breadth, 10)
    nhnl_1d, nhnl_5d, nhnl_10d = _chg(nhnl_abs, 1),  _chg(nhnl_abs, 5),  _chg(nhnl_abs, 10)

    # Divergence dynamics data
    d5           = div.get("detail", {}).get("5d",  {})
    d10          = div.get("detail", {}).get("10d", {})
    rsi_d5       = d5.get("rsi21", 0)   or 0
    br_d5        = d5.get("breadth", 0) or 0
    nhnl_d5      = d5.get("nhnl", 0)    or 0
    rsi_d10      = d10.get("rsi21", 0)  or 0
    br_d10       = d10.get("breadth", 0) or 0
    nhnl_d10     = d10.get("nhnl", 0)   or 0
    severity     = div.get("severity", "None")
    internal_avg = div.get("internal_avg", 0) or 0

    avg_int_d5  = (br_d5  + nhnl_d5)  / 2
    avg_int_d10 = (br_d10 + nhnl_d10) / 2

    if rsi_d5 < -1 and avg_int_d5 > 1:
        dir5 = "resolving"
    elif rsi_d5 > 1 and avg_int_d5 < -1:
        dir5 = "deepening"
    elif rsi_d5 < -1 and avg_int_d5 < -1:
        dir5 = "broad_deterioration"
    elif rsi_d5 > 1 and avg_int_d5 > 1:
        dir5 = "broad_improvement"
    else:
        dir5 = "stable"

    if gap > 20:
        gap_state = "severe_bearish"
        gap_desc  = f"RSI 21D is running {gap:+.1f} pts above the internal average ({internal_avg:.1f}) — a severe bearish divergence"
    elif gap > 12:
        gap_state = "moderate_bearish"
        gap_desc  = f"RSI 21D sits {gap:+.1f} pts above the internal average ({internal_avg:.1f}) — a moderate bearish gap is in place"
    elif gap < -20:
        gap_state = "severe_bullish"
        gap_desc  = f"RSI 21D is {abs(gap):.1f} pts below the internal average ({internal_avg:.1f}) — internals are significantly stronger than the headline"
    elif gap < -12:
        gap_state = "moderate_bullish"
        gap_desc  = f"RSI 21D sits {abs(gap):.1f} pts below the internal average ({internal_avg:.1f}) — internals are outpacing the headline index"
    else:
        gap_state = "aligned"
        gap_desc  = f"RSI 21D and internal indicators are closely aligned (gap: {gap:+.1f} pts, internal avg: {internal_avg:.1f})"

    rsi_d5_dir = "fell" if rsi_d5 < 0 else "rose"
    br_d5_dir  = "gained" if br_d5 > 0 else "lost"
    nh_d5_dir  = "gained" if nhnl_d5 > 0 else "lost"

    div_s1 = f"{gap_desc}."
    if dir5 == "resolving":
        div_s2 = (f"Over 5 days, RSI 21D {rsi_d5_dir} {abs(rsi_d5):.1f} pts while breadth {br_d5_dir} {abs(br_d5):.1f} pts "
                  f"and NHNL RSI {nh_d5_dir} {abs(nhnl_d5):.1f} pts — the gap is actively closing as internals recover faster than the headline.")
    elif dir5 == "deepening":
        div_s2 = (f"Over 5 days, RSI 21D {rsi_d5_dir} {abs(rsi_d5):.1f} pts while breadth {br_d5_dir} {abs(br_d5):.1f} pts "
                  f"and NHNL RSI {nh_d5_dir} {abs(nhnl_d5):.1f} pts — divergence is deepening with headline momentum running counter to internal health.")
    elif dir5 == "broad_deterioration":
        div_s2 = (f"Over 5 days, RSI 21D {rsi_d5_dir} {abs(rsi_d5):.1f} pts alongside breadth losing {abs(br_d5):.1f} pts "
                  f"and NHNL RSI losing {abs(nhnl_d5):.1f} pts — this is broad deterioration rather than a classic divergence pattern.")
    elif dir5 == "broad_improvement":
        div_s2 = (f"Over 5 days, RSI 21D {rsi_d5_dir} {abs(rsi_d5):.1f} pts together with breadth gaining {abs(br_d5):.1f} pts "
                  f"and NHNL RSI gaining {abs(nhnl_d5):.1f} pts — broad improvement with headline and internals moving in tandem.")
    else:
        div_s2 = (f"Over 5 days, RSI 21D moved {rsi_d5:+.1f} pts with breadth at {br_d5:+.1f} pts "
                  f"and NHNL RSI at {nhnl_d5:+.1f} pts — mixed signals with no clear directional bias.")

    rsi_d10_dir = "falling" if rsi_d10 < 0 else "rising"
    int_d10_dir = "recovering" if avg_int_d10 > 0 else "deteriorating"
    div_s3 = (f"The 10-day view shows RSI 21D {rsi_d10_dir} {rsi_d10:+.1f} pts with internals {int_d10_dir} "
              f"(breadth {br_d10:+.1f} pts, NHNL RSI {nhnl_d10:+.1f} pts).")

    if gap_state in ("severe_bearish", "moderate_bearish") and dir5 == "resolving":
        div_s4 = "If internals continue recovering toward RSI levels the divergence risk diminishes — a healthier, broader rally could follow."
    elif gap_state in ("severe_bearish", "moderate_bearish") and dir5 == "deepening":
        div_s4 = "A widening gap with internals lagging the headline is the most dangerous configuration — distribution tends to accelerate at this stage."
    elif gap_state in ("severe_bearish", "moderate_bearish") and dir5 == "broad_deterioration":
        div_s4 = "Both headline and internals deteriorating together reduces the divergence gap but broadens systemic downside risk."
    elif gap_state == "aligned" and dir5 == "broad_improvement":
        div_s4 = "Alignment between headline and internals with both trending up is the healthiest configuration — no divergence risk, trend extension likely."
    elif gap_state == "aligned" and dir5 == "broad_deterioration":
        div_s4 = "Watch for gap divergence to emerge if RSI 21D holds while breadth continues falling — this is the sequence where divergences are born."
    elif gap_state in ("moderate_bullish", "severe_bullish") and dir5 in ("resolving", "broad_improvement"):
        div_s4 = "Internals leading the headline higher is a bullish structural signal — the type of confirmation that precedes sustained markup phases."
    else:
        div_s4 = f"With divergence severity at '{severity}', the current setup warrants monitoring but has not yet reached a critical threshold."

    div_narrative = f"{div_s1} {div_s2} {div_s3} {div_s4}"

    # ── Multi-factor phase assessment ──────────────────────────────────────────
    # Derive directional signals from actual VNIndex, breadth, and NHNL data
    vni_trend_up   = (vni_5d  or 0) >  5  and (vni_10d or 0) >  0
    vni_trend_dn   = (vni_5d  or 0) < -5
    vni_stalling   = not vni_trend_up and not vni_trend_dn

    br_expanding   = (br_5d  or 0) >  1.5
    br_contracting = (br_5d  or 0) < -1.5
    br_wide        = (br_now or 0) >= 52
    br_narrow      = (br_now or 0) <  38

    nhnl_improving = (nhnl_5d      or 0) >  20
    nhnl_worsening = (nhnl_5d      or 0) < -20
    nhnl_deep      = (nhnl_abs_now or 0) < -300
    nhnl_ok        = (nhnl_abs_now or 0) >= -100

    bearish_gap = gap_state in ("severe_bearish", "moderate_bearish")
    bullish_gap = gap_state in ("severe_bullish", "moderate_bullish")

    # ── Phase priority (strongest evidence first) ──────────────────────────────
    if vni_trend_dn and nhnl_deep and (nhnl_worsening or br_narrow):
        # MARKDOWN: price falling, NHNL deeply negative and deteriorating
        phase = "markdown"
        phase_label = "Markdown / Distribution Confirmed"
        phase_color = "#FF0037"
        v5s  = f"{abs(vni_5d):.1f}"  if vni_5d  is not None else "—"
        v10s = f"{abs(vni_10d):.1f}" if vni_10d is not None else "—"
        v10_dir = "lower" if (vni_10d or 0) < 0 else "higher"
        nhnl_s     = f"{nhnl_abs_now:+,.0f}" if nhnl_abs_now is not None else "—"
        nhnl_chg_s = f"{abs(nhnl_5d):.0f} further" if nhnl_5d is not None else ""
        br_s     = f"{br_now:.1f}%"   if br_now  is not None else "—"
        br_chg_s = f"{br_5d:+.1f} pp over 5 days" if br_5d is not None else ""
        rsi_lag = (f" RSI 21D at {rsi:.1f} may still appear elevated — that is a lagging artefact: "
                   f"the headline index is slower to price in the deterioration that breadth and NHNL have already confirmed."
                   ) if rsi > 48 else ""
        summary = (
            f"The Composite Man has moved into active markdown. "
            f"VNIndex has shed {v5s} pts over 5 days and {v10s} pts over 10 days ({v10_dir}) — "
            f"the selling pressure is sustained and multi-session, not a single-day event. "
            f"Breadth stands at {br_s}{(f', {br_chg_s}' if br_chg_s else '')}, "
            f"meaning fewer than two in five VNI stocks hold above their MA50 — "
            f"the rank-and-file is being abandoned as supply overwhelms demand. "
            f"The NHNL net count sits at {nhnl_s}"
            f"{(f', having worsened by {nhnl_chg_s} in 5 days' if nhnl_chg_s else '')} — "
            f"new lows are dominating across the entire universe.{rsi_lag} "
            f"His playbook: sell into any bounce, use temporary strength to offload remaining supply, "
            f"and keep weak hands shaking out at lower prices. Rallies here are exit windows, not opportunities."
        )
        validation = (
            f"Price continuing lower, NHNL net count deteriorating further below {nhnl_s}, "
            f"and breadth failing to recover above 40% would confirm the markdown phase is intact and progressing."
        )
        invalidation = (
            f"Breadth recovering above 45% on expanding volume, NHNL net count improving for 3+ consecutive days, "
            f"and VNIndex 5-day change turning positive would suggest accumulation is beginning — "
            f"Composite Man shifting from active selling to re-accumulation at lower levels."
        )

    elif not vni_trend_dn and bearish_gap and (nhnl_worsening or br_contracting):
        # DISTRIBUTION: price resilient/advancing while internals erode
        phase = "distribution_test"
        phase_label = "Distribution Test — Divergence Building"
        phase_color = "#FF671B"
        vni_dir_s  = "advancing" if vni_trend_up else "holding"
        v5s        = f"{vni_5d:+.1f}" if vni_5d is not None else "—"
        br_s       = f"{br_now:.1f}%"  if br_now is not None else "—"
        br_chg_s   = f"{br_5d:+.1f} pp" if br_5d is not None else "—"
        nhnl_s     = f"{nhnl_abs_now:+,.0f}" if nhnl_abs_now is not None else "—"
        nhnl_chg_s = f"{nhnl_5d:+.0f}" if nhnl_5d is not None else "—"
        summary = (
            f"The Composite Man is running a classic distribution play: "
            f"VNIndex is {vni_dir_s} ({v5s} pts over 5 days, price {price:,.1f}) "
            f"while internals quietly erode beneath the surface. "
            f"Breadth has moved {br_chg_s} over 5 days to {br_s} — "
            f"only {br_s} of VNI stocks hold above their MA50, a narrow base that belies the headline resilience. "
            f"NHNL net count sits at {nhnl_s} and has shifted {nhnl_chg_s} over 5 days, "
            f"confirming new lows are expanding even as the index looks supported. "
            f"The RSI 21D gap of {gap:+.1f} pts above internals is the fingerprint: "
            f"he is selling into strength he engineered, letting weaker stocks absorb the supply. "
            f"Bear score of {bear_score} signals elevated distribution pressure. "
            f"Retail sees an index holding up; Composite Man is exiting through that buying."
        )
        validation = (
            f"Gap divergence widening beyond +20, breadth failing to recover above 45%, "
            f"and NHNL net count continuing to worsen below {nhnl_s} would confirm "
            f"the distribution is progressing — markdown becomes increasingly likely."
        )
        invalidation = (
            f"Breadth recovering above 50% on expanding volume, NHNL net count turning and holding positive, "
            f"and the gap divergence closing below +10 would suggest the index strength is genuine — "
            f"Composite Man re-accumulating, not distributing."
        )

    elif not vni_trend_dn and bearish_gap and br_narrow:
        # DISTRIBUTION (stalling + narrow + gap): softer distribution signal
        phase = "distribution_test"
        phase_label = "Distribution Test — Divergence Building"
        phase_color = "#FF671B"
        v5s    = f"{vni_5d:+.1f}" if vni_5d is not None else "—"
        br_s   = f"{br_now:.1f}%" if br_now is not None else "—"
        nhnl_s = f"{nhnl_abs_now:+,.0f}" if nhnl_abs_now is not None else "—"
        summary = (
            f"The Composite Man's distribution fingerprint is visible. "
            f"VNIndex is broadly flat ({v5s} pts, 5d, price {price:,.1f}) "
            f"while internals are structurally weak: breadth at {br_s} and NHNL net count at {nhnl_s}. "
            f"The RSI 21D gap of {gap:+.1f} pts above the internal average ({internal_avg:.1f}) "
            f"signals the headline is being propped while distribution continues below the surface. "
            f"Bear score of {bear_score} reflects the accumulated internal deterioration. "
            f"This configuration — index stable, internals weak, RSI running ahead — "
            f"is how distribution phases look before they tip into markdown."
        )
        validation = (
            f"NHNL net count continuing to worsen and gap divergence holding above +15 "
            f"would confirm the distribution phase is intact and deepening."
        )
        invalidation = (
            f"Breadth recovering above 50% and NHNL net count turning consistently positive "
            f"would signal the gap is a temporary artefact — Composite Man re-accumulating, not distributing."
        )

    elif vni_trend_up and br_wide and (nhnl_ok or nhnl_improving):
        # MARKUP HEALTHY: price rising, broad participation, NHNL positive
        phase = "markup_healthy"
        phase_label = "Markup — Broad Participation"
        phase_color = "#00BF6F"
        v5s  = f"{vni_5d:+.1f}"  if vni_5d  is not None else "—"
        v10s = f"{vni_10d:+.1f}" if vni_10d is not None else "—"
        br_s     = f"{br_now:.1f}%" if br_now is not None else "—"
        br_chg_s = f"{br_5d:+.1f} pp over 5 days" if br_5d is not None else ""
        nhnl_s   = f"{nhnl_abs_now:+,.0f}" if nhnl_abs_now is not None else "—"
        gap_interp = ("tracking" if abs(gap) <= 12 else ("ahead of" if gap < 0 else "slightly stretched above"))
        summary = (
            f"The Composite Man is in a healthy markup phase. "
            f"VNIndex has gained {v5s} pts over 5 days and {v10s} pts over 10 days — "
            f"the price trend is confirmed across multiple timeframes. "
            f"Breadth at {br_s}{(f' ({br_chg_s})' if br_chg_s else '')} shows the majority of VNI stocks "
            f"participating — this is broad-based buying, not narrow speculation. "
            f"NHNL net count at {nhnl_s} confirms new highs are expanding across the universe. "
            f"RSI 21D at {rsi:.1f} reflects trend strength, with the gap of {gap:+.1f} pts showing "
            f"internals are {gap_interp} the headline. "
            f"His playbook: push prices higher on expanding volume, keep retail engaged, "
            f"and fuel momentum while internals remain healthy. This phase has room to run."
        )
        validation = (
            f"Breadth holding above 55%, NHNL net count staying positive, "
            f"and VNIndex 5-day change remaining above +10 pts would confirm "
            f"the markup phase is in full force — pullbacks should be bought."
        )
        invalidation = (
            f"Breadth rolling below 45% or NHNL net count deteriorating below -100 "
            f"would signal distribution is beginning — Composite Man starting to unload into retail buying."
        )

    elif (vni_trend_up or (vni_stalling and (vni_5d or 0) > -3)) and (br_narrow or br_contracting):
        # MARKUP NARROWING: price up/flat but breadth failing to follow
        phase = "markup_narrowing"
        phase_label = "Late Markup — Narrowing Leadership"
        phase_color = "#C08F4F"
        v5s      = f"{vni_5d:+.1f}" if vni_5d is not None else "—"
        br_s     = f"{br_now:.1f}%" if br_now is not None else "—"
        br_chg_s = f"{br_5d:+.1f} pp over 5 days" if br_5d is not None else ""
        nhnl_s   = f"{nhnl_abs_now:+,.0f}" if nhnl_abs_now is not None else "—"
        nhnl_dir_s = ("worsening" if (nhnl_5d or 0) < -20 else ("improving" if (nhnl_5d or 0) > 20 else "flat"))
        summary = (
            f"The Composite Man is in late markup with the index at {price:,.1f}, "
            f"but the rally is increasingly carried by fewer stocks. "
            f"VNIndex has moved {v5s} pts over 5 days, yet breadth at {br_s}"
            f"{(f' ({br_chg_s})' if br_chg_s else '')} means fewer than two in five "
            f"VNI stocks hold above their MA50 — the advance is narrowing. "
            f"NHNL net count at {nhnl_s} is {nhnl_dir_s}, confirming the universe of "
            f"stocks making new highs is shrinking. "
            f"RSI 21D at {rsi:.1f} with a gap of {gap:+.1f} pts suggests he may still be "
            f"riding index heavyweights while quietly distributing mid and small-cap positions "
            f"into lingering retail enthusiasm. "
            f"This is a phase that demands caution: the trend may look intact at the index level "
            f"but the internal foundation is thinning."
        )
        validation = (
            f"Breadth recovering above 50% and NHNL net count turning from {nhnl_s} toward positive "
            f"would reset the leadership and confirm the markup is still healthy."
        )
        invalidation = (
            f"Breadth breaking below 30% or VNIndex 5-day change turning below -20 pts would signal "
            f"the markup is over — Composite Man has finished distributing and markdown pressure is building."
        )

    elif (vni_trend_dn or vni_stalling) and (nhnl_deep or (nhnl_abs_now or 0) < -150) and (nhnl_improving or br_expanding):
        # ACCUMULATION: price down/flat, internals deeply negative but showing early turns
        phase = "accumulation"
        phase_label = "Accumulation / Base Building"
        phase_color = "#C08F4F"
        v5s      = f"{vni_5d:+.1f}" if vni_5d is not None else "—"
        br_s     = f"{br_now:.1f}%" if br_now is not None else "—"
        br_chg_s = f"{br_5d:+.1f} pp over 5 days" if br_5d is not None else ""
        nhnl_s     = f"{nhnl_abs_now:+,.0f}" if nhnl_abs_now is not None else "—"
        nhnl_chg_s = f"{nhnl_5d:+.0f}" if nhnl_5d is not None else "—"
        turn_parts = []
        if nhnl_improving:
            turn_parts.append(f"NHNL net count has improved {nhnl_chg_s} over 5 days to {nhnl_s} — new lows are receding, an early signal")
        if br_expanding:
            turn_parts.append(f"breadth has expanded {br_5d:+.1f} pp over 5 days to {br_s} — more stocks are firming above their MA50")
        turn_note = (". ".join(turn_parts).capitalize() + ". ") if turn_parts else ""
        summary = (
            f"The Composite Man appears to be in accumulation — quietly absorbing supply at {price:,.1f} "
            f"while keeping the tape uninspiring enough to discourage retail participation. "
            f"VNIndex has moved {v5s} pts over 5 days — price is under pressure or stalling, "
            f"which suits his purpose: accumulate without attracting followers. "
            f"Breadth at {br_s} and NHNL net count at {nhnl_s} remain deeply negative, "
            f"confirming most stocks are still under distribution pressure. "
            f"{turn_note}"
            f"The pattern to watch: repeated tests of support with shrinking selling pressure on each retest. "
            f"He is patient — the markup phase will only begin once he has absorbed sufficient supply."
        )
        validation = (
            f"NHNL net count improving consistently toward -150 or better, breadth clawing back above 40%, "
            f"and VNIndex 5-day change turning and holding positive would mark the spring — "
            f"confirmation that accumulation is nearing completion."
        )
        invalidation = (
            f"VNIndex accelerating lower (5d change worsening below -50 pts), breadth collapsing under 20%, "
            f"or NHNL net count making new lows would signal this is not accumulation but active markdown."
        )

    else:
        # TRANSITION: mixed signals, no dominant phase
        phase = "transition"
        phase_label = "Transition / Indeterminate Phase"
        phase_color = "#97999B"
        v5s    = f"{vni_5d:+.1f}" if vni_5d is not None else "—"
        br_s   = f"{br_now:.1f}%" if br_now is not None else "—"
        nhnl_s = f"{nhnl_abs_now:+,.0f}" if nhnl_abs_now is not None else "—"
        summary = (
            f"The Composite Man's intentions are difficult to read at this juncture. "
            f"VNIndex has moved {v5s} pts over 5 days to {price:,.1f}, breadth sits at {br_s}, "
            f"and NHNL net count at {nhnl_s} — the market shows neither the broad participation "
            f"of a healthy markup nor the collapsed internals of a confirmed markdown. "
            f"RSI 21D at {rsi:.1f} with a gap of {gap:+.1f} pts sits in a transitional zone. "
            f"He may be in a re-test phase, probing both buyers and sellers to gauge remaining supply and demand. "
            f"During such phases he often engineers false moves in both directions to shake out committed positions. "
            f"The wisest stance is to wait for a definitive break in internals before committing aggressively."
        )
        validation = (
            f"Breadth moving decisively above 50% and NHNL net count recovering consistently above -100 "
            f"would confirm a new markup phase — Composite Man has absorbed supply and is ready to advance."
        )
        invalidation = (
            f"Breadth dropping below 30% and VNIndex 5-day change turning below -30 pts would signal "
            f"a markdown is beginning — the transitional indecision has resolved to the downside."
        )

    def _chg_row(label, val, pos_good=True):
        if val is None:
            return (f"<div style='display:flex;justify-content:space-between;align-items:center;font-size:12px;padding:2px 0;'>"
                    f"<span style='color:#97999B;'>{label}</span><span style='color:#97999B;'>—</span></div>")
        good  = val > 0 if pos_good else val < 0
        color = "#00BF6F" if good else "#FF0037"
        arrow = "▲" if val > 0 else ("▼" if val < 0 else "→")
        return (f"<div style='display:flex;justify-content:space-between;align-items:center;font-size:12px;padding:2px 0;'>"
                f"<span style='color:#97999B;'>{label}</span>"
                f"<span style='color:{color};font-weight:700;'>{val:+.1f} {arrow}</span></div>")

    def _tile(label, val_str, r1d, r5d, r10d, pos_good=True):
        rows = _chg_row("1d", r1d, pos_good) + _chg_row("5d", r5d, pos_good) + _chg_row("10d", r10d, pos_good)
        return (f"<div style='flex:1;min-width:160px;background:#f5f5f5;border-radius:10px;padding:14px 16px;'>"
                f"<div style='font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:#97999B;margin-bottom:6px;'>{label}</div>"
                f"<div style='font-size:20px;font-weight:800;color:#101820;margin-bottom:10px;'>{val_str}</div>"
                f"<div style='display:flex;flex-direction:column;gap:2px;'>{rows}</div></div>")

    vni_tile  = _tile("VNIndex",
                      f"{vni_now:,.1f}"  if vni_now  is not None else "—",
                      vni_1d,  vni_5d,  vni_10d)
    br_tile   = _tile("Breadth % &gt; MA50",
                      f"{br_now:.1f}%"  if br_now   is not None else "—",
                      br_1d,   br_5d,   br_10d)
    nhnl_tile = _tile("NHNL Absolute",
                      f"{nhnl_abs_now:+,.0f}" if nhnl_abs_now is not None else "—",
                      nhnl_1d, nhnl_5d, nhnl_10d)

    html = f"""<div style="background:linear-gradient(135deg,#f9f9f9 0%,#fff 100%);border:1px solid #e8e8e8;border-left:4px solid {phase_color};border-radius:12px;padding:20px 24px;">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap;">
    <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.6px;color:#97999B;">Phase Detected</span>
    <span style="background:{phase_color};color:#fff;font-size:11px;font-weight:700;padding:3px 12px;border-radius:20px;letter-spacing:0.4px;">{phase_label.upper()}</span>
  </div>
  <p style="margin:0 0 14px;font-size:14px;line-height:1.75;color:#101820;">{summary}</p>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">
    <div style="background:#f0faf5;border:1px solid #b8e8d0;border-radius:8px;padding:12px 14px;">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:#00BF6F;margin-bottom:6px;">✅ Validation — Confirms Current View</div>
      <p style="margin:0;font-size:13px;line-height:1.6;color:#101820;">{validation}</p>
    </div>
    <div style="background:#fff5f5;border:1px solid #f5c0c0;border-radius:8px;padding:12px 14px;">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:#FF0037;margin-bottom:6px;">❌ Invalidation — Changes Our View</div>
      <p style="margin:0;font-size:13px;line-height:1.6;color:#101820;">{invalidation}</p>
    </div>
  </div>
  <div>
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:#97999B;margin-bottom:10px;">Recent Changes</div>
    <div style="display:flex;gap:12px;flex-wrap:wrap;">{vni_tile}{br_tile}{nhnl_tile}</div>
  </div>
</div>"""
    return html


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
        # Seasonality 2026 YTD
        "{{seasonality_2026_json}}":   render_seasonality_2026(regime),
        # Composite Man Masterplan
        "{{composite_man_narrative}}": render_composite_man(regime),
        # Metric cards
        "{{regime_metric_cards}}":   render_metric_cards(regime),
        # Charts
        "{{chart_json}}":            chart_json,
        "{{full_chart_json}}":       json.dumps(regime.get("full_history", hist)),
        "{{nhnl_chart_json}}":       json.dumps(snapshot.get("nhnl_chart", {})),
        "{{breadth_chart_json}}":    json.dumps(snapshot.get("breadth_chart", {})),
        "{{ma200_chart_json}}":      json.dumps(snapshot.get("ma200_chart", {})),
        "{{rs_chart_json}}":         json.dumps(snapshot.get("rs_chart", {})),
        "{{interbank_chart_json}}":  json.dumps(snapshot.get("interbank_chart", {})),
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
