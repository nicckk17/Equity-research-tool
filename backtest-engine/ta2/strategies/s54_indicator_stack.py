"""S54 indicator stack (SAR + Force + MACD votes). TIER: WEAK (TSX only; failed US). Signal code from v1."""

from __future__ import annotations

import time
import numpy as np
import pandas as pd
from numba import njit

OUT = "S54"
CHUNK = 5
SIDES = (1, -1)
MODES = [0, 1]
BUFS = [0.1, 0.5]
FLAGS = ["all", "trend200", "slope", "volume"]
FAMILIES = ("one_candle", "two", "three")
EPISODE_GAP = 15


def _clean(df, ctx):
    if not isinstance(df.index, pd.DatetimeIndex) or not df.index.is_unique or not df.index.is_monotonic_increasing:
        raise ValueError("df requires a unique increasing DatetimeIndex")
    a = np.asarray(ctx["atr"], dtype=float)
    if a.ndim != 1 or len(a) != len(df):
        raise ValueError("ATR must align with df")
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    good = (np.isfinite(o) & np.isfinite(h) & np.isfinite(l) & np.isfinite(c)
            & (h >= np.maximum(o, c)) & (l <= np.minimum(o, c)))
    pos = np.flatnonzero(good)
    return df.iloc[pos], a[pos], pos


@njit(cache=True)
def _sar(h, l, c):
    """Wilder-style SAR: AF .02, step .02, cap .20; prior two-bar clamp."""
    out = np.full(len(c), np.nan)
    direction = 0
    sar, extreme, af = 0., 0., .02
    for t in range(1, len(c)):
        if direction == 0:
            if c[t] == c[t-1]:
                continue
            direction = 1 if c[t] > c[t-1] else -1
            sar = min(l[t-1], l[t]) if direction == 1 else max(h[t-1], h[t])
            extreme = max(h[t-1], h[t]) if direction == 1 else min(l[t-1], l[t])
        else:
            candidate = sar + af * (extreme-sar)
            if direction == 1:
                candidate = min(candidate, l[t-1], l[max(0,t-2)])
                if l[t] < candidate:
                    direction, sar, extreme, af = -1, extreme, l[t], .02
                else:
                    sar = candidate
                    if h[t] > extreme:
                        extreme, af = h[t], min(.20, af+.02)
            else:
                candidate = max(candidate, h[t-1], h[max(0,t-2)])
                if h[t] > candidate:
                    direction, sar, extreme, af = 1, extreme, h[t], .02
                else:
                    sar = candidate
                    if l[t] < extreme:
                        extreme, af = l[t], min(.20, af+.02)
        out[t] = sar
    return out


def _features(bars):
    c = bars.close.astype(float)
    ema = {k: c.ewm(span=k, adjust=False, min_periods=k).mean() for k in (12,20,26,50,200)}
    macd = ema[12]-ema[26]
    histogram = macd-macd.ewm(span=9, adjust=False, min_periods=9).mean()
    # Unknown volume never supplies a Force vote or an entry. No backward fill.
    v = bars.volume.astype(float).where(lambda x: np.isfinite(x) & (x >= 0))
    force = (c.diff()*v).ewm(span=13, adjust=False, min_periods=13).mean().where(v.notna())
    sar = _sar(bars.high.to_numpy(dtype=float), bars.low.to_numpy(dtype=float), c.to_numpy())
    values = np.column_stack([c.to_numpy()-sar, force.to_numpy(), histogram.to_numpy()])
    ready = np.isfinite(values).all(axis=1) & ema[50].notna().to_numpy()
    votes = np.column_stack([(values > 0).sum(axis=1), (values < 0).sum(axis=1)]).astype(np.int64)
    votes[~ready] = -1
    return ema, votes, ready, v


def signals(df, ctx):
    started = time.perf_counter()
    columns = ["t", "side", "anchor", "A", "opp", "fam"] + FLAGS
    bars, a, pos = _clean(df, ctx)
    ema, votes, ready, volume = _features(bars)
    c, o = bars.close.to_numpy(dtype=float), bars.open.to_numpy(dtype=float)
    floor = bars.low.rolling(10).min().to_numpy()
    ceiling = bars.high.rolling(10).max().to_numpy()
    prior_volume = volume.rolling(10).mean().shift().to_numpy()
    rows = []
    for side, col in ((1,0), (-1,1)):
        trend = ((side*(ema[20]-ema[50]) > 0) & (side*(bars.close-ema[50]) > 0)).to_numpy()
        for fam in FAMILIES:
            needed = 1 if fam == "one_candle" else (2 if fam == "two" else 3)
            qualified = ready & trend & (votes[:,col] >= needed)
            if fam == "one_candle":
                qualified &= side*(c-o) > 0
            previous, last = False, -EPISODE_GAP
            for t, active in enumerate(qualified):
                start = active and not previous
                previous = active  # Consume raw transitions even inside cooldown.
                if not start or t-last < EPISODE_GAP:
                    continue
                last = t
                anchor = floor[t] if side == 1 else ceiling[t]
                if not np.isfinite(a[t]) or a[t] <= 0 or not np.isfinite(anchor):
                    continue
                rows.append(dict(t=int(pos[t]), side=side, anchor=anchor, A=a[t], opp=np.nan,
                                 fam=fam, all=True,
                                 trend200=bool(side*(c[t]-ema[200].iloc[t]) > 0),
                                 slope=bool(t >= 5 and side*(ema[50].iloc[t]-ema[50].iloc[t-5]) > 0),
                                 volume=bool(volume.iloc[t] > prior_volume[t])))
    result = pd.DataFrame(rows, columns=columns)
    result[FLAGS] = result[FLAGS].astype(bool)
    print(f"S54 signals: {len(result)} rows; invalid OHLC skipped {len(df)-len(bars)}; elapsed {time.perf_counter()-started:.3f}s", flush=True)
    return result.sort_values(["t","side","fam"], kind="stable", ignore_index=True)


def specs():
    return [(dict(signals_needed=fam,gate=gate),fam,flags)
            for fam in FAMILIES
            for gate,flags in (("none",()),("200MA",("trend200",)),
                               ("slope",("slope",)),("volume",("volume",)))]


NAMED = {
    "as taught (2 of 3, MA uptrend, next open, 2R)": dict(fam="two",flags=(),target="2R",mode=1,buf=.1,sides=(1,)),
    "as traded (2 of 3, MA uptrend, indicator flip)": dict(fam="two",flags=(),target="flip",mode=1,buf=.1,sides=(1,)),
    "taught alternative (1 plus candle, 2R)": dict(fam="one_candle",flags=(),target="2R",mode=1,buf=.1,sides=(1,)),
}
LADDER = dict(base=dict(fam="one_candle",flags=(),target="2R",mode=1,buf=.1),steps=[
    ("MA trend + 1 indicator + candle",{},True),
    ("2 of 3 indicators",{"fam":"two"},True),
    ("3 of 3 indicators",{"fam":"three"},False),
    ("+ price beyond 200MA",{"add":"trend200"},True),
    ("+ MA50 slope",{"add":"slope"},True),
    ("+ expanding volume",{"add":"volume"},True),
    ("indicator-flip exit",{"target":"flip"},False),
])


# ------------------------------------------------------------ v2 adapter
TIER = "weak"
EVIDENCE = ("as traded (2 of 3, indicator-flip exit): TSX IS +15 (p .002-.006), OOS +18 (p .03) R/yr; "
            "US IS +9 (p .2) and US OOS +22 (p .08-.09) not significant. Keep as a TSX-only weak edge.")
MAX_HOLD = 40
EXITS = {"2R": dict(target_R=2.0, max_hold=40), "flip": dict(state="flip", state_skip_first=True, max_hold=40)}
TARGETS = list(EXITS)


def lines(df, ctx, fam, side):
    _, votes, _, _ = _features(df)
    v = votes[:, 0] if side == 1 else votes[:, 1]
    # exit when the trade side has fewer than 2 of 3 votes (v1: 0 <= votes < 2); NaN = not ready (never exits)
    state = np.where(v < 0, np.nan, np.where(v < 2, -1.0, 1.0)) * side
    return {"flip": state}


KEEP = {
    "as traded: 2 of 3 indicators, MA uptrend, indicator-flip exit": dict(fam="two", flags=(), target="flip", mode=1, buf=0.1, sides=(1,)),
    "IS pick 2: 2 of 3, flip exit, wide stop": dict(fam="two", flags=(), target="flip", mode=1, buf=0.5, sides=(1,)),
}
LIVE = "as traded: 2 of 3 indicators, MA uptrend, indicator-flip exit"
