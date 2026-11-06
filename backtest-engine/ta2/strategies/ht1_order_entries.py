"""HT1 Humbled Trader (Shay) - order-entry setups (strategy list #8, #9, #10, #11). TIER: candidate.

Entry = a resting order filled DURING the signal bar (engine mode 3, column px):
  fgd   #10a first green day   long : >= 2 red closes, today opens below the prior close -> buy-stop at the prior close
  day2  #10b day-2 reclaim     long : day 1 up >= 3% on >= 1.5x volume, closes in top 20% of range above its 60-day high;
                                      day 2 opens below the day-1 close -> buy-stop at the day-1 close; target = day-1 high
  frd   #11  first red day     short: >= 5 green closes, today opens above the prior close -> sell-stop at the prior close;
                                      cover target = prior-day low
  para  #9   parabolic dip buy long : >= 5 of the last 6 closes up (or +15% in 10 days) -> limit buy at the prior-day low;
                                      target = the run high
  bag   #8   bagholder short   short: below the 200 SMA, a 1-3 day pop >= 10% with an upper wick -> sell-stop at the prior
                                      close (large-cap analog: TSX60 has no small caps)
Stops: anchor = today's open (fgd/day2/frd), the order price (para) or the run high (bag), +/- buf x ATR.
Sources: notes batches 9-12, 15, 16, 20, 22, 23 (see claude/humbled-trader-strategy-list.md).
"""
from __future__ import annotations
import numpy as np, pandas as pd
from .common import std_exits
from .ht_common import up_streak, index_bars, common_lines

OUT = "HT1"
TIER = "weak"
EVIDENCE = ("Only 'para' survives (limit buy at the prior-day low after a parabolic run, index opens up, target = run high): "
            "TSX IS +0.03R edge +0.14, OOS +0.01R edge +0.12; US IS +0.01R edge +0.12, OOS +0.02R edge +0.09 (all p<.001). "
            "Skill +32..+50 R/yr vs random twins, but costs eat it: 2-6% CAGR at 0.12%/side, 7-14% at 0.05%/side. "
            "fgd/day2/frd/bag rejected (docs/REJECTED_LOG.md).")
CHUNK = 10
SIDES = (1, -1)
MODES = [3]
BUFS = [0.5, 1.0]
FLAGS = ["all", "trend200", "streak3", "idx_up", "big"]
EXITS = {"day": dict(same_day=True),
         "next": dict(time_bars=1),
         "time3": dict(time_bars=3),
         "opp": dict(target="opp", max_hold=5),
         "2R": dict(target_R=2.0, max_hold=10)}
TARGETS = list(EXITS)


def signals(df, ctx):
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    v = df.volume.to_numpy(float); n = len(c); A = ctx["atr"]
    s200 = ctx["sma"][200]; vol20 = pd.Series(v).rolling(20).mean().shift(1).to_numpy()
    st = up_streak(c); ix = index_bars(df, ctx)
    hi60 = pd.Series(h).rolling(60).max().shift(1).to_numpy()          # max high of [t-60, t-1]
    rng = np.where(h - l > 0, h - l, np.nan); pos = (c - l) / rng      # close location in range
    rows = []
    for t in range(201, n):
        p = t - 1                                                       # prior bar: everything here is known at t's open
        if not (np.isfinite(A[p]) and A[p] > 0):
            continue
        idx_up = bool(np.isfinite(ix["c"][p]) and ix["o"][t] >= ix["c"][p])     # index opens flat/up
        idx_dn = bool(np.isfinite(ix["c"][p]) and ix["o"][t] < ix["c"][p])
        tr = bool(c[p] > s200[p])
        base = dict(t=t, A=A[p], opp=np.nan, all=True, trend200=tr, idx_up=idx_up)
        # fgd: first green day
        if st[p] <= -2 and o[t] < c[p] and h[t] >= c[p]:
            rows.append(dict(base, side=1, fam="fgd", px=c[p], anchor=o[t], streak3=st[p] <= -3,
                             big=(c[p] / c[p - 5] - 1) <= -0.05))
        # day2: reclaim of a strong breakout day
        if (p >= 2 and c[p] / c[p - 1] - 1 >= 0.03 and np.isfinite(vol20[p]) and v[p] >= 1.5 * vol20[p]
                and pos[p] >= 0.8 and np.isfinite(hi60[p]) and c[p] > hi60[p]
                and o[t] < c[p] and h[t] >= c[p] and h[p] > c[p]):
            rows.append(dict(base, side=1, fam="day2", px=c[p], anchor=o[t], opp=h[p], streak3=False,
                             big=c[p] / c[p - 1] - 1 >= 0.05))
        # frd: first red day (short)
        if st[p] >= 5 and o[t] > c[p] and l[t] <= c[p]:
            rows.append(dict(base, side=-1, fam="frd", px=c[p], anchor=o[t], opp=l[p], idx_up=idx_dn,
                             streak3=st[p] >= 7, big=bool(np.isfinite(ctx["hi252"][p]) and h[p] >= ctx["hi252"][p])))
        # para: parabolic run -> limit at the prior-day low
        ups6 = int(np.sum(np.diff(c[p - 6:p + 1]) > 0))
        run10 = c[p] / c[p - 10] - 1
        if (ups6 >= 5 or run10 >= 0.15) and l[t] <= l[p]:
            px = min(o[t], l[p])
            rows.append(dict(base, side=1, fam="para", px=px, anchor=px, opp=float(np.max(h[p - 5:p + 1])),
                             streak3=ups6 >= 5, big=run10 >= 0.15))
        # bag: bagholder pop in a downtrend (short)
        lo3 = np.min(c[p - 3:p])
        wick = (h[p] - max(o[p], c[p])) >= 0.4 * (h[p] - l[p]) if h[p] > l[p] else False
        if (c[p] < s200[p] and c[p] / lo3 - 1 >= 0.10 and l[t] <= c[p]):
            px = min(o[t], c[p])
            rows.append(dict(base, side=-1, fam="bag", px=px, anchor=max(float(np.max(h[p - 2:p + 1])), o[t]),
                             trend200=False, idx_up=idx_dn, streak3=bool(wick), big=c[p] / lo3 - 1 >= 0.20))
    cols = ["t", "side", "anchor", "A", "opp", "px", "fam"] + FLAGS
    out = pd.DataFrame(rows, columns=cols)
    out[FLAGS] = out[FLAGS].astype(bool)
    return out


def lines(df, ctx, fam, side):
    return common_lines(df, side)


# flags per family: trend200 = prior close > 200 SMA (shorts: n/a), streak3 = longer streak (fgd 3 red, frd 7 green,
# para 5-of-6 rule, bag upper wick), idx_up = index opens with the trade (longs up, shorts down), big = bigger move
def specs():
    out = []
    for fam in ("fgd", "day2", "frd", "para", "bag"):
        for fl in ((), ("trend200",), ("streak3",), ("idx_up",), ("big",)):
            if fam in ("frd", "bag") and fl == ("trend200",):
                continue
            out.append((dict(fam=fam, flt="+".join(fl) or "none"), fam, fl))
    return out


NAMED = {
    "as taught: first green day (buy-stop at prior close, out at close)": dict(fam="fgd", flags=(), target="day", mode=3, buf=0.5, sides=(1,)),
    "as taught: day-2 reclaim (target day-1 high)": dict(fam="day2", flags=(), target="opp", mode=3, buf=0.5, sides=(1,)),
    "as taught: first red day short (cover prior-day low)": dict(fam="frd", flags=(), target="opp", mode=3, buf=0.5, sides=(-1,)),
    "as taught: parabolic dip limit at prior low": dict(fam="para", flags=(), target="opp", mode=3, buf=1.0, sides=(1,)),
    "as taught: bagholder short (large-cap analog)": dict(fam="bag", flags=("streak3",), target="day", mode=3, buf=0.5, sides=(-1,)),
}
LADDER = dict(base=dict(fam="fgd", flags=(), target="day", mode=3, buf=0.5), steps=[
    ("base", {}, True), ("+ 3 red closes", {"add": "streak3"}, True), ("+ index opens up", {"add": "idx_up"}, True),
    ("+ above 200 SMA", {"add": "trend200"}, True), ("hold 3 days", {"target": "time3"}, False)])
KEEP = {
    "parabolic dip limit at prior low, index opens up, target run high": dict(fam="para", flags=("idx_up",), target="opp", mode=3, buf=1.0, sides=(1,)),
}
LIVE = "parabolic dip limit at prior low, index opens up, target run high"
