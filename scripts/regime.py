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
                "nhnl_rsi":    float(parts[5]),
                "mfi_rsi":     float(parts[6]),
                "ad_rsi":      float(parts[7]) if len(parts) > 7 else None,
                "mfi_abs":     float(parts[8])  if len(parts) > 8  else None,
                "ad_abs":      float(parts[9])  if len(parts) > 9  else None,
                "nhnl_abs":    float(parts[10]) if len(parts) > 10 else None,
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

def _base_rate(div):
    dir_5d  = div["dir_5d"]
    dir_10d = div["dir_10d"]
    gap_abs = abs(div["gap"])
    strong  = dir_5d and dir_10d
    if strong and gap_abs > 20:               return 30
    if strong or (dir_10d and gap_abs >= 12): return 40
    if dir_10d or gap_abs >= 12:              return 50
    if dir_5d:                                return 55
    return 65


def build_scenarios(rows, div, trend_label, breadth_label, mf_label, alloc):
    latest   = rows[-1]
    rsi      = latest["rsi21"]
    breadth  = latest["breadth_pct"]
    base     = _base_rate(div)

    adj = 0
    if rsi > 70 or rsi < 30:       adj -= 10
    if breadth > 75 or breadth < 25: adj -= 10
    cont = max(25, min(70, base + adj))

    is_up   = "Uptrend" in trend_label or "Sideways Up" in trend_label
    is_down = "Downtrend" in trend_label

    if is_up:
        if cont >= 55:
            sc = [
                {"name": "Uptrend continues",
                 "probability": cont,
                 "allocation": min(100, alloc + 10),
                 "logic": f"RSI21={rsi:.1f} ({trend_label}). Breadth {breadth:.1f}%. MF: {mf_label}.",
                 "confirmation": f"RSI21 holds >{rsi-3:.0f}, breadth improves above {breadth+3:.0f}%.",
                 "invalidation": f"RSI21 breaks below 55, breadth collapses below {breadth-8:.0f}%."},
                {"name": "Pullback / Consolidation",
                 "probability": 100 - cont - 10,
                 "allocation": max(30, alloc - 20),
                 "logic": "Short-term extended; divergence may trigger a pause.",
                 "confirmation": "RSI21 retreats to 57-60, breadth dips but holds 35%+.",
                 "invalidation": "RSI21 rebounds, breadth recovers above current level."},
                {"name": "Trend breaks down",
                 "probability": 10,
                 "allocation": 20,
                 "logic": f"Divergence severity: {div['severity']}. Multiple indicator failure needed.",
                 "confirmation": "RSI21 < 50, breadth < 30%, NHNL collapses.",
                 "invalidation": "Price holds support, RSI21 bounces above 55."},
            ]
        else:
            bear_prob = 100 - cont + 10   # ~60 when cont=50; rises as cont falls
            bull_prob = max(10, cont - 15) # ~35 when cont=50; never below 10
            side_prob = 5
            sc = [
                {"name": "Distribution accelerates",
                 "probability": bear_prob,
                 "allocation": 20,
                 "logic": f"Divergence {div['severity']} ({div['type']}). Gap={div['gap']:+.1f}. High reversal risk.",
                 "confirmation": f"RSI21 breaks 55, breadth falls below 35%.",
                 "invalidation": "Breadth and NHNL recover, RSI21 holds 60+."},
                {"name": "Divergence fades, upside resumes",
                 "probability": bull_prob,
                 "allocation": alloc,
                 "logic": "Internals catch up to RSI21; divergence resolves bullishly.",
                 "confirmation": "NHNL and A/D turn up alongside RSI21.",
                 "invalidation": f"Gap divergence widens beyond {abs(div['gap'])+5:.0f}."},
                {"name": "Sideways chop",
                 "probability": side_prob,
                 "allocation": 40,
                 "logic": "Market digests gains without resolution.",
                 "confirmation": "RSI21 oscillates 58-65, breadth flat.",
                 "invalidation": "Decisive directional break."},
            ]
    elif is_down:
        sc = [
            {"name": "Downtrend continues",
             "probability": cont,
             "allocation": 10,
             "logic": f"RSI21={rsi:.1f} confirms downtrend. Breadth={breadth:.1f}%.",
             "confirmation": f"RSI21 falls below {rsi-3:.0f}, breadth stays below 35%.",
             "invalidation": "RSI21 reclaims 50, breadth rebounds above 40%."},
            {"name": "Oversold bounce",
             "probability": 100 - cont - 10,
             "allocation": 40,
             "logic": "Internals may form a bottom while trend stays weak.",
             "confirmation": "RSI21 turns up from <45, NHNL stops falling.",
             "invalidation": "RSI21 fails to recover, breadth makes new lows."},
            {"name": "Full trend reversal",
             "probability": 10,
             "allocation": 65,
             "logic": "Bullish divergence (if present) could catalyse reversal.",
             "confirmation": "RSI21 > 50 with breadth expanding above 40%.",
             "invalidation": "Rally fades, RSI21 rolls over below 48."},
        ]
    else:
        sc = [
            {"name": "Resolves upward",
             "probability": 45,
             "allocation": 70,
             "logic": f"RSI21={rsi:.1f} in neutral zone. Break depends on internals.",
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
    return sc


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

    # Adjust allocation for divergence
    alloc = alloc_score
    sev_map = {"Severe": -40, "Moderate": -25, "Mild": -15, "Early Warning": -10}
    alloc += sev_map.get(div["severity"], 0)
    alloc  = round(max(10, min(100, alloc)) / 10) * 10

    scenarios = build_scenarios(rows30, div, trend_label, breadth_label, mf_summary, alloc)
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
