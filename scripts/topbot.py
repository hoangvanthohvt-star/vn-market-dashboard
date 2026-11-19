"""Breadth combo top/bottom signals on VNMIDCAP.

Bottom ("washout") score: count of 6 breadth extremes. Score >= 3 = bottom zone.
Top ("divergence"): VNMIDCAP within 3% of its 60-day high while breadth breaks
(NHNL < 0 OR % above MA50 dropped >= 15 pts from its 20-day max).

Backtest 11/2022-11/2026 (VNMIDCAP forward returns):
  bottom score>=3   -> 20d avg +8.7%, 90% positive, 40d max DD -2.7%
  top divergence    -> 20d avg -3.5%, 75% negative, 40d max DD -9.3%
  baseline          -> 20d avg +1.1%, 55% positive
"""

BOTTOM_RULES = [
    # key, label, field, op, threshold
    ("pct50",    "% > MA50",  "breadth_pct", "<=", 15),
    ("nhnl",     "NHNL",      "nhnl_abs",    "<=", -400),
    ("ad",       "A/D",       "ad_abs",      "<=", -450),
    ("nhnl_rsi", "NHNL RSI",  "nhnl_rsi",    "<=", 25),
    ("ad_rsi",   "A/D RSI",   "ad_rsi",      "<=", 36),
    ("mfi_rsi",  "MFI RSI",   "mfi_rsi",     "<=", 36),
]
BOTTOM_MIN_SCORE = 3
NEAR_HIGH_PCT = 0.03       # within 3% of 60d high
HIGH_LOOKBACK = 60
PCT50_DROP = 15            # pts from 20d max
PCT50_DROP_LOOKBACK = 20
WASHOUT_LOOKBACK = 15      # days a washout stays "armed" for confirmation
EPISODE_GAP = 10           # days between separate signal episodes


def _hit(v, op, th):
    if v is None:
        return False
    return v <= th if op == "<=" else v >= th


def _ffill(vals):
    out, last = [], None
    for v in vals:
        if v is not None:
            last = v
        out.append(last)
    return out


def _episodes(flags):
    eps, last = [], -10**9
    for i, f in enumerate(flags):
        if f:
            if i - last > EPISODE_GAP:
                eps.append(i)
            last = i
    return eps


def compute_topbot(rows):
    rows = [r for r in rows if r.get("vnmidcap")]
    if len(rows) < HIGH_LOOKBACK:
        return {"error": "Insufficient VNMIDCAP data"}

    dates = [r["date"] for r in rows]
    mid = _ffill([r.get("vnmidcap") for r in rows])
    pct50 = [r.get("breadth_pct") for r in rows]

    bscore, bflags, near, hi60, top_flag, top_why, confirm = [], [], [], [], [], [], []
    for i, r in enumerate(rows):
        hits = {k: _hit(r.get(f), op, th) for k, _, f, op, th in BOTTOM_RULES}
        bflags.append(hits)
        bscore.append(sum(hits.values()))

        h = max(mid[max(0, i - HIGH_LOOKBACK + 1): i + 1])
        hi60.append(h)
        nh = mid[i] >= h * (1 - NEAR_HIGH_PCT)
        near.append(nh)

        win = [x for x in pct50[max(0, i - PCT50_DROP_LOOKBACK + 1): i + 1] if x is not None]
        drop = (max(win) - pct50[i]) if win and pct50[i] is not None else 0
        why = []
        if nh and (r.get("nhnl_abs") or 0) < 0:
            why.append("NHNL < 0")
        if nh and drop >= PCT50_DROP:
            why.append(f"%>MA50 −{drop:.0f}pts in 20d")
        top_flag.append(bool(why))
        top_why.append(why)

        armed = any(s >= BOTTOM_MIN_SCORE for s in bscore[max(0, i - WASHOUT_LOOKBACK + 1): i + 1])
        prev_ad = rows[i - 1].get("ad_rsi") if i else None
        cross = (r.get("ad_rsi") or 0) > 50 and prev_ad is not None and prev_ad <= 50
        confirm.append(armed and cross)

    bot_flag = [s >= BOTTOM_MIN_SCORE for s in bscore]
    bot_eps, top_eps, conf_eps = _episodes(bot_flag), _episodes(top_flag), _episodes(confirm)

    i = len(rows) - 1
    r = rows[i]
    components = []
    for k, label, f, op, th in BOTTOM_RULES:
        components.append({"key": k, "label": label, "value": r.get(f), "threshold": th,
                           "op": op, "hit": bflags[i][k]})

    # days since last signal episode (based on flags, not episode start)
    def _since(flags):
        for j in range(i, -1, -1):
            if flags[j]:
                return i - j
        return None

    if top_flag[i]:
        state, state_cls = "TOP ZONE — Breadth Divergence", "neg"
    elif bot_flag[i]:
        state, state_cls = "BOTTOM ZONE — Washout", "pos"
    elif confirm[i]:
        state, state_cls = "BOTTOM CONFIRMED — A/D RSI > 50", "pos"
    elif bscore[i] >= 2:
        state, state_cls = "Approaching Bottom Zone", "warn"
    else:
        state, state_cls = "Neutral", "neu"

    return {
        "date": dates[i],
        "vnmidcap": mid[i],
        "hi60": hi60[i],
        "dist_hi60_pct": round((mid[i] / hi60[i] - 1) * 100, 1),
        "near_high": near[i],
        "bottom_score": bscore[i],
        "bottom_min": BOTTOM_MIN_SCORE,
        "components": components,
        "top_signal": top_flag[i],
        "top_reasons": top_why[i],
        "confirm_signal": confirm[i],
        "state": state,
        "state_cls": state_cls,
        "days_since_bottom": _since(bot_flag),
        "days_since_top": _since(top_flag),
        "chart": {
            "dates": dates,
            "vnmidcap": mid,
            "bottom_score": bscore,
            "bottom_eps": [dates[j] for j in bot_eps],
            "top_eps": [dates[j] for j in top_eps],
            "confirm_eps": [dates[j] for j in conf_eps],
        },
    }
