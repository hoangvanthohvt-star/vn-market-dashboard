"""Interest Rate Regime — VNIBOR 6M level x direction, shown against VNMIDCAP.

Rules (finalised Nov 2026):
  Direction = VNIBOR 6M today minus VNIBOR 6M 120 sessions earlier (rate calendar).
      > +0.5pp -> rising ; < -0.5pp -> falling ; inside +/-0.5pp -> keep prior direction.
  Regime:
      Good     : VNIBOR 6M < 6%  and falling
      Caution  : VNIBOR 6M < 6%  and rising, or 6% <= VNIBOR 6M <= 7%
      Risk     : VNIBOR 6M > 7%  and rising
      Easing   : VNIBOR 6M > 7%  and falling

Inputs:
  ib_records : full VNIBOR 6M history [{"date": "YYYY-MM-DD", "value": float}, ...]
               (macro_data_consolidated, Ticker 'VNIVND6MD=' -- Step 1 of the daily run)
  doc_rows   : parsed regime-doc rows (carry daily "vnmidcap"); extend the seed file
  data/vnmid_history.json : 10y VNMIDCAP seed (DC MSSQL MarketIndex, COMGROUPCODE='VNMID')

Stats are recomputed every run on full history, with the regime lagged one session
(regime known at close t is applied to the return of t+1 and to the 60d forward window from t+1).
"""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "vnmid_history.json"

LEVEL_LOW = 6.0
LEVEL_HIGH = 7.0
LOOKBACK = 120
GAP = 0.5
FWD = 60
CHART_START = "2016-06-01"

REGIMES = {
    "G": {"name": "Good",    "cls": "pos",  "rule": "VNIBOR 6M < 6% and falling"},
    "C": {"name": "Caution", "cls": "warn", "rule": "< 6% but rising, or 6–7%"},
    "R": {"name": "Risk",    "cls": "neg",  "rule": "VNIBOR 6M > 7% and rising"},
    "E": {"name": "Easing",  "cls": "neu",  "rule": "VNIBOR 6M > 7% but falling"},
}


def _classify(level, direction):
    if direction is None:
        return None
    if level > LEVEL_HIGH:
        return "R" if direction == "up" else "E"
    if level < LEVEL_LOW and direction == "down":
        return "G"
    return "C"


def _load_vnmid(doc_rows):
    series = {}
    if SEED.exists():
        for d, v in json.loads(SEED.read_text()).get("data", []):
            if v and v > 0:
                series[d] = float(v)
    for r in doc_rows or []:
        v = r.get("vnmidcap")
        if v and v > 0:
            series[r["date"]] = float(v)
    return sorted(series.items())


def compute_rate_regime(ib_records, doc_rows=None):
    ib = sorted(
        (str(x["date"])[:10], float(x["value"]))
        for x in (ib_records or [])
        if x.get("value") is not None and 0 < float(x["value"]) < 30
    )
    # de-duplicate dates (keep last)
    ib = list(dict(ib).items())
    if len(ib) <= LOOKBACK:
        return {"error": "Insufficient VNIBOR 6M history"}

    ib_dates = [d for d, _ in ib]
    ib_vals = [v for _, v in ib]

    # direction state machine + regime on the rate calendar
    direction, dirs, chgs, regs = None, [], [], []
    for i, v in enumerate(ib_vals):
        ch = v - ib_vals[i - LOOKBACK] if i >= LOOKBACK else None
        if ch is not None:
            if ch > GAP:
                direction = "up"
            elif ch < -GAP:
                direction = "down"
        dirs.append(direction)
        chgs.append(ch)
        regs.append(_classify(v, direction))

    mid = _load_vnmid(doc_rows)
    if len(mid) < FWD + 10:
        return {"error": "Insufficient VNMIDCAP history"}
    m_dates = [d for d, _ in mid]
    m_vals = [v for _, v in mid]

    # forward-fill rate and regime onto VNMIDCAP trading days
    m_rate, m_reg = [], []
    j, last_rate, last_reg = 0, None, None
    for d in m_dates:
        while j < len(ib_dates) and ib_dates[j] <= d:
            last_rate, last_reg = ib_vals[j], regs[j]
            j += 1
        m_rate.append(last_rate)
        m_reg.append(last_reg)

    # ── Stats (regime lagged one session) ──
    acc = {k: {"n": 0, "lr": 0.0, "f_n": 0, "f_win": 0, "f_sum": 0.0} for k in REGIMES}
    total = 0
    for i in range(1, len(m_dates)):
        if m_dates[i] < CHART_START:
            continue
        reg = m_reg[i - 1]
        if reg is None:
            continue
        a = acc[reg]
        total += 1
        a["n"] += 1
        a["lr"] += math.log(m_vals[i] / m_vals[i - 1])
        if i + FWD < len(m_vals):
            f = m_vals[i + FWD] / m_vals[i] - 1
            a["f_n"] += 1
            a["f_sum"] += f
            a["f_win"] += f > 0
    stats = {}
    for k, a in acc.items():
        stats[k] = {
            "days": a["n"],
            "pct_time": round(a["n"] / total * 100, 1) if total else None,
            "ann_ret": round((math.exp(a["lr"] / a["n"] * 252) - 1) * 100, 1) if a["n"] else None,
            "win60": round(a["f_win"] / a["f_n"] * 100, 1) if a["f_n"] else None,
            "avg60": round(a["f_sum"] / a["f_n"] * 100, 2) if a["f_n"] else None,
        }

    # ── Regime switch log (rate calendar) ──
    switches = []
    for i in range(1, len(regs)):
        if regs[i] is not None and regs[i] != regs[i - 1] and ib_dates[i] >= CHART_START:
            switches.append({
                "date": ib_dates[i], "regime": regs[i], "name": REGIMES[regs[i]]["name"],
                "vnibor": ib_vals[i], "chg120": round(chgs[i], 2) if chgs[i] is not None else None,
            })
    since = next((s["date"] for s in reversed(switches) if s["regime"] == regs[-1]), None)

    cur = regs[-1]
    ref = ib_vals[-1 - LOOKBACK]
    current = {
        "date": ib_dates[-1],
        "vnibor": ib_vals[-1],
        "chg120": round(chgs[-1], 2),
        "ref_date": ib_dates[-1 - LOOKBACK],
        "ref_value": ref,
        "direction": dirs[-1],
        "regime": cur,
        "name": REGIMES[cur]["name"] if cur else "—",
        "cls": REGIMES[cur]["cls"] if cur else "neu",
        "since": since,
        "vnmid": m_vals[-1],
        "vnmid_date": m_dates[-1],
        "up_trigger": round(ref + GAP, 2),
        "down_trigger": round(ref - GAP, 2),
    }

    start = next(i for i, d in enumerate(m_dates) if d >= CHART_START)
    chart = {
        "dates": m_dates[start:],
        "vnmid": [round(v, 2) for v in m_vals[start:]],
        "vnibor": m_rate[start:],
        "regime": "".join(r or "C" for r in m_reg[start:]),
    }

    return {
        "current": current,
        "stats": stats,
        "regimes": REGIMES,
        "switches": switches[-10:],
        "chart": chart,
        "params": {"low": LEVEL_LOW, "high": LEVEL_HIGH, "lookback": LOOKBACK, "gap": GAP, "fwd": FWD},
    }


if __name__ == "__main__":
    import sys
    recs = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else []
    out = compute_rate_regime(recs)
    out.pop("chart", None)
    print(json.dumps(out, indent=2))
