#!/usr/bin/env python3
"""
VnIndex Market Regime System v2
Reads Google Doc text (passed as file path in argv[1] or stdin).
Outputs regime JSON to stdout.

Indicators:
  VNI RSI 21D  — trend
  Breadth % > MA50 — market breadth
  NHNL RSI, MFI RSI, A/D RSI — money flow internals

Divergence:
  Direction divergence — RSI21 vs 3+ internals over 5-day and 10-day windows
  Gap divergence — RSI21 minus average of all internals
"""

import sys
import json
import re


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_doc(text):
    rows = []
    for raw in text.split("\n"):
        line = raw.strip()
        # Strip markdown formatting
        line = re.sub(r"\*+", "", line)
        line = line.replace("\\>", ">").replace("\\-", "-")
        if not line:
            continue
        # Must start with a date-like token
        parts = line.split()
        if not parts:
            continue
        # Validate date token
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", parts[0]):
            continue
        if len(parts) < 7:
            continue
        try:
            breadth_raw = parts[4].replace("%", "")
            row = {
                "date":        parts[0],
                "vnindex":     float(parts[1]),
                "rsi21":       float(parts[2]),
                "rsi70":       float(parts[3]),
                "breadth_pct": float(breadth_raw),   # e.g. 40.9 means 40.9 %
                "nhnl_rsi":    float(parts[6]),
                "mfi_rsi":     float(parts[7]),
                "ad_rsi":      float(parts[8])  if len(parts) > 8  else None,
                "mfi_abs":     float(parts[9])  if len(parts) > 9  else None,
                "ad_abs":      float(parts[10]) if len(parts) > 10 else None,
                "nhnl_abs":    float(parts[11]) if len(parts) > 11 else None,
            }
            rows.append(row)
        except (ValueError, IndexError):
            continue
    return sorted(rows, key=lambda r: r["date"])


# ---------------------------------------------------------------------------
# Classifications
# ---------------------------------------------------------------------------

def classify_rsi21(rsi, prev_rsi=None):
    if prev_rsi is not None:
        diff = rsi - prev_rsi
        trend_dir = "rising" if diff > 0.3 else ("falling" if diff < -0.3 else "flat")
    else:
        trend_dir = "flat"

    if rsi > 60 and trend_dir == "rising":
        label, alloc = "Strong Uptrend", 100
    elif rsi > 60:
        label, alloc = "Strong Uptrend", 90
    elif rsi >= 55:
        label, alloc = "Uptrend", 80
    elif rsi >= 50:
        label, alloc = "Mild Sideways Up", 60
    elif rsi >= 45:
        label, alloc = "Mild Sideways Down", 40
    elif rsi >= 40:
        label, alloc = "Downtrend", 20
    else:
        label, alloc = "Strong Downtrend", 5

    return label, trend_dir, alloc


def classify_breadth(pct):
    if pct < 25:   return f"Oversold ({pct:.1f}%)"
    if pct < 40:   return f"Very Narrow ({pct:.1f}%)"
    if pct < 50:   return f"Below Average ({pct:.1f}%)"
    if pct < 60:   return f"Above Average ({pct:.1f}%)"
    if pct < 70:   return f"Strong ({pct:.1f}%)"
    return f"Very Strong ({pct:.1f}%)"


def classify_mf(val):
    if val is None: return "N/A"
    if val < 20:    return "Oversold"
    if val < 30:    return "Very Weak"
    if val < 40:    return "Weak"
    if val < 50:    return "Below Average"
    if val < 60:    return "Above Average"
    if val < 70:    return "Strong"
    return "Very Strong"


# ---------------------------------------------------------------------------
# Divergence
# ---------------------------------------------------------------------------

def _dir(series, n):
    if len(series) <= n:
        return "flat"
    diff = series[-1] - series[-1 - n]
    if diff > 0.5:   return "rising"
    if diff < -0.5:  return "falling"
    return "flat"


def calc_divergence(rows):
    if len(rows) < 11:
        return {
            "dir_5d": False, "dir_10d": False, "type": None,
            "gap": 0.0, "internal_avg": 0.0, "severity": "Insufficient Data",
            "rsi_dir_5d": "flat", "rsi_dir_10d": "flat", "detail": {},
        }

    rsi21_s   = [r["rsi21"]       for r in rows]
    breadth_s = [r["breadth_pct"] for r in rows]
    nhnl_s    = [r["nhnl_rsi"]    for r in rows]
    mfi_s     = [r["mfi_rsi"]     for r in rows]
    ad_s      = [r["ad_rsi"] for r in rows if r.get("ad_rsi") is not None]

    dir_results = {}
    detail = {}
    for n, key in [(5, "5d"), (10, "10d")]:
        rsi_dir = _dir(rsi21_s, n)
        internals = [_dir(s, n) for s in [breadth_s, nhnl_s, mfi_s] if len(s) > n]
        if len(ad_s) > n:
            internals.append(_dir(ad_s, n))
        rsi_chg = rsi21_s[-1] - rsi21_s[-1 - n]
        if rsi_chg == 0:
            opposite = 0
        else:
            opp_dir = "falling" if rsi_chg > 0 else "rising"
            opposite = sum(1 for d in internals if d == opp_dir)
        diverged = opposite >= 3
        dir_results[key] = {"rsi_dir": rsi_dir, "diverged": diverged, "opposite": opposite}

        def chg(s):
            return round(s[-1] - s[-1 - n], 1) if len(s) > n else None

        detail[key] = {
            "rsi21":         chg(rsi21_s),
            "breadth":       chg(breadth_s),
            "nhnl":          chg(nhnl_s),
            "mfi":           chg(mfi_s),
            "ad":            chg(ad_s) if len(ad_s) > n else None,
            "opposite_count": opposite,
            "total_internals": len(internals),
            "diverged":      diverged,
        }

    latest = rows[-1]
    ad_val = latest.get("ad_rsi") or 0.0
    internal_avg = (latest["breadth_pct"] + latest["nhnl_rsi"] + latest["mfi_rsi"] + ad_val) / 4
    gap = latest["rsi21"] - internal_avg

    div_type = None
    dir_5d  = dir_results["5d"]["diverged"]
    dir_10d = dir_results["10d"]["diverged"]
    if dir_5d or dir_10d:
        rsi_dir_ref = dir_results["10d"]["rsi_dir"] if dir_10d else dir_results["5d"]["rsi_dir"]
        div_type = "bearish" if rsi_dir_ref == "rising" else "bullish"

    strong_dir = dir_5d and dir_10d
    gap_abs    = abs(gap)

    if strong_dir and gap_abs > 20:                      severity = "Severe"
    elif strong_dir or (dir_10d and gap_abs >= 12):      severity = "Moderate"
    elif dir_10d or gap_abs >= 12:                       severity = "Mild"
    elif dir_5d:                                         severity = "Early Warning"
    else:                                                severity = "None"

    return {
        "dir_5d":        dir_5d,
        "dir_10d":       dir_10d,
        "type":          div_type,
        "gap":           round(gap, 1),
        "internal_avg":  round(internal_avg, 1),
        "severity":      severity,
        "rsi_dir_5d":    dir_results["5d"]["rsi_dir"],
        "rsi_dir_10d":   dir_results["10d"]["rsi_dir"],
        "detail":        detail,
    }


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def _bear_score(div, rsi, breadth):
    """Bearish risk score 0-100 for uptrend regimes. Higher = more risk.
    Returns (total_score, components_list)."""
    components = []

    # Gap: RSI21 vs internal average (level divergence)
    gap = abs(div["gap"])
    if   gap >= 30: gap_pts = 35
    elif gap >= 20: gap_pts = 25
    elif gap >= 10: gap_pts = 15
    else:           gap_pts = 0
    gap_note = (
        f"RSI21 is {div['gap']:+.1f}pts above internal avg — severe leadership gap" if gap >= 30 else
        f"RSI21 is {div['gap']:+.1f}pts above internal avg — wide gap, index running ahead of breadth" if gap >= 20 else
        f"RSI21 is {div['gap']:+.1f}pts above internal avg — moderate gap" if gap >= 10 else
        f"RSI21 is {div['gap']:+.1f}pts vs internal avg — internals broadly aligned"
    )
    components.append({"label": "Gap (RSI21 − Avg Internals)", "value": f"{div['gap']:+.1f}", "note": gap_note, "pts": gap_pts})

    # Direction divergence 10d
    d10_pts  = 25 if div["dir_10d"] else 0
    d10_note = ("3+ internals falling while RSI21 rising over 10 days — active distribution signal"
                if div["dir_10d"] else "Internals not moving against RSI21 over 10 days — no direction warning")
    components.append({"label": "Direction Divergence 10d", "value": "Yes" if div["dir_10d"] else "No", "note": d10_note, "pts": d10_pts})

    # Direction divergence 5d
    d5_pts  = 15 if div["dir_5d"] else 0
    d5_note = ("3+ internals falling while RSI21 rising over 5 days — early rotation signal"
               if div["dir_5d"] else "No short-term direction divergence over 5 days")
    components.append({"label": "Direction Divergence 5d",  "value": "Yes" if div["dir_5d"]  else "No", "note": d5_note,  "pts": d5_pts})

    # Breadth level
    if   breadth < 25: brd_pts = 20; brd_note = f"Extremely narrow — only {breadth:.0f}% of stocks above MA50, distribution risk very high"
    elif breadth < 40: brd_pts = 10; brd_note = f"Very narrow — only {breadth:.0f}% of stocks above MA50, headline index masking weak internals"
    elif breadth < 60: brd_pts =  0; brd_note = f"Average breadth — {breadth:.0f}% of stocks above MA50, no additional concern"
    elif breadth < 75: brd_pts = -5; brd_note = f"Strong breadth — {breadth:.0f}% of stocks above MA50, internals supportive"
    else:              brd_pts = -5; brd_note = f"Very strong breadth — {breadth:.0f}% of stocks above MA50, broad participation"
    components.append({"label": "Breadth (% above MA50)", "value": f"{breadth:.1f}%", "note": brd_note, "pts": brd_pts})

    # RSI extension
    if rsi > 70: rsi_pts = 10; rsi_note = f"RSI21={rsi:.1f} — overbought, elevated mean-reversion risk"
    else:        rsi_pts =  0; rsi_note = f"RSI21={rsi:.1f} — not overbought, no extension penalty"
    components.append({"label": "RSI21 Extension", "value": f"{rsi:.1f}", "note": rsi_note, "pts": rsi_pts})

    total = max(0, min(100, sum(c["pts"] for c in components)))
    if   total < 20: tier = "Clean"
    elif total < 40: tier = "Caution"
    elif total < 60: tier = "Warning"
    else:            tier = "High Risk"

    return total, tier, components


def build_scenarios(rows, div, trend_label, breadth_label, mf_label, base_alloc):
    latest  = rows[-1]
    rsi     = latest["rsi21"]
    breadth = latest["breadth_pct"]

    is_up   = "Uptrend" in trend_label or "Sideways Up" in trend_label
    is_down = "Downtrend" in trend_label

    if is_up:
        bs, bs_tier, bs_components = _bear_score(div, rsi, breadth)

        if bs < 20:   # ── Clean uptrend ──────────────────────────────────────
            sc = [
                {"name": "Uptrend continues",
                 "probability": 65,
                 "allocation": min(100, base_alloc + 10),
                 "logic": f"RSI21={rsi:.1f} ({trend_label}). Breadth {breadth:.1f}%. MF: {mf_label}. Risk score: {bs}.",
                 "confirmation": f"RSI21 holds >{rsi-3:.0f}, breadth expands above {breadth+5:.0f}%.",
                 "invalidation": f"RSI21 drops below 55, breadth falls below {max(25,breadth-10):.0f}%."},
                {"name": "Pullback / Consolidation",
                 "probability": 25,
                 "allocation": max(40, base_alloc - 20),
                 "logic": "Healthy digestion of gains; internals intact.",
                 "confirmation": "RSI21 dips 57-60, breadth holds 50%+.",
                 "invalidation": "RSI21 rebounds quickly, breadth stable."},
                {"name": "Trend breaks down",
                 "probability": 10,
                 "allocation": 20,
                 "logic": "Tail risk; requires simultaneous failure of multiple internals.",
                 "confirmation": "RSI21 < 50, breadth < 30%, NHNL collapses.",
                 "invalidation": "Price holds support, RSI21 bounces above 55."},
            ]
        elif bs < 40:  # ── Caution ────────────────────────────────────────────
            sc = [
                {"name": "Uptrend continues",
                 "probability": 50,
                 "allocation": base_alloc,
                 "logic": f"RSI21={rsi:.1f} trend intact; early warning signs present. Risk score: {bs}.",
                 "confirmation": f"RSI21 holds >{rsi-3:.0f}, breadth recovers above {breadth+8:.0f}%.",
                 "invalidation": f"RSI21 breaks 55, breadth slides below {max(25,breadth-8):.0f}%."},
                {"name": "Pullback / Consolidation",
                 "probability": 35,
                 "allocation": max(30, base_alloc - 30),
                 "logic": f"Gap {div['gap']:+.1f}. Breadth {breadth:.1f}% signals narrow leadership.",
                 "confirmation": "RSI21 retreats to 57-60, breadth stabilises.",
                 "invalidation": "RSI21 rebounds, internals recover."},
                {"name": "Trend breaks down",
                 "probability": 15,
                 "allocation": 20,
                 "logic": f"Breadth {breadth:.1f}% and gap {div['gap']:+.1f} elevate tail risk.",
                 "confirmation": "RSI21 < 50, breadth < 30%, NHNL collapses.",
                 "invalidation": "Internals recover, gap narrows below 10."},
            ]
        elif bs < 60:  # ── Warning ────────────────────────────────────────────
            sc = [
                {"name": "Distribution risk",
                 "probability": 55,
                 "allocation": 25,
                 "logic": f"Risk score {bs}: gap {div['gap']:+.1f}, breadth {breadth:.1f}%, {div['severity']} divergence.",
                 "confirmation": "RSI21 breaks 55, breadth falls below 30%.",
                 "invalidation": "Breadth recovers above 45%, gap narrows, NHNL turns up."},
                {"name": "Divergence resolves bullishly",
                 "probability": 30,
                 "allocation": base_alloc,
                 "logic": "Internals catch up to RSI21; leadership broadens.",
                 "confirmation": "Breadth expands >50%, NHNL and A/D turn up.",
                 "invalidation": f"Gap widens beyond {abs(div['gap'])+8:.0f}, breadth makes new lows."},
                {"name": "Sideways chop",
                 "probability": 15,
                 "allocation": 45,
                 "logic": "Market stalls while internals rebuild — no clean resolution.",
                 "confirmation": "RSI21 oscillates 55-65, breadth flat.",
                 "invalidation": "Decisive directional break."},
            ]
        else:          # ── High risk ───────────────────────────────────────────
            sc = [
                {"name": "Distribution accelerates",
                 "probability": 70,
                 "allocation": 15,
                 "logic": f"Risk score {bs}: gap {div['gap']:+.1f}, breadth {breadth:.1f}%, {div['severity']} divergence.",
                 "confirmation": "RSI21 breaks 55, breadth crashes below 25%.",
                 "invalidation": "Internals sharply recover, gap closes to <10."},
                {"name": "Divergence resolves bullishly",
                 "probability": 20,
                 "allocation": base_alloc,
                 "logic": "Internals aggressively catch up — requires major catalyst.",
                 "confirmation": "NHNL spikes, breadth jumps >50% within 3 sessions.",
                 "invalidation": f"Gap persists, breadth stays below {breadth+5:.0f}%."},
                {"name": "Sideways chop",
                 "probability": 10,
                 "allocation": 35,
                 "logic": "Volatility compresses while internals remain broken.",
                 "confirmation": "RSI21 range-bound 58-68, no breadth recovery.",
                 "invalidation": "Directional break resolves."},
            ]

    elif is_down:
        if   rsi < 30: bounce_prob = 55
        elif rsi < 40: bounce_prob = 35
        else:          bounce_prob = 20
        sc = [
            {"name": "Downtrend continues",
             "probability": 100 - bounce_prob - 10,
             "allocation": 10,
             "logic": f"RSI21={rsi:.1f} confirms downtrend. Breadth={breadth:.1f}%.",
             "confirmation": f"RSI21 falls below {rsi-3:.0f}, breadth stays below 35%.",
             "invalidation": "RSI21 reclaims 50, breadth rebounds above 40%."},
            {"name": "Oversold bounce",
             "probability": bounce_prob,
             "allocation": 40,
             "logic": "Mean-reversion rally likely; not a trend change.",
             "confirmation": "RSI21 turns up from <45, NHNL stops falling.",
             "invalidation": "RSI21 fails to recover, breadth makes new lows."},
            {"name": "Full trend reversal",
             "probability": 10,
             "allocation": 65,
             "logic": "Bullish divergence could catalyse full reversal.",
             "confirmation": "RSI21 > 50 with breadth expanding above 40%.",
             "invalidation": "Rally fades, RSI21 rolls over below 48."},
        ]

    else:  # Neutral / Sideways
        sc = [
            {"name": "Resolves upward",
             "probability": 45,
             "allocation": 70,
             "logic": f"RSI21={rsi:.1f} in neutral zone. Slight upward historical bias.",
             "confirmation": "RSI21 > 55, breadth expands above 50%.",
             "invalidation": "RSI21 drops below 45, breadth contracts."},
            {"name": "Sideways continues",
             "probability": 35,
             "allocation": 50,
             "logic": "No catalyst for directional break.",
             "confirmation": "RSI21 oscillates 45-55, breadth flat.",
             "invalidation": "Decisive move in RSI21 and breadth."},
            {"name": "Resolves downward",
             "probability": 20,
             "allocation": 25,
             "logic": "Weak internals could drag price lower.",
             "confirmation": "RSI21 < 45, breadth falls below 35%.",
             "invalidation": "RSI21 holds 50+, breadth stable."},
        ]

    total = sum(s["probability"] for s in sc)
    for s in sc:
        s["probability"] = round(s["probability"] / total * 100)

    bear_detail = None
    if is_up:
        bear_detail = {"score": bs, "tier": bs_tier, "components": bs_components}

    return sc, bear_detail


# ---------------------------------------------------------------------------
# Phase labeling
# ---------------------------------------------------------------------------

def build_phases(rows):
    if not rows:
        return []

    phases  = []
    ph_start = 0

    def flush(end_idx):
        ph_rows = rows[ph_start : end_idx + 1]
        if len(ph_rows) < 3:
            return
        base_vni = rows[ph_start - 1]["vnindex"] if ph_start > 0 else ph_rows[0]["vnindex"]
        ret = (ph_rows[-1]["vnindex"] / base_vni - 1) * 100
        t_lbl, _, _ = classify_rsi21(ph_rows[-1]["rsi21"])
        b_lbl       = classify_breadth(ph_rows[-1]["breadth_pct"])
        pd = calc_divergence(ph_rows) if len(ph_rows) >= 5 else None
        div_str = (
            f"Dir 5d: {'Y' if pd['dir_5d'] else 'N'} | 10d: {'Y' if pd['dir_10d'] else 'N'} | Gap {pd['gap']:+.1f}"
            if pd else "Insufficient data"
        )
        phases.append({
            "start":       ph_rows[0]["date"],
            "end":         ph_rows[-1]["date"],
            "regime":      f"{t_lbl} – {b_lbl}",
            "vni_end":     round(ph_rows[-1]["vnindex"], 1),
            "return_pct":  round(ret, 2),
            "divergence":  div_str,
        })

    for i in range(1, len(rows)):
        curr, _ , _ = classify_rsi21(rows[i]["rsi21"],   rows[i-1]["rsi21"])
        prev, _ , _ = classify_rsi21(rows[i-1]["rsi21"], rows[i-2]["rsi21"] if i > 1 else None)
        if curr != prev:
            flush(i - 1)
            ph_start = i

    flush(len(rows) - 1)
    return phases


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def analyze(rows):
    if len(rows) < 2:
        return {"error": "Insufficient data"}

    rows30 = rows[-30:] if len(rows) >= 30 else rows
    latest = rows30[-1]
    prev   = rows30[-2]

    trend_label, trend_dir, alloc_score = classify_rsi21(latest["rsi21"], prev["rsi21"])
    breadth_label = classify_breadth(latest["breadth_pct"])
    nhnl_label    = classify_mf(latest["nhnl_rsi"])
    mfi_label     = classify_mf(latest["mfi_rsi"])
    ad_label      = classify_mf(latest.get("ad_rsi"))
    mf_summary    = f"NHNL {nhnl_label} · MFI {mfi_label} · A/D {ad_label}"

    div = calc_divergence(rows30)

    # Build divergence flag string
    parts = []
    if div["dir_5d"] and div["dir_10d"]: parts.append("Dir: 5d+10d")
    elif div["dir_5d"]:                  parts.append("Dir: 5d")
    elif div["dir_10d"]:                 parts.append("Dir: 10d")
    if abs(div["gap"]) >= 12:            parts.append(f"Gap {div['gap']:+.1f}")

    if div["type"] and parts:
        div_flag = f"DIVERGENT ({div['type'].capitalize()}, {', '.join(parts)})"
    elif div["type"]:
        div_flag = f"DIVERGENT ({div['type'].capitalize()})"
    else:
        div_flag = "ALIGNED"

    regime_name = f"{trend_label} – {breadth_label} – {mf_summary}"

    scenarios, bear_detail = build_scenarios(rows30, div, trend_label, breadth_label, mf_summary, alloc_score)
    phases    = build_phases(rows30)

    # Recommended allocation = probability-weighted average of scenario allocations
    alloc = round(sum(s["probability"] * s["allocation"] for s in scenarios) / 100 / 10) * 10

    # 30-day history for divergence detail
    history = {
        "dates":   [r["date"]        for r in rows30],
        "vnindex": [r["vnindex"]     for r in rows30],
        "rsi21":   [r["rsi21"]       for r in rows30],
        "breadth": [r["breadth_pct"] for r in rows30],
        "nhnl":    [r["nhnl_rsi"]    for r in rows30],
        "mfi":     [r["mfi_rsi"]     for r in rows30],
        "ad":      [r.get("ad_rsi")  for r in rows30],
    }

    # Full history for main chart (all available rows)
    full_history = {
        "dates":   [r["date"]           for r in rows],
        "vnindex": [r["vnindex"]        for r in rows],
        "rsi21":   [r["rsi21"]          for r in rows],
        "breadth": [r["breadth_pct"]    for r in rows],
        "nhnl":    [r["nhnl_rsi"]       for r in rows],
        "mfi":     [r["mfi_rsi"]        for r in rows],
        "ad":      [r.get("ad_rsi")     for r in rows],
    }

    nhnl_history = {
        "dates":   [r["date"]            for r in rows],
        "nhnl":    [r.get("nhnl_abs")    for r in rows],
        "vnindex": [r["vnindex"]         for r in rows],
    }

    breadth_history = {
        "dates":       [r["date"]          for r in rows],
        "breadth_pct": [r["breadth_pct"]   for r in rows],
        "vnindex":     [r["vnindex"]       for r in rows],
    }

    mfi_history = {
        "dates":   [r["date"]           for r in rows],
        "mfi_abs": [r.get("mfi_abs")    for r in rows],
        "vnindex": [r["vnindex"]        for r in rows],
    }

    ad_history = {
        "dates":   [r["date"]          for r in rows],
        "ad_abs":  [r.get("ad_abs")    for r in rows],
        "vnindex": [r["vnindex"]       for r in rows],
    }

    gap_history = {
        "dates":   [r["date"]                             for r in rows],
        "gap":     [round(r["rsi21"] - r["nhnl_rsi"], 1) for r in rows],
        "vnindex": [r["vnindex"]                          for r in rows],
    }

    return {
        "date":            latest["date"],
        "vnindex":         latest["vnindex"],
        "history":         history,
        "full_history":    full_history,
        "nhnl_history":    nhnl_history,
        "breadth_history": breadth_history,
        "mfi_history":     mfi_history,
        "ad_history":      ad_history,
        "gap_history":     gap_history,
        "indicators": {
            "rsi21":       latest["rsi21"],
            "rsi70":       latest.get("rsi70"),
            "breadth_pct": latest["breadth_pct"],
            "nhnl_rsi":    latest["nhnl_rsi"],
            "mfi_rsi":     latest["mfi_rsi"],
            "ad_rsi":      latest.get("ad_rsi"),
        },
        "classifications": {
            "trend":           trend_label,
            "trend_direction": trend_dir,
            "breadth":         breadth_label,
            "nhnl":            nhnl_label,
            "mfi":             mfi_label,
            "ad":              ad_label,
        },
        "regime_name":    regime_name,
        "divergence_flag": div_flag,
        "divergence":     div,
        "allocation":     alloc,
        "scenarios":      scenarios,
        "bear_detail":    bear_detail,
        "phases":         phases,
    }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    rows   = parse_doc(text)
    result = analyze(rows)
    print(json.dumps(result, ensure_ascii=False, indent=2))
